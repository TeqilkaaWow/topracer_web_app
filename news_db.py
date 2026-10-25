"""
Модуль для работы с базой данных новостей (SQLite)
"""
import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
DB_PATH = "news.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()

    # Таблица постов
    conn.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL,
            author_name TEXT NOT NULL,
            content TEXT NOT NULL,
            image_path TEXT,
            likes_count INTEGER DEFAULT 0,
            comments_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица лайков
    conn.execute('''
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(post_id, user_id)
        )
    ''')

    # Таблица комментариев
    conn.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Индексы
    conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_likes_post ON likes(post_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id)')

    conn.commit()
    conn.close()
    logger.info("✅ База данных новостей инициализирована")


def create_post(author_id, author_name, content, image_path=None):
    conn = get_db()
    cursor = conn.execute('''
        INSERT INTO posts (author_id, author_name, content, image_path)
        VALUES (?, ?, ?, ?)
    ''', (author_id, author_name, content, image_path))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return post_id


def get_posts(limit=50, offset=0):
    conn = get_db()
    posts = conn.execute('''
        SELECT * FROM posts
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', (limit, offset)).fetchall()
    conn.close()
    return [dict(row) for row in posts]


def get_post(post_id):
    conn = get_db()
    post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    conn.close()
    return dict(post) if post else None


def delete_post(post_id):
    conn = get_db()
    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.execute('DELETE FROM likes WHERE post_id = ?', (post_id,))
    conn.execute('DELETE FROM comments WHERE post_id = ?', (post_id,))
    conn.commit()
    conn.close()


def like_post(post_id, user_id):
    conn = get_db()
    try:
        conn.execute('INSERT INTO likes (post_id, user_id) VALUES (?, ?)', (post_id, user_id))
        conn.execute('UPDATE posts SET likes_count = likes_count + 1 WHERE id = ?', (post_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Уже лайкнул
        return False
    finally:
        conn.close()


def unlike_post(post_id, user_id):
    conn = get_db()
    conn.execute('DELETE FROM likes WHERE post_id = ? AND user_id = ?', (post_id, user_id))
    conn.execute('UPDATE posts SET likes_count = MAX(0, likes_count - 1) WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()


def is_liked(post_id, user_id):
    conn = get_db()
    result = conn.execute('SELECT id FROM likes WHERE post_id = ? AND user_id = ?', (post_id, user_id)).fetchone()
    conn.close()
    return result is not None


def add_comment(post_id, user_id, user_name, content):
    conn = get_db()
    cursor = conn.execute('''
        INSERT INTO comments (post_id, user_id, user_name, content)
        VALUES (?, ?, ?, ?)
    ''', (post_id, user_id, user_name, content))
    conn.execute('UPDATE posts SET comments_count = comments_count + 1 WHERE id = ?', (post_id,))
    comment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return comment_id


def get_comments(post_id, limit=100):
    conn = get_db()
    comments = conn.execute('''
        SELECT * FROM comments
        WHERE post_id = ?
        ORDER BY created_at ASC
        LIMIT ?
    ''', (post_id, limit)).fetchall()
    conn.close()
    return [dict(row) for row in comments]


def delete_comment(comment_id):
    conn = get_db()
    comment = conn.execute('SELECT post_id FROM comments WHERE id = ?', (comment_id,)).fetchone()
    if comment:
        conn.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
        conn.execute('UPDATE posts SET comments_count = MAX(0, comments_count - 1) WHERE id = ?', (comment['post_id'],))
        conn.commit()
    conn.close()