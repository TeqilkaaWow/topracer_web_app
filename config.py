import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Google Sheets
    GOOGLE_SHEET_ID = "1XE5Spg0wAIQIwo1I0p2UJqZe7LjrHPxv9RWkhx7-Lpg"
    CREDENTIALS_FILE = "credentials.json"

    # Бонусы
    WELCOME_BONUS_MINUTES = 30
    BONUS_VALIDITY_DAYS = 30
    TOURNAMENT_BONUS_MINUTES = 30
    WELCOME_BONUS_COINS = 500
    TOURNAMENT_BONUS_COINS = 500
    VISIT_BONUS_COINS = 50

    # QR коды
    QR_CODES_FOLDER = "qr_codes"

    # ✅ НАСТРОЙКИ СЕССИИ (ДОБАВИТЬ/ИЗМЕНИТЬ)
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)  # 30 дней вместо 7
    SESSION_PERMANENT = True  # Сделать сессию постоянной

    # ✅ "ЗАПОМНИТЬ МЕНЯ" (ДОБАВИТЬ)
    REMEMBER_COOKIE_DURATION = timedelta(days=30)  # Cookie на 30 дней
    REMEMBER_COOKIE_SECURE = False  # True только для HTTPS
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_REFRESH_EACH_REQUEST = True  # Обновлять при каждом запросе

    # Загрузка файлов
    UPLOAD_FOLDER = 'static/uploads/avatars'
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB