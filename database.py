import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import logging
import re
import json
import os

logger = logging.getLogger(__name__)

AUTH_FILE = "users_auth.json"


class Database:
    def __init__(self, config):
        self.config = config
        self.SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

        credentials_file = getattr(config, 'CREDENTIALS_FILE', 'credentials.json')
        self.creds = Credentials.from_service_account_file(credentials_file, scopes=self.SCOPES)
        self.gc = gspread.authorize(self.creds)

        sheet_id = getattr(config, 'GOOGLE_SHEET_ID', "1tFBii2ByZLhOQ4-xBNKlanY-jSr__OiAHF2x8Px_K3Q")
        self.sheet = self.gc.open_by_key(sheet_id)

        # Константы бонусов
        self.WELCOME_BONUS_MINUTES = getattr(config, 'WELCOME_BONUS_MINUTES', 30)
        self.BONUS_VALIDITY_DAYS = getattr(config, 'BONUS_VALIDITY_DAYS', 30)
        self.TOURNAMENT_BONUS_MINUTES = getattr(config, 'TOURNAMENT_BONUS_MINUTES', 30)
        self.WELCOME_BONUS_COINS = getattr(config, 'WELCOME_BONUS_COINS', 500)
        self.TOURNAMENT_BONUS_COINS = getattr(config, 'TOURNAMENT_BONUS_COINS', 500)
        self.VISIT_BONUS_COINS = getattr(config, 'VISIT_BONUS_COINS', 50)
        self.QR_CODES_FOLDER = getattr(config, 'QR_CODES_FOLDER', 'qr_codes')

        # Заголовки Google Sheets
        self.HEADER_TOP_RACER_ID = "TopRacerDataBase ID "
        self.HEADER_NICKNAME = "Ник-нейм "
        self.HEADER_PROFILE = "Профиль Телеграмм "
        self.HEADER_REG_DATE = "Дата регистрации "
        self.HEADER_LEVEL = "Уровень "
        self.HEADER_VISITS = "Колличество посещений "
        self.HEADER_TELEGRAM_ID = "Telegram ID "
        self.HEADER_LAST_VISIT = "Последний визит "
        self.HEADER_ADMIN = "Администратор "
        self.HEADER_PHONE = "Номер телефона "
        self.HEADER_TOPCOINS = "TopCoins "
        self.HEADER_BONUS_MINUTES = "Бонусные минуты "
        self.HEADER_BONUS_EXPIRY = "Срок действия бонуса "

        self.EXPECTED_HEADERS = [
            self.HEADER_TOP_RACER_ID, self.HEADER_NICKNAME, self.HEADER_PROFILE,
            self.HEADER_REG_DATE, self.HEADER_LEVEL, self.HEADER_VISITS,
            self.HEADER_TELEGRAM_ID, self.HEADER_LAST_VISIT, self.HEADER_ADMIN,
            self.HEADER_PHONE, self.HEADER_TOPCOINS, self.HEADER_BONUS_MINUTES,
            self.HEADER_BONUS_EXPIRY
        ]

        # Турниры и трассы
        self.TOURNAMENT_INFO_TEXT = {
            "cs2": {"name": "Counter Strike 2", "emoji": "🎮", "sheet": "CS2_Registrations",
                    "description": "🏆 <b>🔥 Турнир по Counter-Strike 2 — формат 2x2 🔥</b>",
                    "register_text": "🎮 Зарегистрироваться на CS2"},
            "mk": {"name": "Mortal Kombat", "emoji": "🥋", "sheet": "MK_Registrations",
                   "description": "🏆 <b> Турнир по Mortal Kombat 11 🔥</b>",
                   "register_text": "🥋 Зарегистрироваться на Mortal Kombat"},
            "gt": {"name": "Gran Turismo", "emoji": "🏎️", "sheet": "GT_Registrations",
                   "description": "🏎️ <b>Турнир по Gran Turismo 7</b>",
                   "register_text": "🏎️ Зарегистрироваться на Gran Turismo"},
            "ufc": {"name": "UFC 5/6", "emoji": "🥊", "sheet": "UFC_Registrations",
                    "description": "🔥 <b>ТУРНИРЫ ПО UFC 5 И UFC 6</b>",
                    "register_text": "🥊 Зарегистрироваться на UFC"}
        }

        self.BRANCHES = {
            "summer": {"name": "Лето", "address": "Филиал Лето, пр-кт. Московский, 19"},
            "prospekt": {"name": "Проспект", "address": "Филиал Проспект, пр-кт. Ленина, 33"},
            "raduga": {"name": "Радуга", "address": "Филиал Радуга, пр-кт. Шахтёров, 54"}
        }

        self.GT_TRACKS = {
            "monza": {"name": "Монца", "emoji": "🇮"},
            "nurburgring": {"name": "Нюрбургринг", "emoji": "🇩🇪"},
            "spa": {"name": "Спа", "emoji": "🇧🇪"},
            "tokio_expressway": {"name": "Токио Expressway", "emoji": "🇯🇵"},
            "laguna_seca": {"name": "Лагуна Сека", "emoji": "🇸"},
            "fuji": {"name": "Фудзи", "emoji": "🇵"},
            "interlagos": {"name": "Интерлагос", "emoji": "🇧🇷"},
            "bathurst": {"name": "Батхерст", "emoji": "🇦🇺"},
        }

    # ============================================================
    # РАБОТА С ЛОКАЛЬНЫМ ФАЙЛОМ АВТОРИЗАЦИИ (users_auth.json)
    # ============================================================

    def _load_auth_data(self):
        """Загружает данные авторизации из локального файла"""
        if os.path.exists(AUTH_FILE):
            try:
                with open(AUTH_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Ошибка чтения {AUTH_FILE}: {e}")
                return {}
        return {}

    def _save_auth_data(self, data):
        """Сохраняет данные авторизации в локальный файл"""
        with open(AUTH_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def register_auth_user(self, phone, password_hash, user_id, tracerdb_id, nickname):
        """Регистрирует пользователя в локальном файле авторизации"""
        try:
            auth_data = self._load_auth_data()
            phone_clean = re.sub(r'\D', '', phone)

            if phone_clean in auth_data:
                logger.warning(f"Пользователь с телефоном {phone_clean} уже существует")
                return {"success": False, "error": "Пользователь уже зарегистрирован"}

            auth_data[phone_clean] = {
                "user_id": user_id,
                "tracerdb_id": tracerdb_id,
                "password_hash": password_hash,
                "phone": phone,
                "nickname": nickname,
                "created_at": datetime.now().isoformat()
            }

            self._save_auth_data(auth_data)
            logger.info(f"✅ Пользователь сохранён в {AUTH_FILE}: {nickname} ({phone_clean})")
            return {"success": True}
        except Exception as e:
            logger.error(f"Ошибка регистрации в auth файле: {e}")
            return {"success": False, "error": str(e)}

    def verify_auth_user(self, phone, password):
        """Проверяет пароль пользователя по локальному файлу"""
        try:
            from werkzeug.security import check_password_hash
            auth_data = self._load_auth_data()
            phone_clean = re.sub(r'\D', '', phone)

            if phone_clean not in auth_data:
                logger.warning(f"Пользователь не найден в auth файле: {phone_clean}")
                return None

            user_auth = auth_data[phone_clean]
            if not check_password_hash(user_auth['password_hash'], password):
                logger.warning(f"Неверный пароль для {phone_clean}")
                return None

            logger.info(f"✅ Аутентификация успешна: {user_auth['nickname']} (ID: {user_auth['user_id']})")
            return user_auth
        except Exception as e:
            logger.error(f"Ошибка проверки пароля: {e}")
            return None

    def get_auth_user_by_id(self, user_id):
        """Находит пользователя в auth файле по user_id"""
        try:
            auth_data = self._load_auth_data()
            user_id_str = str(user_id)
            for phone_clean, user_auth in auth_data.items():
                if str(user_auth.get('user_id')) == user_id_str:
                    return user_auth
            return None
        except Exception as e:
            logger.error(f"Ошибка поиска в auth файле: {e}")
            return None

    def update_auth_nickname(self, phone, new_nickname):
        """Обновляет никнейм в auth файле"""
        try:
            auth_data = self._load_auth_data()
            phone_clean = re.sub(r'\D', '', phone)
            if phone_clean in auth_data:
                auth_data[phone_clean]['nickname'] = new_nickname
                self._save_auth_data(auth_data)
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления ника: {e}")
            return False

    # ============================================================
    # РАБОТА С GOOGLE SHEETS (ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ)
    # ============================================================

    def get_or_create_users_sheet(self):
        try:
            ws = self.sheet.worksheet("Users")
            return ws
        except gspread.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title="Users", rows="1000", cols="13")
            ws.append_row(self.EXPECTED_HEADERS)
            return ws

    def get_user_history_sheet(self, user_id):
        try:
            ws = self.sheet.worksheet(f"User_ID_{user_id}")
            return ws
        except gspread.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title=f"User_ID_{user_id}", rows="1000", cols="4")
            ws.append_row(["Дата", "Scanner ID", "Scanner Username", "Администратор"])
            return ws

    def get_tournament_registration_sheet(self, tournament_key):
        tournament = self.TOURNAMENT_INFO_TEXT[tournament_key]
        sheet_name = tournament["sheet"]
        try:
            ws = self.sheet.worksheet(sheet_name)
            return ws
        except gspread.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title=sheet_name, rows="1000", cols="15")
            headers = ["Дата регистрации", "Имя участника", "Номер телефона", "Филиал", "Турнир",
                       "Статус", "User ID", "Username", "TopCoins начислено", "Бонусные минуты", "Срок действия бонуса"]
            ws.append_row(headers)
            return ws

    def get_lap_times_sheet(self):
        try:
            ws = self.sheet.worksheet("GranTurismo_LapTimes")
            return ws
        except gspread.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title="GranTurismo_LapTimes", rows="10000", cols="20")
            headers = ["Дата", "User ID", "Имя пользователя", "Трасса", "Время круга (сек)",
                       "Форматированное время", "Администратор", "Квалификация/Финал"]
            ws.append_row(headers)
            return ws

    def get_next_tracerdb_id(self, users_ws):
        try:
            all_data = users_ws.get_all_values()
            if not all_data or len(all_data) < 2:
                return 1
            max_id = 0
            for row in all_data[1:]:
                if not row:
                    continue
                try:
                    current_id = int(str(row[0]).strip())
                    if current_id > max_id:
                        max_id = current_id
                except (ValueError, TypeError):
                    continue
            return max_id + 1 if max_id > 0 else 1
        except Exception as e:
            logger.error(f"Ошибка получения следующего ID: {e}")
            return 1

    def find_user_by_id(self, user_id, users_ws):
        """Ищет пользователя по TopRacerDataBase ID (первая колонка)"""
        try:
            all_data = users_ws.get_all_values()
            if not all_data or len(all_data) < 2:
                return None
            user_id_str = str(user_id).strip()
            headers = all_data[0]
            for row in all_data[1:]:
                if not row:
                    continue
                row_id = str(row[0]).strip() if len(row) > 0 else ""
                if row_id == user_id_str:
                    record = {}
                    for i, header in enumerate(headers):
                        record[header] = row[i] if i < len(row) else ""
                    return record
            return None
        except Exception as e:
            logger.error(f"Ошибка поиска по ID: {e}")
            return None

    def find_user_by_phone(self, phone, users_ws):
        """Ищет пользователя по телефону"""
        try:
            all_data = users_ws.get_all_values()
            if not all_data or len(all_data) < 2:
                return None
            target_phone_clean = re.sub(r'\D', '', phone)
            if target_phone_clean.startswith('8') and len(target_phone_clean) == 11:
                target_phone_clean = '7' + target_phone_clean[1:]
            headers = all_data[0]
            phone_col_index = None
            for i, header in enumerate(headers):
                if "телефон" in str(header).lower() or "phone" in str(header).lower():
                    phone_col_index = i
                    break
            if phone_col_index is None:
                return None
            for row in all_data[1:]:
                if not row or len(row) <= phone_col_index:
                    continue
                phone_value = str(row[phone_col_index]).strip()
                phone_clean = re.sub(r'\D', '', phone_value)
                if phone_clean.startswith('8') and len(phone_clean) == 11:
                    phone_clean = '7' + phone_clean[1:]
                if phone_clean == target_phone_clean:
                    record = {}
                    for i, header in enumerate(headers):
                        record[header] = row[i] if i < len(row) else ""
                    return record
            return None
        except Exception as e:
            logger.error(f"Ошибка поиска по телефону: {e}")
            return None

    def get_topcoins(self, user_id):
        try:
            users_ws = self.get_or_create_users_sheet()
            record = self.find_user_by_id(user_id, users_ws)
            if record:
                balance = record.get(self.HEADER_TOPCOINS, 0)
                if isinstance(balance, str):
                    balance = int(balance.replace("TC", "").strip() or 0)
                return int(balance) if balance else 0
            return 0
        except Exception as e:
            logger.error(f"Ошибка получения TopCoins: {e}")
            return 0

    def update_topcoins(self, user_id, amount, operation="add"):
        try:
            users_ws = self.get_or_create_users_sheet()
            all_data = users_ws.get_all_values()
            if not all_data or len(all_data) < 2:
                return None
            user_row = None
            for i, row in enumerate(all_data[1:], start=2):
                if row and str(row[0]).strip() == str(user_id).strip():
                    user_row = i
                    break
            if user_row:
                current_balance = self.get_topcoins(user_id)
                new_balance = current_balance + amount if operation == "add" else max(0, current_balance - amount)
                users_ws.update(f'K{user_row}', [[f"{new_balance} TC"]])
                return new_balance
            return None
        except Exception as e:
            logger.error(f"Ошибка обновления TopCoins: {e}")
            return None

    def get_bonus_minutes(self, user_id):
        try:
            users_ws = self.get_or_create_users_sheet()
            record = self.find_user_by_id(user_id, users_ws)
            if record:
                minutes = record.get(self.HEADER_BONUS_MINUTES, 0)
                if isinstance(minutes, str):
                    minutes = int(minutes.replace("мин", "").strip() or 0)
                return int(minutes) if minutes else 0
            return 0
        except Exception as e:
            logger.error(f"Ошибка получения бонусных минут: {e}")
            return 0

    def add_bonus_minutes(self, user_id, minutes):
        try:
            users_ws = self.get_or_create_users_sheet()
            all_data = users_ws.get_all_values()
            if not all_data or len(all_data) < 2:
                return None, None
            user_row = None
            for i, row in enumerate(all_data[1:], start=2):
                if row and str(row[0]).strip() == str(user_id).strip():
                    user_row = i
                    break
            if user_row:
                current_minutes = self.get_bonus_minutes(user_id)
                new_minutes = current_minutes + minutes
                expiry_date = (datetime.now() + timedelta(days=self.BONUS_VALIDITY_DAYS)).strftime("%d.%m.%Y")
                users_ws.update(f'L{user_row}', [[f"{new_minutes} мин"]])
                users_ws.update(f'M{user_row}', [[expiry_date]])
                return new_minutes, expiry_date
            return None, None
        except Exception as e:
            logger.error(f"Ошибка добавления бонусных минут: {e}")
            return None, None

    def use_bonus_minutes(self, user_id, minutes_to_use):
        try:
            users_ws = self.get_or_create_users_sheet()
            all_data = users_ws.get_all_values()
            if not all_data or len(all_data) < 2:
                return None
            user_row = None
            for i, row in enumerate(all_data[1:], start=2):
                if row and str(row[0]).strip() == str(user_id).strip():
                    user_row = i
                    break
            if user_row:
                current_minutes = self.get_bonus_minutes(user_id)
                if current_minutes >= minutes_to_use:
                    new_minutes = current_minutes - minutes_to_use
                    users_ws.update(f'L{user_row}', [[f"{new_minutes} мин"]])
                    return new_minutes
                return None
        except Exception as e:
            logger.error(f"Ошибка использования бонусных минут: {e}")
            return None

    def register_user(self, nickname, phone, password_hash, registered_by=None):
        """Регистрирует нового пользователя"""
        try:
            phone_digits = re.sub(r'\D', '', phone)
            if phone_digits.startswith('8') and len(phone_digits) == 11:
                phone_digits = '7' + phone_digits[1:]

            formatted_phone = f"+{phone_digits[0]} ({phone_digits[1:4]}) {phone_digits[4:7]}-{phone_digits[7:9]}-{phone_digits[9:]}"

            users_ws = self.get_or_create_users_sheet()
            all_data = users_ws.get_all_values()

            # Проверяем, существует ли уже
            if all_data:
                for row in all_data[1:]:
                    if len(row) > 9 and re.sub(r'\D', '', str(row[9])) == phone_digits:
                        return {'success': False, 'error': 'Пользователь уже существует'}

            # Генерируем ID
            tracerdb_id = self.get_next_tracerdb_id(users_ws)
            reg_date = datetime.now().strftime("%d/%m/%Y %H:%M")
            expiry_date = (datetime.now() + timedelta(days=self.BONUS_VALIDITY_DAYS)).strftime("%d.%m.%Y")

            # Определяем кто зарегистрировал
            registered_by_str = str(registered_by) if registered_by else "self"

            # Добавляем в таблицу
            users_ws.append_row([
                tracerdb_id,
                nickname,
                "",  # Профиль
                reg_date,
                1,  # Уровень
                0,  # Посещения
                tracerdb_id,  # Telegram ID
                "",  # Последний визит
                "Нет",  # Администратор
                formatted_phone,
                f"{self.WELCOME_BONUS_COINS} TC",
                f"{self.WELCOME_BONUS_MINUTES} мин",
                expiry_date,
                registered_by_str  # Кто зарегистрировал
            ])

            # Сохраняем пароль
            self.save_user_password(formatted_phone, password_hash, tracerdb_id, tracerdb_id, nickname)

            logger.info(f"✅ Пользователь {nickname} зарегистрирован (ID: {tracerdb_id})")
            return {'success': True, 'user_id': tracerdb_id}
        except Exception as e:
            logger.error(f"Ошибка регистрации: {e}")
            return {'success': False, 'error': str(e)}

    def record_visit(self, tracerdb_id, scanner_id, scanner_username, is_admin=False):
        try:
            users_ws = self.get_or_create_users_sheet()
            all_data = users_ws.get_all_values()
            if not all_data or len(all_data) < 2:
                return {"success": False, "error": "Таблица пуста"}

            user_row = None
            user_record = None
            headers = all_data[0]

            for i, row in enumerate(all_data[1:], start=2):
                if row and str(row[0]).strip() == str(tracerdb_id).strip():
                    user_row = i
                    user_record = {}
                    for j, header in enumerate(headers):
                        user_record[header] = row[j] if j < len(row) else ""
                    break

            if not user_row:
                return {"success": False, "error": "Пользователь не найден"}

            user_id = user_record.get(self.HEADER_TELEGRAM_ID, tracerdb_id)
            current_visits = int(user_record.get(self.HEADER_VISITS, 0))
            new_visits = current_visits + 1
            level = (new_visits // 10) + 1
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M")

            users_ws.update(f'E{user_row}', [[level]])
            users_ws.update(f'F{user_row}', [[new_visits]])
            users_ws.update(f'H{user_row}', [[current_time]])
            users_ws.update(f'I{user_row}', [["Да" if is_admin else "Нет"]])

            current_topcoins = self.get_topcoins(user_id)
            new_topcoins = current_topcoins + self.VISIT_BONUS_COINS
            users_ws.update(f'K{user_row}', [[f"{new_topcoins} TC"]])

            user_ws = self.get_user_history_sheet(user_id)
            user_ws.append_row([current_time, scanner_id, scanner_username, "Да" if is_admin else "Нет"])

            return {
                "success": True,
                "tracerdb_id": tracerdb_id,
                "total_visits": new_visits,
                "level": level,
                "username": user_record.get(self.HEADER_NICKNAME, "Неизвестно"),
                "topcoins_earned": self.VISIT_BONUS_COINS,
                "topcoins_balance": new_topcoins
            }
        except Exception as e:
            logger.error(f"Ошибка записи посещения: {e}")
            return {"success": False, "error": str(e)}

    def get_user_history(self, user_id):
        try:
            user_ws = self.get_user_history_sheet(user_id)
            return user_ws.get_all_records()
        except:
            return []

    def save_lap_time(self, user_id, username, track_key, lap_time_seconds, admin_id, is_qualification=True):
        try:
            ws = self.get_lap_times_sheet()
            track = self.GT_TRACKS.get(track_key, {"name": track_key})
            minutes = int(lap_time_seconds // 60)
            secs = lap_time_seconds % 60
            formatted_time = f"{minutes}:{secs:06.3f}"
            session_type = "Квалификация" if is_qualification else "Финал"
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            ws.append_row([current_time, str(user_id), username, track["name"],
                           lap_time_seconds, formatted_time, str(admin_id), session_type])
            return {"success": True, "formatted_time": formatted_time}
        except Exception as e:
            logger.error(f"Ошибка сохранения времени круга: {e}")
            return {"success": False, "error": str(e)}

    def get_track_records(self, track_key, limit=10):
        try:
            ws = self.get_lap_times_sheet()
            records = ws.get_all_records()
            track = self.GT_TRACKS.get(track_key, {"name": track_key})
            track_records = []
            for record in records:
                if record.get("Трасса", "") == track["name"]:
                    track_records.append({
                        "username": record.get("Имя пользователя", "Неизвестно"),
                        "time": float(record.get("Время круга (сек)", 0)),
                        "formatted": record.get("Форматированное время", ""),
                        "date": record.get("Дата", ""),
                    })
            track_records.sort(key=lambda x: x["time"])
            return track_records[:limit]
        except Exception as e:
            logger.error(f"Ошибка получения рекордов: {e}")
            return []

    def save_tournament_registration(self, tournament_key, name, phone, branch_key, user_id, username):
        try:
            tournament = self.TOURNAMENT_INFO_TEXT[tournament_key]
            branch = self.BRANCHES[branch_key]
            ws = self.get_tournament_registration_sheet(tournament_key)
            reg_date = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            expiry_date = (datetime.now() + timedelta(days=self.BONUS_VALIDITY_DAYS)).strftime("%d.%m.%Y")
            ws.append_row([reg_date, name, phone, branch["name"], tournament["name"],
                           "Зарегистрирован", str(user_id), username or "Нет username",
                           f"+{self.TOURNAMENT_BONUS_COINS} TC",
                           f"+{self.TOURNAMENT_BONUS_MINUTES} мин", expiry_date])
            return {
                "success": True, "tournament": tournament["name"],
                "branch": branch["name"], "branch_address": branch["address"],
                "name": name, "phone": phone, "reg_date": reg_date
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def calculate_progress(self, total_visits):
        current_level = (total_visits // 10) + 1
        visits_in_current_level = total_visits % 10
        visits_to_next_level = 10 - visits_in_current_level if visits_in_current_level > 0 else 0
        progress_percentage = (visits_in_current_level / 10) * 100
        filled = '▓' * visits_in_current_level
        empty = '░' * (10 - visits_in_current_level)
        progress_bar = f"[{filled}{empty}]"
        return {
            "current_level": current_level,
            "visits_in_level": visits_in_current_level,
            "visits_to_next": visits_to_next_level,
            "progress_percentage": progress_percentage,
            "progress_bar": progress_bar
        }

    def get_user_friends(self, user_id):
        """Получает список друзей пользователя"""
        try:
            friends_ws = self.get_or_create_friends_sheet()
            records = friends_ws.get_all_records()

            friends = []
            for record in records:
                if str(record.get('user_id', '')) == str(user_id):
                    friend_id = record.get('friend_id')
                    if friend_id:
                        # Получаем информацию о друге
                        users_ws = self.get_or_create_users_sheet()
                        friend_record = self.find_user_by_id(int(friend_id), users_ws)
                        if friend_record:
                            friends.append({
                                'id': int(friend_id),
                                'nickname': friend_record.get(self.HEADER_NICKNAME, 'Неизвестно'),
                                'avatar_url': f"/static/uploads/avatars/avatar_{friend_id}.png"
                            })

            return friends
        except Exception as e:
            logger.error(f"Ошибка получения друзей: {e}")
            return []

    def is_friend(self, user_id, friend_id):
        """Проверяет, является ли пользователь другом"""
        try:
            friends_ws = self.get_or_create_friends_sheet()
            records = friends_ws.get_all_records()

            for record in records:
                if (str(record.get('user_id', '')) == str(user_id) and
                        str(record.get('friend_id', '')) == str(friend_id)):
                    return True
            return False
        except:
            return False

    def add_friend(self, user_id, friend_id):
        """Добавляет пользователя в друзья"""
        try:
            if self.is_friend(user_id, friend_id):
                return False

            friends_ws = self.get_or_create_friends_sheet()
            friends_ws.append_row([
                user_id,
                friend_id,
                datetime.now().strftime("%d/%m/%Y %H:%M")
            ])
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления друга: {e}")
            return False

    def remove_friend(self, user_id, friend_id):
        """Удаляет пользователя из друзей"""
        try:
            friends_ws = self.get_or_create_friends_sheet()
            all_data = friends_ws.get_all_values()

            for i, row in enumerate(all_data[1:], start=2):
                if (len(row) >= 2 and
                        str(row[0]) == str(user_id) and
                        str(row[1]) == str(friend_id)):
                    friends_ws.delete_rows(i, i)
                    return True
            return False
        except Exception as e:
            logger.error(f"Ошибка удаления друга: {e}")
            return False

    # ============================================================
    # МЕТОДЫ ДЛЯ РАБОТЫ С ДРУЗЬЯМИ
    # ============================================================

    def get_or_create_friends_sheet(self):
        """Создает или получает лист друзей в Google Sheets"""
        try:
            ws = self.sheet.worksheet("Friends")
            return ws
        except gspread.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title="Friends", rows="1000", cols="3")
            ws.append_row(["user_id", "friend_id", "added_date"])
            logger.info("✅ Создан лист Friends")
            return ws

    def get_user_friends(self, user_id):
        """Получает список друзей пользователя"""
        try:
            friends_ws = self.get_or_create_friends_sheet()
            records = friends_ws.get_all_records()
            friends = []

            for record in records:
                if str(record.get('user_id', '')) == str(user_id):
                    friend_id = record.get('friend_id')
                    if friend_id:
                        try:
                            friend_id = int(friend_id)
                            users_ws = self.get_or_create_users_sheet()
                            friend_record = self.find_user_by_id(friend_id, users_ws)

                            if friend_record:
                                friends.append({
                                    'id': friend_id,
                                    'nickname': friend_record.get(self.HEADER_NICKNAME, 'Неизвестно'),
                                    'avatar_url': f"/static/uploads/avatars/avatar_{friend_id}.png"
                                })
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Ошибка обработки друга {friend_id}: {e}")

            return friends
        except Exception as e:
            logger.error(f"Ошибка получения друзей: {e}")
            return []

    def get_user_friends_count(self, user_id):
        """Возвращает количество друзей пользователя"""
        try:
            friends_ws = self.get_or_create_friends_sheet()
            records = friends_ws.get_all_records()
            count = sum(1 for r in records if str(r.get('user_id', '')) == str(user_id))
            return count
        except Exception as e:
            logger.error(f"Ошибка подсчета друзей: {e}")
            return 0

    def is_friend(self, user_id, friend_id):
        """Проверяет, является ли пользователь другом"""
        try:
            friends_ws = self.get_or_create_friends_sheet()
            records = friends_ws.get_all_records()

            for record in records:
                if (str(record.get('user_id', '')) == str(user_id) and
                        str(record.get('friend_id', '')) == str(friend_id)):
                    return True
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки дружбы: {e}")
            return False

    def add_friend(self, user_id, friend_id):
        """Добавляет пользователя в друзья"""
        try:
            # Проверяем, не являются ли уже друзьями
            if self.is_friend(user_id, friend_id):
                logger.info(f"Пользователи {user_id} и {friend_id} уже друзья")
                return False

            # Проверяем, не добавляет ли пользователь сам себя
            if str(user_id) == str(friend_id):
                return False

            friends_ws = self.get_or_create_friends_sheet()
            added_date = datetime.now().strftime("%d/%m/%Y %H:%M")

            friends_ws.append_row([
                int(user_id),
                int(friend_id),
                added_date
            ])

            logger.info(f"✅ Пользователь {friend_id} добавлен в друзья к {user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления друга: {e}")
            return False

    def remove_friend(self, user_id, friend_id):
        """Удаляет пользователя из друзей"""
        try:
            friends_ws = self.get_or_create_friends_sheet()
            all_data = friends_ws.get_all_values()

            if not all_data or len(all_data) < 2:
                return False

            for i, row in enumerate(all_data[1:], start=2):
                if (len(row) >= 2 and
                        str(row[0]).strip() == str(user_id).strip() and
                        str(row[1]).strip() == str(friend_id).strip()):
                    friends_ws.delete_rows(i, i)
                    logger.info(f"✅ Пользователь {friend_id} удален из друзей у {user_id}")
                    return True

            logger.warning(f"Дружба между {user_id} и {friend_id} не найдена")
            return False
        except Exception as e:
            logger.error(f"Ошибка удаления друга: {e}")
            return False

    def save_user_password(self, phone, password_hash, user_id, tracerdb_id, nickname):
        """Сохраняет пароль пользователя в локальный auth файл"""
        try:
            phone_digits = re.sub(r'\D', '', phone)
            if phone_digits.startswith('8') and len(phone_digits) == 11:
                phone_digits = '7' + phone_digits[1:]

            auth_data = self._load_auth_data()
            auth_data[phone_digits] = {
                "user_id": user_id,
                "tracerdb_id": tracerdb_id,
                "password_hash": password_hash,
                "phone": phone,
                "nickname": nickname,
                "created_at": datetime.now().isoformat()
            }
            self._save_auth_data(auth_data)
            logger.info(f"✅ Пароль сохранен для {phone_digits}")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения пароля: {e}")
            return False

    def update_auth_nickname(self, phone, new_nickname):
        """Обновляет никнейм в auth файле"""
        try:
            phone_digits = re.sub(r'\D', '', phone)
            if phone_digits.startswith('8') and len(phone_digits) == 11:
                phone_digits = '7' + phone_digits[1:]

            auth_data = self._load_auth_data()
            if phone_digits in auth_data:
                auth_data[phone_digits]['nickname'] = new_nickname
                self._save_auth_data(auth_data)
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления ника: {e}")
            return False

    def get_or_create_lap_times_sheet(self):
        """Создает или получает лист с временем кругов"""
        try:
            ws = self.sheet.worksheet("LapTimes")
            return ws
        except gspread.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title="LapTimes", rows="1000", cols="5")
            ws.append_row(["user_id", "nickname", "track_key", "lap_time_seconds", "lap_time_formatted", "set_date"])
            logger.info("✅ Создан лист LapTimes")
            return ws

    def save_lap_time(self, user_id, track_key, lap_time_seconds, lap_time_formatted):
        """Сохраняет лучшее время круга"""
        try:
            lap_ws = self.get_or_create_lap_times_sheet()
            users_ws = self.get_or_create_users_sheet()

            # Получаем никнейм
            record = self.find_user_by_id(user_id, users_ws)
            nickname = record.get(self.HEADER_NICKNAME, 'Неизвестно') if record else 'Неизвестно'

            # Проверяем, есть ли уже время для этой трассы
            all_data = lap_ws.get_all_values()
            existing_row = None

            if all_data and len(all_data) > 1:
                for i, row in enumerate(all_data[1:], start=2):
                    if (len(row) >= 3 and
                            str(row[0]) == str(user_id) and
                            str(row[2]) == track_key):
                        existing_row = i
                        # Если новое время лучше - обновляем
                        if float(row[3]) > lap_time_seconds:
                            lap_ws.update(f'D{i}', [[lap_time_seconds]])
                            lap_ws.update(f'E{i}', [[lap_time_formatted]])
                            lap_ws.update(f'F{i}', [[datetime.now().strftime("%d/%m/%Y %H:%M")]])
                            logger.info(f"✅ Обновлено время круга: {nickname} - {track_key} - {lap_time_formatted}")
                            return {'success': True, 'updated': True}
                        else:
                            return {'success': False, 'error': 'Текущее время лучше'}

            # Если нет существующей записи - добавляем новую
            if not existing_row:
                lap_ws.append_row([
                    user_id,
                    nickname,
                    track_key,
                    lap_time_seconds,
                    lap_time_formatted,
                    datetime.now().strftime("%d/%m/%Y %H:%M")
                ])
                logger.info(f"✅ Записано время круга: {nickname} - {track_key} - {lap_time_formatted}")
                return {'success': True, 'updated': False}

            return {'success': False, 'error': 'Ошибка'}
        except Exception as e:
            logger.error(f"Ошибка записи времени круга: {e}")
            return {'success': False, 'error': str(e)}

    def get_user_lap_times(self, user_id):
        """Получает все времена кругов пользователя"""
        try:
            lap_ws = self.get_or_create_lap_times_sheet()
            all_data = lap_ws.get_all_values()

            lap_times = []
            if all_data and len(all_data) > 1:
                for row in all_data[1:]:
                    if len(row) >= 5 and str(row[0]) == str(user_id):
                        lap_times.append({
                            'track_key': row[2],
                            'lap_time_seconds': float(row[3]),
                            'lap_time_formatted': row[4],
                            'set_date': row[5] if len(row) > 5 else ''
                        })

            return lap_times
        except Exception as e:
            logger.error(f"Ошибка получения времен кругов: {e}")
            return []

    def get_track_leaderboard(self, track_key, limit=10):
        """Получает таблицу лидеров для трассы"""
        try:
            lap_ws = self.get_or_create_lap_times_sheet()
            all_data = lap_ws.get_all_values()

            leaderboard = []
            if all_data and len(all_data) > 1:
                for row in all_data[1:]:
                    if len(row) >= 5 and str(row[2]) == track_key:
                        leaderboard.append({
                            'user_id': int(row[0]),
                            'nickname': row[1],
                            'lap_time_seconds': float(row[3]),
                            'lap_time_formatted': row[4],
                            'set_date': row[5] if len(row) > 5 else ''
                        })

            # Сортируем по времени
            leaderboard.sort(key=lambda x: x['lap_time_seconds'])
            return leaderboard[:limit]
        except Exception as e:
            logger.error(f"Ошибка получения таблицы лидеров: {e}")
            return []