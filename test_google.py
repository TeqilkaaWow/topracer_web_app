import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

try:
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key("1tFBii2ByZLhOQ4-xBNKlanY-jSr__OiAHF2x8Px_K3Q")
    print(f"✅ Успешно! Таблица: {sheet.title}")
    print(f"📋 Листы: {[ws.title for ws in sheet.worksheets()]}")
except Exception as e:
    print(f"❌ Ошибка: {e}")