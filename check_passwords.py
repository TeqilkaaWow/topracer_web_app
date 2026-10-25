import json
import os

if os.path.exists('passwords.json'):
    with open('passwords.json', 'r', encoding='utf-8') as f:
        passwords = json.load(f)

    print("📋 Сохранённые пароли:")
    for phone, hash_val in passwords.items():
        print(f" {phone}: {hash_val[:50]}...")
else:
    print("❌ Файл passwords.json не найден!")