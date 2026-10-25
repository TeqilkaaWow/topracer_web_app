from database import Database
from config import Config

db = Database(Config)

print("🔍 Проверка пользователей в базе данных\n")

users_ws = db.get_or_create_users_sheet()
records = users_ws.get_all_records()

print(f"📊 Всего пользователей: {len(records)}\n")

for i, record in enumerate(records, 1):
    phone = record.get(db.HEADER_PHONE, "")
    phone_clean = re.sub(r'\D', '', str(phone))
    print(f"{i}. Ник: {record.get(db.HEADER_NICKNAME, 'N/A')}")
    print(f"   Телефон: {phone}")
    print(f"   Телефон (чистый): {phone_clean}")
    print(f"   User ID: {record.get('User ID', 'N/A')}")
    print()

# Тест поиска
test_phone = "+79123456789"
print(f"\n🔎 Тест поиска пользователя с телефоном: {test_phone}")
user = db.find_user_by_phone(test_phone, users_ws)
if user:
    print(f"✅ Найден: {user.get(db.HEADER_NICKNAME)}")
else:
    print(" Не найден")