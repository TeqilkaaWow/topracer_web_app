"""
Скрипт для создания первого администратора в системе TopRace Z7.
Запускать один раз для создания учётной записи главного админа.
"""

from database import Database
from config import Config
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta


def create_first_admin():
    """Создаёт первого администратора"""

    print("=" * 60)
    print("🔧 Создание первого администратора TopRace Z7")
    print("=" * 60)

    # === НАСТРОЙКИ АДМИНА (ИЗМЕНИТЕ ПОД СЕБЯ!) ===
    nickname = "Admin"
    phone = "+79991234567"  # <-- УКАЖИТЕ СВОЙ ТЕЛЕФОН
    password = "admin123"  # <-- УКАЖИТЕ СВОЙ ПАРОЛЬ (мин. 6 символов)
    # ================================================

    print(f"\n Данные администратора:")
    print(f"   Никнейм: {nickname}")
    print(f"   Телефон: {phone}")
    print(f"   Пароль: {password}")
    print()

    # Инициализация базы данных
    print("🔌 Подключение к Google Sheets...")
    try:
        db = Database(Config)
        print("✅ Google Sheets подключена")
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        print("   Проверьте файл credentials.json")
        return

    # Получаем лист Users
    users_ws = db.get_or_create_users_sheet()

    # Проверяем, не существует ли уже пользователь с таким телефоном
    existing_user = db.find_user_by_phone(phone, users_ws)
    if existing_user:
        print(f"⚠️  Пользователь с телефоном {phone} уже существует!")
        print(f"   Никнейм: {existing_user.get(db.HEADER_NICKNAME, 'Неизвестно')}")
        print(f"   ID: {existing_user.get(db.HEADER_TOP_RACER_ID, 'N/A')}")
        print()

        # Спрашиваем, обновить ли его до админа
        answer = input("Назначить его администратором? (да/нет): ").strip().lower()
        if answer in ['да', 'yes', 'y', 'д']:
            # Находим строку пользователя
            all_data = users_ws.get_all_values()
            for i, row in enumerate(all_data[1:], start=2):
                if row and str(row[0]).strip() == str(existing_user.get(db.HEADER_TOP_RACER_ID)).strip():
                    # Обновляем статус админа (колонка I - 9-я)
                    col_letter = chr(64 + 9)  # I
                    users_ws.update(f'{col_letter}{i}', [['Да']])
                    print(f"✅ Пользователь назначен администратором!")

                    # Сохраняем/обновляем пароль
                    password_hash = generate_password_hash(password)
                    db.register_auth_user(phone, password_hash,
                                          existing_user.get(db.HEADER_TOP_RACER_ID),
                                          existing_user.get(db.HEADER_TOP_RACER_ID),
                                          nickname)
                    print(f"✅ Пароль обновлён")
                    return
        else:
            print("❌ Операция отменена")
            return

    # Создаём нового администратора
    print("📝 Создание нового администратора...")

    tracerdb_id = db.get_next_tracerdb_id(users_ws)
    reg_date = datetime.now().strftime("%d/%m/%Y %H:%M")
    expiry_date = (datetime.now() + timedelta(days=30)).strftime("%d.%m.%Y")

    # Добавляем в таблицу с флагом админа
    users_ws.append_row([
        tracerdb_id,  # TopRacerDataBase ID
        nickname,  # Ник-нейм
        "",  # Профиль
        reg_date,  # Дата регистрации
        1,  # Уровень
        0,  # Посещения
        tracerdb_id,  # Telegram ID
        "",  # Последний визит
        "Да",  # Администратор ✅
        phone,  # Номер телефона
        "0 TC",  # TopCoins
        "0 мин",  # Бонусные минуты
        expiry_date  # Срок действия бонуса
    ])

    print(f"✅ Запись добавлена в таблицу (ID: {tracerdb_id})")

    # Сохраняем пароль в локальный файл
    password_hash = generate_password_hash(password)
    auth_result = db.register_auth_user(phone, password_hash, tracerdb_id, tracerdb_id, nickname)

    if auth_result['success']:
        print(f"✅ Пароль сохранён в users_auth.json")
    else:
        print(f"⚠️  Ошибка сохранения пароля: {auth_result.get('error')}")

    # Итог
    print()
    print("=" * 60)
    print("✅ АДМИНИСТРАТОР УСПЕШНО СОЗДАН!")
    print("=" * 60)
    print(f"   ID: {tracerdb_id}")
    print(f"   Телефон: {phone}")
    print(f"   Пароль: {password}")
    print(f"   Права: Администратор")
    print()
    print(" Теперь вы можете войти в веб-приложение:")
    print(f"   URL: http://localhost:5000/login")
    print(f"   Телефон: {phone}")
    print(f"   Пароль: {password}")
    print()
    print("⚠️  ВАЖНО: Смените пароль после первого входа!")
    print("=" * 60)


if __name__ == '__main__':
    create_first_admin()