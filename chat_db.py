"""
Модуль для работы с базой данных чатов (SQLite)
"""
import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = "chats.db"


def get_db():
    """Получает подключение к базе данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Для лучшей производительности
    return conn


def init_db():
    """Инициализирует базу данных"""
    conn = get_db()
    cursor = conn.cursor()

    # Таблица сообщений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id)
        )
    ''')

    # Таблица пользователей (для кэширования ников)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            nickname TEXT NOT NULL,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Индексы для быстрого поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_unread ON messages(receiver_id, is_read)')

    conn.commit()
    conn.close()
    logger.info("✅ База данных чатов инициализирована")


def save_user(user_id, nickname):
    """Сохраняет/обновляет пользователя в БД чатов"""
    conn = get_db()
    conn.execute('''
        INSERT OR REPLACE INTO users (id, nickname, last_seen)
        VALUES (?, ?, ?)
    ''', (user_id, nickname, datetime.now()))
    conn.commit()
    conn.close()


def update_last_seen(user_id):
    """Обновляет время последней активности"""
    conn = get_db()
    conn.execute('''
        UPDATE users SET last_seen = ? WHERE id = ?
    ''', (datetime.now(), user_id))
    conn.commit()
    conn.close()


def send_message(sender_id, receiver_id, message):
    """Отправляет сообщение"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (sender_id, receiver_id, message, created_at)
        VALUES (?, ?, ?, ?)
    ''', (sender_id, receiver_id, message, datetime.now()))
    conn.commit()
    message_id = cursor.lastrowid
    conn.close()
    return message_id


def get_messages(user_id, friend_id, limit=100):
    """Получает историю переписки"""
    conn = get_db()
    messages = conn.execute('''
        SELECT * FROM messages
        WHERE (sender_id = ? AND receiver_id = ?)
           OR (sender_id = ? AND receiver_id = ?)
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, friend_id, friend_id, user_id, limit)).fetchall()
    conn.close()
    return list(reversed(messages))  # Возвращаем в хронологическом порядке


def get_unread_count(user_id, friend_id=None):
    """Получает количество непрочитанных сообщений"""
    conn = get_db()
    if friend_id:
        count = conn.execute('''
            SELECT COUNT(*) as count FROM messages
            WHERE receiver_id = ? AND sender_id = ? AND is_read = 0
        ''', (user_id, friend_id)).fetchone()['count']
    else:
        # ✅ ИСПРАВЛЕНО: добавлена запятая после user_id, чтобы это был кортеж (user_id,)
        count = conn.execute('''
            SELECT COUNT(*) as count FROM messages
            WHERE receiver_id = ? AND is_read = 0
        ''', (user_id,)).fetchone()['count']
    conn.close()
    return count


def mark_as_read(user_id, friend_id):
    """Отмечает сообщения как прочитанные"""
    conn = get_db()
    conn.execute('''
        UPDATE messages SET is_read = 1
        WHERE receiver_id = ? AND sender_id = ? AND is_read = 0
    ''', (user_id, friend_id))
    conn.commit()
    conn.close()


def get_conversations(user_id):
    """Получает список всех диалогов пользователя"""
    conn = get_db()

    # Сначала получаем список уникальных собеседников и время последнего сообщения
    partners = conn.execute('''
        SELECT 
            CASE 
                WHEN sender_id = ? THEN receiver_id
                ELSE sender_id
            END as partner_id,
            MAX(created_at) as last_message_time
        FROM messages
        WHERE sender_id = ? OR receiver_id = ?
        GROUP BY partner_id
        ORDER BY last_message_time DESC
    ''', (user_id, user_id, user_id)).fetchall()

    result = []
    for conv in partners:
        partner_id = conv['partner_id']

        # Получаем текст последнего сообщения
        last_msg = conn.execute('''
            SELECT message FROM messages 
            WHERE (sender_id = ? AND receiver_id = ?) 
               OR (sender_id = ? AND receiver_id = ?)
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id, partner_id, partner_id, user_id)).fetchone()

        # Получаем количество непрочитанных от этого собеседника
        unread = conn.execute('''
            SELECT COUNT(*) as count FROM messages
            WHERE receiver_id = ? AND sender_id = ? AND is_read = 0
        ''', (user_id, partner_id)).fetchone()['count']

        result.append({
            'friend_id': partner_id,
            'last_message_time': conv['last_message_time'],
            'last_message': last_msg['message'] if last_msg else '',
            'unread_count': unread
        })

    conn.close()
    return result


def get_user_nickname(user_id):
    """Получает никнейм пользователя из БД чатов"""
    conn = get_db()
    user = conn.execute('SELECT nickname FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user['nickname'] if user else None


def is_user_online(user_id, timeout_seconds=300):
    """Проверяет, был ли пользователь активен в последние 5 минут"""
    conn = get_db()
    user = conn.execute('SELECT last_seen FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if not user:
        return False
    last_seen = datetime.fromisoformat(str(user['last_seen']))
    return (datetime.now() - last_seen).seconds < timeout_seconds