"""
Скрипт для инициализации новой Google таблицы
Создает все необходимые листы с правильными заголовками
"""

import gspread
from google.oauth2.service_account import Credentials
import logging

# Настройки
NEW_SHEET_ID = "1XE5Spg0wAIQIwo1I0p2UJqZe7LjrHPxv9RWkhx7-Lpg"  # <-- ВСТАВЬТЕ СЮДА ID
CREDENTIALS_FILE = "credentials.json"

# Заголовки
EXPECTED_HEADERS = [
    "TopRacerDataBase ID ",
    "Ник-нейм ",
    "Профиль Телеграмм ",
    "Дата регистрации ",
    "Уровень ",
    "Колличество посещений ",
    "Telegram ID ",
    "Последний визит ",
    "Администратор ",
    "Номер телефона ",
    "TopCoins ",
    "Бонусные минуты ",
    "Срок действия бонуса "
]

EXPECTED_TOURNAMENT_HEADERS = [
    "Дата регистрации",
    "Имя участника",
    "Номер телефона",
    "Филиал",
    "Турнир",
    "Статус",
    "Telegram ID",
    "Telegram Username",
    "TopCoins начислено",
    "Бонусные минуты",
    "Срок действия бонуса"
]

EXPECTED_LAP_TIMES_HEADERS = [
    "Дата",
    "Telegram ID",
    "Имя пользователя",
    "Трасса",
    "Время круга (сек)",
    "Форматированное время",
    "Администратор",
    "Квалификация/Финал"
]

TOURNAMENT_SHEETS = {
    "CS2_Registrations": "Counter Strike 2",
    "MK_Registrations": "Mortal Kombat",
    "GT_Registrations": "Gran Turismo",
    "UFC_Registrations": "UFC 5/6"
}

GT_TRACKS = [
    "Монца", "Нюрбургринг", "Спа", "Судзука",
    "Лагуна Сека", "Фудзи", "Интерлагос", "Батхерст"
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_sheet():
    """Инициализирует новую таблицу"""

    print("=" * 60)
    print("🚀 Инициализация новой Google таблицы TopRace Z7")
    print("=" * 60)

    # Авторизация
    try:
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=SCOPES
        )
        gc = gspread.authorize(creds)
        print("✅ Авторизация успешна")
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        return

    # Открываем таблицу
    try:
        sheet = gc.open_by_key(NEW_SHEET_ID)
        print(f"✅ Таблица открыта: {sheet.title}")
    except Exception as e:
        print(f"❌ Ошибка открытия таблицы: {e}")
        print("Проверьте GOOGLE_SHEET_ID и доступы")
        return

    # Создаем лист Users
    try:
        users_ws = sheet.worksheet("Users")
        print("⚠️  Лист 'Users' уже существует")
    except gspread.WorksheetNotFound:
        users_ws = sheet.add_worksheet(title="Users", rows="1000", cols="13")
        users_ws.append_row(EXPECTED_HEADERS)
        print("✅ Создан лист 'Users' с заголовками")

    # Создаем лист для времени кругов
    try:
        lap_ws = sheet.worksheet("GranTurismo_LapTimes")
        print("⚠️  Лист 'GranTurismo_LapTimes' уже существует")
    except gspread.WorksheetNotFound:
        lap_ws = sheet.add_worksheet(title="GranTurismo_LapTimes", rows="10000", cols="20")
        lap_ws.append_row(EXPECTED_LAP_TIMES_HEADERS)
        print("✅ Создан лист 'GranTurismo_LapTimes'")

    # Создаем листы для турниров
    for sheet_name, tournament_name in TOURNAMENT_SHEETS.items():
        try:
            tourney_ws = sheet.worksheet(sheet_name)
            print(f"️  Лист '{sheet_name}' уже существует")
        except gspread.WorksheetNotFound:
            tourney_ws = sheet.add_worksheet(title=sheet_name, rows="1000", cols="15")
            tourney_ws.append_row(EXPECTED_TOURNAMENT_HEADERS)
            print(f"✅ Создан лист '{sheet_name}' ({tournament_name})")

    # Добавляем тестового админа (опционально)
    print("\n Добавление тестового администратора...")
    try:
        from datetime import datetime, timedelta

        tracerdb_id = 1
        reg_date = datetime.now().strftime("%d/%m/%Y %H:%M")
        expiry_date = (datetime.now() + timedelta(days=30)).strftime("%d.%m.%Y")

        users_ws.append_row([
            tracerdb_id,
            "Admin",
            "Администратор системы",
            reg_date,
            1,
            0,
            "5188161065",  # Telegram ID первого админа
            "",
            "Да",
            "+79999999999",
            "1000 TC",
            "100 мин",
            expiry_date
        ])
        print("✅ Добавлен тестовый администратор (ID: 1)")
    except Exception as e:
        print(f"️  Не удалось добавить админа: {e}")

    print("\n" + "=" * 60)
    print("✅ ИНИЦИАЛИЗАЦИЯ ЗАВЕРШЕНА!")
    print("=" * 60)
    print("\n Созданные листы:")
    print("  • Users - основные пользователи")
    print("  • GranTurismo_LapTimes - рекорды кругов")
    print("  • CS2_Registrations - турнир CS2")
    print("  • MK_Registrations - турнир Mortal Kombat")
    print("  • GT_Registrations - турнир Gran Turismo")
    print("  • UFC_Registrations - турнир UFC")
    print("\n Данные для входа админа:")
    print("  • TopRacer ID: 1")
    print("  • Ник: Admin")
    print("  • Telegram ID: 5188161065")
    print("=" * 60)


if __name__ == "__main__":
    init_sheet()