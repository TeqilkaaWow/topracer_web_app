"""
Модуль для работы с базой данных уведомлений (SQLite)
"""
import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
DB_PATH = "notifications.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            link TEXT DEFAULT '/',
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read)')
    conn.commit()
    conn.close()
    logger.info("✅ База данных уведомлений инициализирована")

def add_notification(user_id, notif_type, title, message, link="/"):
    conn = get_db()
    conn.execute('''
        INSERT INTO notifications (user_id, type, title, message, link)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, notif_type, title, message, link))
    conn.commit()
    conn.close()

def get_unread_count(user_id):
    conn = get_db()
    count = conn.execute('''
        SELECT COUNT(*) as count FROM notifications
        WHERE user_id = ? AND is_read = 0
    ''', (user_id,)).fetchone()['count']
    conn.close()
    return count

def get_recent_notifications(user_id, limit=10):
    conn = get_db()
    notifs = conn.execute('''
        SELECT * FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit)).fetchall()
    conn.close()
    return [dict(row) for row in notifs]

def mark_as_read(user_id, notif_id=None):
    conn = get_db()
    if notif_id:
        conn.execute('''
            UPDATE notifications SET is_read = 1
            WHERE user_id = ? AND id = ?
        ''', (user_id, notif_id))
    else:
        conn.execute('''
            UPDATE notifications SET is_read = 1
            WHERE user_id = ? AND is_read = 0
        ''', (user_id,))
    conn.commit()
    conn.close()

def get_admin_ids(db_instance):
    try:
        users_ws = db_instance.get_or_create_users_sheet()
        all_data = users_ws.get_all_values()
        admin_ids = []
        if all_data and len(all_data) > 1:
            headers = all_data[0]
            admin_idx = None
            id_idx = None
            for i, h in enumerate(headers):
                if 'админ' in str(h).lower():
                    admin_idx = i
                if 'topracer' in str(h).lower() or (str(h).strip().lower() == 'id'):
                    id_idx = i

            if admin_idx is not None and id_idx is not None:
                for row in all_data[1:]:
                    if len(row) > max(admin_idx, id_idx):
                        if str(row[admin_idx]).strip() == "Да":
                            try:
                                admin_ids.append(int(row[id_idx]))
                            except ValueError:
                                pass
        return admin_ids
    except Exception as e:
        logger.error(f"Ошибка получения админов: {e}")
        return []