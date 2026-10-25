"""
TopRace Z7 - Веб-приложение системы лояльности
Главный файл приложения Flask
"""
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from config import Config
from database import Database
import qrcode
from io import BytesIO
import os
import re
import logging
import random
import string
import asyncio
from datetime import datetime, timedelta

# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# СОЗДАНИЕ ПРИЛОЖЕНИЯ
# ============================================================
app = Flask(__name__)
app.config.from_object(Config)

# ============================================================
# НАСТРОЙКИ ЗАГРУЗКИ ФАЙЛОВ
# ============================================================
UPLOAD_FOLDER = 'static/uploads/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ============================================================
# ИНИЦИАЛИЗАЦИЯ БД И МЕНЕДЖЕРА ВХОДА
# ============================================================
db = Database(Config)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему'
login_manager.login_message_category = 'info'

# ============================================================
# ИМПОРТ ВСПОМОГАТЕЛЬНЫХ МОДУЛЕЙ
# ============================================================
try:
    from chat_db import init_db as init_chat_db, save_user, update_last_seen
    from chat_db import send_message, get_messages, get_unread_count as get_chat_unread
    from chat_db import mark_as_read as mark_chat_read, get_conversations, get_user_nickname, is_user_online
    init_chat_db()
    logger.info("✅ База данных чатов инициализирована")
except ImportError as e:
    logger.warning(f"⚠️ Модуль chat_db не найден: {e}")

try:
    from notifications_db import init_db as init_notif_db, add_notification, get_unread_count as get_notif_unread
    from notifications_db import get_recent_notifications, mark_as_read as mark_notif_read, get_admin_ids
    from push_notifications import send_push_notification, send_telegram_notification, notify_admins, \
        save_user_subscription

    init_notif_db()
    logger.info("✅ База данных уведомлений инициализирована")
except ImportError as e:
    logger.warning(f"⚠️ Модули уведомлений не найдены: {e}")

try:
    from news_db import (
        init_db as init_news_db, create_post, get_posts, get_post, delete_post,
        like_post, unlike_post, is_liked, add_comment, get_comments, delete_comment
    )
    init_news_db()
    logger.info("✅ База данных новостей инициализирована")
except ImportError as e:
    logger.warning(f"⚠️ Модуль news_db не найден: {e}")

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def allowed_file(filename):
    """Проверяет разрешение файла"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_avatar(file, user_id):
    """Обрабатывает загруженный файл: сохраняет и создает миниатюру"""
    if not allowed_file(file.filename):
        return None
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[1].lower()
    new_filename = f"avatar_{user_id}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
    file.save(filepath)
    try:
        img = Image.open(filepath)
        img.thumbnail((200, 200), Image.LANCZOS)
        thumb_filename = f"avatar_{user_id}_thumb.{ext}"
        thumb_path = os.path.join(app.config['UPLOAD_FOLDER'], thumb_filename)
        img.save(thumb_path, quality=85)
        return new_filename
    except Exception as e:
        logger.error(f"Ошибка при создании миниатюры: {e}")
        return new_filename

def get_user_avatar(user_id):
    """Возвращает путь к аватарке пользователя или None"""
    upload_folder = app.config['UPLOAD_FOLDER']
    for ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
        filename = f"avatar_{user_id}.{ext}"
        filepath = os.path.join(upload_folder, filename)
        if os.path.exists(filepath):
            return f"/static/uploads/avatars/{filename}"
    return None

def notify_user(user_id, notif_type, title, message, link="/"):
    """Универсальная функция отправки уведомления (внутреннее + push)"""
    try:
        add_notification(user_id, notif_type, title, message, link)
        asyncio.run(send_push_notification(user_id, title, message, link))
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")

def notify_admins_app(title, message, link="/admin/panel"):
    """Отправляет уведомление всем администраторам"""
    try:
        admin_ids = get_admin_ids(db)
        for admin_id in admin_ids:
            add_notification(admin_id, "admin", title, message, link)
            asyncio.run(send_push_notification(admin_id, title, message, link))
    except Exception as e:
        logger.error(f"Ошибка уведомления админов: {e}")

# ============================================================
# КЛАСС ПОЛЬЗОВАТЕЛЯ
# ============================================================
class User(UserMixin):
    def __init__(self, user_id, nickname, is_admin=False, phone=""):
        self.id = int(user_id)
        self.user_id = int(user_id)
        self.nickname = str(nickname) if nickname else "Пользователь"
        self.is_admin = bool(is_admin)
        self.phone = str(phone)

    def __repr__(self):
        return f'<User {self.id} {self.nickname}>'

# ============================================================
# КЭШ ПОЛЬЗОВАТЕЛЯ (для снижения нагрузки на Google Sheets)
# ============================================================
user_cache = {}
CACHE_TTL = 60  # секунд

@login_manager.user_loader
def load_user(user_id):
    """Загружает пользователя по ID с кэшированием"""
    try:
        user_id_str = str(user_id)
        now = datetime.now().timestamp()

        # Проверяем кэш
        if user_id_str in user_cache:
            cached_user, timestamp = user_cache[user_id_str]
            if now - timestamp < CACHE_TTL:
                return cached_user

        # Запрашиваем из Google Sheets
        users_ws = db.get_or_create_users_sheet()
        record = db.find_user_by_id(user_id, users_ws)

        if record:
            nickname = record.get(db.HEADER_NICKNAME) or "Пользователь"
            is_admin = str(record.get(db.HEADER_ADMIN, "")) == "Да"
            phone = record.get(db.HEADER_PHONE, "")

            user = User(
                user_id=int(user_id),
                nickname=str(nickname),
                is_admin=bool(is_admin),
                phone=str(phone)
            )
            user.avatar_url = get_user_avatar(int(user_id))

            # Сохраняем в кэш
            user_cache[user_id_str] = (user, now)
            return user
        else:
            if user_id_str in user_cache:
                del user_cache[user_id_str]
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка в load_user: {e}")
        return None

# ============================================================
# ОСНОВНЫЕ МАРШРУТЫ
# ============================================================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        phone = request.form.get('phone')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        if not all([nickname, phone, password]):
            flash('Заполните все поля', 'error')
            return redirect(url_for('register'))
        if password != password_confirm:
            flash('Пароли не совпадают', 'error')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('Пароль должен быть не менее 6 символов', 'error')
            return redirect(url_for('register'))

        phone_digits = re.sub(r'\D', '', phone)
        if not (10 <= len(phone_digits) <= 15):
            flash('Неверный формат телефона', 'error')
            return redirect(url_for('register'))

        auth_check = db._load_auth_data()
        if phone_digits in auth_check:
            flash('Пользователь с таким телефоном уже зарегистрирован', 'error')
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password)
        result = db.register_user(nickname, phone, password_hash)

        if result['success']:
            # Уведомление админам о новой регистрации
            notify_admins_app(
                " Новая регистрация",
                f"Пользователь {nickname} зарегистрировался в системе",
                "/admin/users-list"
            )
            flash('Регистрация успешна! Теперь войдите в систему.', 'success')
            return redirect(url_for('login'))
        else:
            flash(f'Ошибка регистрации: {result.get("error")}', 'error')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')

        logger.info(f"🔐 Попытка входа: телефон={phone}")

        if not phone or not password:
            flash('Заполните все поля', 'error')
            return redirect(url_for('login'))

        auth_user = db.verify_auth_user(phone, password)
        if not auth_user:
            logger.warning(f"❌ Неверный телефон или пароль: {phone}")
            flash('Неверный телефон или пароль', 'error')
            return redirect(url_for('login'))

        user_id = auth_user['user_id']
        users_ws = db.get_or_create_users_sheet()
        record = db.find_user_by_id(user_id, users_ws)

        if not record:
            logger.error(f" Профиль не найден в Google Sheets для ID={user_id}")
            flash('Ошибка: профиль пользователя не найден', 'error')
            return redirect(url_for('login'))

        nickname = record.get(db.HEADER_NICKNAME) or auth_user.get('nickname', 'Пользователь')
        is_admin = str(record.get(db.HEADER_ADMIN, "")) == "Да"
        phone_from_sheet = record.get(db.HEADER_PHONE, phone)

        logger.info(f"✅ Вход успешен: {nickname} (ID: {user_id}, Админ: {is_admin})")

        user = User(
            user_id=int(user_id),
            nickname=str(nickname),
            is_admin=bool(is_admin),
            phone=str(phone_from_sheet)
        )
        user.avatar_url = get_user_avatar(int(user_id))

        login_user(user, remember=True)

        # Очищаем кэш для этого пользователя
        user_cache.pop(str(user_id), None)

        flash(f'Добро пожаловать, {user.nickname}!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    users_ws = db.get_or_create_users_sheet()
    record = db.find_user_by_id(current_user.id, users_ws)

    if not record:
        flash('Профиль не найден', 'error')
        return redirect(url_for('logout'))

    tracerdb_id = record.get(db.HEADER_TOP_RACER_ID) or current_user.id
    topcoins = db.get_topcoins(current_user.id)
    bonus_minutes = db.get_bonus_minutes(current_user.id)
    bonus_expiry = record.get(db.HEADER_BONUS_EXPIRY, "")
    avatar_url = get_user_avatar(current_user.id)

    return render_template('dashboard.html',
                         tracerdb_id=tracerdb_id,
                         nickname=current_user.nickname,
                         topcoins=topcoins,
                         bonus_minutes=bonus_minutes,
                         bonus_expiry=bonus_expiry,
                         avatar_url=avatar_url)

@app.route('/stats')
@login_required
def stats():
    users_ws = db.get_or_create_users_sheet()
    record = db.find_user_by_id(current_user.id, users_ws)

    if not record:
        flash('Профиль не найден', 'error')
        return redirect(url_for('dashboard'))

    tracerdb_id = record.get(db.HEADER_TOP_RACER_ID) or current_user.id
    level = int(record.get(db.HEADER_LEVEL, 1) or 1)
    total_visits = int(record.get(db.HEADER_VISITS, 0) or 0)
    topcoins = db.get_topcoins(current_user.id)
    bonus_minutes = db.get_bonus_minutes(current_user.id)
    bonus_expiry = record.get(db.HEADER_BONUS_EXPIRY, "")
    progress = db.calculate_progress(total_visits)

    return render_template('stats.html',
                         tracerdb_id=tracerdb_id,
                         nickname=current_user.nickname,
                         level=level,
                         total_visits=total_visits,
                         topcoins=topcoins,
                         bonus_minutes=bonus_minutes,
                         bonus_expiry=bonus_expiry,
                         progress=progress)

@app.route('/history')
@login_required
def history():
    history_records = db.get_user_history(current_user.id)
    recent_history = history_records[-15:][::-1] if history_records else []
    return render_template('history.html',
                         nickname=current_user.nickname,
                         history=recent_history,
                         total=len(history_records))

@app.route('/qr')
@login_required
def qr_code():
    tracerdb_id = current_user.id
    return render_template('qr_code.html',
                         tracerdb_id=tracerdb_id,
                         nickname=current_user.nickname)

@app.route('/qr_image/<int:tracerdb_id>')
@login_required
def qr_image(tracerdb_id):
    """Генерация изображения QR-кода"""
    try:
        qr_data = f"https://t.me/toprace_data_bot?start=scan_{tracerdb_id}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return send_file(buf, mimetype='image/png')
    except Exception as e:
        logger.error(f"Ошибка генерации QR: {e}")
        return "Ошибка генерации QR-кода", 500

@app.route('/tournaments')
@login_required
def tournaments():
    return render_template('tournaments.html', tournaments=db.TOURNAMENT_INFO_TEXT)

@app.route('/tournament/register/<tournament_key>', methods=['GET', 'POST'])
@login_required
def tournament_register(tournament_key):
    if tournament_key not in db.TOURNAMENT_INFO_TEXT:
        flash('Турнир не найден', 'error')
        return redirect(url_for('tournaments'))

    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        branch_key = request.form.get('branch')

        if not all([name, phone, branch_key]):
            flash('Заполните все поля', 'error')
            return redirect(url_for('tournament_register', tournament_key=tournament_key))

        result = db.save_tournament_registration(
            tournament_key, name, phone, branch_key,
            current_user.id, current_user.nickname
        )

        if result['success']:
            db.add_bonus_minutes(current_user.id, db.config.TOURNAMENT_BONUS_MINUTES)
            db.update_topcoins(current_user.id, db.config.TOURNAMENT_BONUS_COINS, "add")

            # Уведомление админам
            tournament_name = db.TOURNAMENT_INFO_TEXT[tournament_key]['name']
            notify_admins_app(
                "🏆 Регистрация на турнир",
                f"{current_user.nickname} зарегистрировался на турнир {tournament_name}",
                "/admin/panel"
            )

            flash('Регистрация успешна! Бонусы начислены.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash(f'Ошибка регистрации: {result.get("error")}', 'error')

    tournament = db.TOURNAMENT_INFO_TEXT[tournament_key]
    return render_template('tournament_register.html',
                         tournament=tournament,
                         branches=db.BRANCHES,
                         tournament_key=tournament_key)

@app.route('/records')
@login_required
def records():
    return render_template('records.html', tracks=db.GT_TRACKS)

@app.route('/records/<track_key>')
@login_required
def track_records(track_key):
    if track_key not in db.GT_TRACKS:
        flash('Трасса не найдена', 'error')
        return redirect(url_for('records'))
    records = db.get_track_records(track_key, limit=10)
    track = db.GT_TRACKS[track_key]
    return render_template('records.html',
                         track=track,
                         records=records,
                         tracks=db.GT_TRACKS,
                         current_track=track_key)

@app.route('/booking', methods=['GET', 'POST'])
@login_required
def booking():
    if request.method == 'POST':
        booking_text = request.form.get('text')
        phone = request.form.get('phone')
        branch_key = request.form.get('branch')

        if not booking_text or len(booking_text.strip()) < 10:
            flash('Заявка слишком короткая', 'error')
            return redirect(url_for('booking'))
        if not branch_key or branch_key not in db.BRANCHES:
            flash('Выберите филиал', 'error')
            return redirect(url_for('booking'))

        branch = db.BRANCHES[branch_key]

        # Уведомление админам
        notify_admins_app(
            "📝 Новая заявка на посещение",
            f"{current_user.nickname} хочет записаться в филиал {branch['name']}",
            "/admin/panel"
        )

        flash('✅ Заявка отправлена! Администратор уведомлён.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('booking.html',
                         nickname=current_user.nickname,
                         branches=db.BRANCHES)

# ============================================================
# ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ
# ============================================================

@app.route('/profile')
@login_required
def view_profile():
    """Просмотр своего профиля"""
    users_ws = db.get_or_create_users_sheet()
    record = db.find_user_by_id(current_user.id, users_ws)

    if not record:
        flash('Профиль не найден', 'error')
        return redirect(url_for('logout'))

    tracerdb_id = record.get(db.HEADER_TOP_RACER_ID) or current_user.id
    nickname = record.get(db.HEADER_NICKNAME, 'Пользователь')
    phone = record.get(db.HEADER_PHONE, 'Не указан')
    level = int(record.get(db.HEADER_LEVEL, 1) or 1)
    visits = int(record.get(db.HEADER_VISITS, 0) or 0)
    is_admin = str(record.get(db.HEADER_ADMIN, '')).strip() == "Да"
    reg_date = record.get(db.HEADER_REG_DATE, '')
    last_visit = record.get(db.HEADER_LAST_VISIT, '')
    topcoins = db.get_topcoins(current_user.id)
    bonus_minutes = db.get_bonus_minutes(current_user.id)
    bonus_expiry = record.get(db.HEADER_BONUS_EXPIRY, '')
    avatar_url = get_user_avatar(current_user.id)

    # Количество друзей
    try:
        from database import get_user_friends_count
        friends_count = get_user_friends_count(db, current_user.id)
    except:
        friends_count = 0

    return render_template('view_profile.html',
                         tracerdb_id=tracerdb_id,
                         nickname=nickname,
                         phone=phone,
                         level=level,
                         visits=visits,
                         is_admin=is_admin,
                         reg_date=reg_date,
                         last_visit=last_visit,
                         topcoins=topcoins,
                         bonus_minutes=bonus_minutes,
                         bonus_expiry=bonus_expiry,
                         avatar_url=avatar_url,
                         friends_count=friends_count)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Редактирование профиля"""
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        phone = request.form.get('phone')

        if not nickname or len(nickname.strip()) < 2:
            flash('Никнейм должен содержать минимум 2 символа', 'error')
            return redirect(url_for('edit_profile'))

        phone_digits = re.sub(r'\D', '', phone)
        if not (10 <= len(phone_digits) <= 15):
            flash('Неверный формат телефона', 'error')
            return redirect(url_for('edit_profile'))

        if phone_digits.startswith('8') and len(phone_digits) == 11:
            phone_digits = '7' + phone_digits[1:]
        formatted_phone = f"+{phone_digits[0]} ({phone_digits[1:4]}) {phone_digits[4:7]}-{phone_digits[7:9]}-{phone_digits[9:]}"

        users_ws = db.get_or_create_users_sheet()
        all_data = users_ws.get_all_values()

        if all_data and len(all_data) > 1:
            headers = all_data[0]
            user_row = None
            for i, row in enumerate(all_data[1:], start=2):
                if row and str(row[0]).strip() == str(current_user.id).strip():
                    user_row = i
                    break

            if user_row:
                nickname_col = None
                phone_col = None
                for i, header in enumerate(headers):
                    if 'ник' in str(header).lower():
                        nickname_col = i + 1
                    if 'телефон' in str(header).lower():
                        phone_col = i + 1

                if nickname_col:
                    col_letter = chr(64 + nickname_col) if nickname_col <= 26 else 'Z'
                    users_ws.update(f'{col_letter}{user_row}', [[nickname.strip()]])
                if phone_col:
                    col_letter = chr(64 + phone_col) if phone_col <= 26 else 'Z'
                    users_ws.update(f'{col_letter}{user_row}', [[formatted_phone]])

                db.update_auth_nickname(formatted_phone, nickname.strip())

                # Очищаем кэш
                user_cache.pop(str(current_user.id), None)

                flash('Профиль успешно обновлен!', 'success')
                return redirect(url_for('view_profile'))
            else:
                flash('Ошибка: пользователь не найден', 'error')

    users_ws = db.get_or_create_users_sheet()
    record = db.find_user_by_id(current_user.id, users_ws)
    current_phone = record.get(db.HEADER_PHONE, '') if record else ''
    current_nickname = record.get(db.HEADER_NICKNAME, '') if record else ''

    return render_template('edit_profile.html',
                         nickname=current_nickname,
                         phone=current_phone)

@app.route('/profile/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Смена пароля"""
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        users_ws = db.get_or_create_users_sheet()
        record = db.find_user_by_id(current_user.id, users_ws)

        if not record:
            flash('Ошибка: пользователь не найден', 'error')
            return redirect(url_for('change_password'))

        phone = record.get(db.HEADER_PHONE, '')
        if not db.verify_auth_user(phone, old_password):
            flash('Неверный текущий пароль', 'error')
            return redirect(url_for('change_password'))

        if new_password != confirm_password:
            flash('Новые пароли не совпадают', 'error')
            return redirect(url_for('change_password'))

        if len(new_password) < 6:
            flash('Пароль должен быть не менее 6 символов', 'error')
            return redirect(url_for('change_password'))

        password_hash = generate_password_hash(new_password)
        db.save_user_password(phone, password_hash, current_user.id, current_user.id, current_user.nickname)

        flash('Пароль успешно изменен!', 'success')
        return redirect(url_for('view_profile'))

    return render_template('change_password.html')

@app.route('/profile/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    """Загрузка фото профиля"""
    try:
        if 'avatar' not in request.files:
            flash('Файл не выбран', 'error')
            return redirect(url_for('edit_profile'))

        file = request.files['avatar']
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return redirect(url_for('edit_profile'))

        if not allowed_file(file.filename):
            flash('Недопустимый формат. Используйте PNG, JPG, GIF или WEBP', 'error')
            return redirect(url_for('edit_profile'))

        upload_folder = app.config['UPLOAD_FOLDER']
        for ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
            old_file = os.path.join(upload_folder, f"avatar_{current_user.id}.{ext}")
            if os.path.exists(old_file):
                os.remove(old_file)
            old_thumb = os.path.join(upload_folder, f"avatar_{current_user.id}_thumb.{ext}")
            if os.path.exists(old_thumb):
                os.remove(old_thumb)

        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        new_filename = f"avatar_{current_user.id}.{ext}"
        filepath = os.path.join(upload_folder, new_filename)
        file.save(filepath)
        logger.info(f"✅ Аватар сохранён: {filepath}")

        try:
            img = Image.open(filepath)
            img.thumbnail((200, 200), Image.LANCZOS)
            thumb_filename = f"avatar_{current_user.id}_thumb.{ext}"
            thumb_path = os.path.join(upload_folder, thumb_filename)
            img.save(thumb_path, quality=85)
        except Exception as e:
            logger.error(f"Ошибка создания миниатюры: {e}")

        flash('Аватар успешно обновлён!', 'success')
        return redirect(url_for('edit_profile'))
    except Exception as e:
        logger.error(f"Ошибка загрузки аватара: {e}")
        flash('Произошла ошибка при загрузке', 'error')
        return redirect(url_for('edit_profile'))

@app.route('/profile/remove-avatar', methods=['POST'])
@login_required
def remove_avatar():
    """Удаление фото профиля"""
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        removed = False
        for ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
            file_path = os.path.join(upload_folder, f"avatar_{current_user.id}.{ext}")
            if os.path.exists(file_path):
                os.remove(file_path)
                removed = True
            thumb_path = os.path.join(upload_folder, f"avatar_{current_user.id}_thumb.{ext}")
            if os.path.exists(thumb_path):
                os.remove(thumb_path)

        if removed:
            flash('Аватар удален', 'success')
        else:
            flash('Аватар не найден', 'info')
        return redirect(url_for('edit_profile'))
    except Exception as e:
        logger.error(f"Ошибка при удалении аватара: {e}")
        flash('Ошибка при удалении', 'error')
        return redirect(url_for('edit_profile'))

# ============================================================
# ДРУЗЬЯ
# ============================================================

@app.route('/friends/search')
@login_required
def friends_search():
    """Поиск пользователей"""
    query = request.args.get('q', '')
    users = []

    if query and len(query) >= 2:
        users_ws = db.get_or_create_users_sheet()
        all_data = users_ws.get_all_values()

        if all_data and len(all_data) > 1:
            headers = all_data[0]
            for row in all_data[1:]:
                if not row or len(row) < 2:
                    continue
                nickname = row[1] if len(row) > 1 else ''
                user_id = row[0] if len(row) > 0 else ''

                if (query.lower() in str(nickname).lower() and
                    str(user_id) != str(current_user.id)):
                    try:
                        if not db.is_friend(current_user.id, int(user_id)):
                            users.append({
                                'id': user_id,
                                'nickname': nickname,
                                'avatar_url': get_user_avatar(int(user_id))
                            })
                    except:
                        pass

    return render_template('friends_search.html', query=query, users=users)

@app.route('/friends/add/<int:user_id>', methods=['POST'])
@login_required
def add_friend(user_id):
    """Добавить в друзья"""
    if db.add_friend(current_user.id, user_id):
        # Уведомление другу
        notify_user(
            user_id,
            "friend",
            "👥 Новый друг",
            f"Пользователь {current_user.nickname} добавил вас в друзья!",
            "/friends"
        )
        flash('Пользователь добавлен в друзья!', 'success')
    else:
        flash('Ошибка при добавлении в друзья', 'error')
    return redirect(url_for('friends_search'))

@app.route('/friends/remove/<int:user_id>', methods=['POST'])
@login_required
def remove_friend(user_id):
    """Удалить из друзей"""
    if db.remove_friend(current_user.id, user_id):
        flash('Пользователь удален из друзей', 'success')
    else:
        flash('Ошибка при удалении из друзей', 'error')
    return redirect(url_for('my_friends'))

@app.route('/friends')
@login_required
def my_friends():
    """Мои друзья"""
    friends = db.get_user_friends(current_user.id)
    return render_template('my_friends.html', friends=friends)

@app.route('/user/<int:user_id>')
@login_required
def view_user_profile(user_id):
    """Просмотр профиля другого пользователя"""
    users_ws = db.get_or_create_users_sheet()
    record = db.find_user_by_id(user_id, users_ws)

    if not record:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('dashboard'))

    tracerdb_id = record.get(db.HEADER_TOP_RACER_ID) or user_id
    nickname = record.get(db.HEADER_NICKNAME, 'Пользователь')
    phone = record.get(db.HEADER_PHONE, 'Не указан')
    level = int(record.get(db.HEADER_LEVEL, 1) or 1)
    visits = int(record.get(db.HEADER_VISITS, 0) or 0)
    is_admin = str(record.get(db.HEADER_ADMIN, '')).strip() == "Да"
    reg_date = record.get(db.HEADER_REG_DATE, '')
    last_visit = record.get(db.HEADER_LAST_VISIT, '')
    topcoins = db.get_topcoins(user_id)
    bonus_minutes = db.get_bonus_minutes(user_id)
    bonus_expiry = record.get(db.HEADER_BONUS_EXPIRY, '')
    avatar_url = get_user_avatar(user_id)
    is_friend = db.is_friend(current_user.id, user_id)

    return render_template('view_user_profile.html',
                         user_id=user_id,
                         tracerdb_id=tracerdb_id,
                         nickname=nickname,
                         phone=phone,
                         level=level,
                         visits=visits,
                         is_admin=is_admin,
                         reg_date=reg_date,
                         last_visit=last_visit,
                         topcoins=topcoins,
                         bonus_minutes=bonus_minutes,
                         bonus_expiry=bonus_expiry,
                         avatar_url=avatar_url,
                         is_friend=is_friend)

# ============================================================
# ЧАТЫ
# ============================================================

@app.route('/chat')
@login_required
def chat_list():
    """Список диалогов"""
    try:
        update_last_seen(current_user.id)
        save_user(current_user.id, current_user.nickname)
        conversations = get_conversations(current_user.id)

        chats = []
        for conv in conversations:
            friend_id = conv['friend_id']
            nickname = get_user_nickname(friend_id) or f"Пользователь #{friend_id}"
            online = is_user_online(friend_id)

            chats.append({
                'friend_id': friend_id,
                'nickname': nickname,
                'last_message': conv['last_message'],
                'last_message_time': conv['last_message_time'],
                'unread_count': conv['unread_count'],
                'online': online
            })

        return render_template('chat_list.html', chats=chats)
    except Exception as e:
        logger.error(f"Ошибка chat_list: {e}")
        return render_template('chat_list.html', chats=[])

@app.route('/chat/<int:friend_id>')
@login_required
def chat_room(friend_id):
    """Комната чата"""
    try:
        update_last_seen(current_user.id)
        save_user(current_user.id, current_user.nickname)
        mark_chat_read(current_user.id, friend_id)

        friend_nickname = get_user_nickname(friend_id) or f"Пользователь #{friend_id}"
        friend_online = is_user_online(friend_id)
        messages = get_messages(current_user.id, friend_id, limit=200)

        return render_template('chat_room.html',
                             friend_id=friend_id,
                             friend_nickname=friend_nickname,
                             friend_online=friend_online,
                             messages=messages)
    except Exception as e:
        logger.error(f"Ошибка chat_room: {e}")
        flash('Ошибка загрузки чата', 'error')
        return redirect(url_for('chat_list'))

@app.route('/chat/send/<int:friend_id>', methods=['POST'])
@login_required
def chat_send(friend_id):
    """Отправка сообщения"""
    message = request.form.get('message', '').strip()

    if not message:
        flash('Сообщение не может быть пустым', 'error')
        return redirect(url_for('chat_room', friend_id=friend_id))

    if len(message) > 1000:
        flash('Сообщение слишком длинное (макс. 1000 символов)', 'error')
        return redirect(url_for('chat_room', friend_id=friend_id))

    send_message(current_user.id, friend_id, message)
    update_last_seen(current_user.id)

    # Уведомление получателю
    notify_user(
        friend_id,
        "message",
        f"💬 Новое сообщение от {current_user.nickname}",
        "Нажмите, чтобы открыть чат",
        f"/chat/{current_user.id}"
    )

    return redirect(url_for('chat_room', friend_id=friend_id))

@app.route('/chat/api/messages/<int:friend_id>')
@login_required
def chat_api_messages(friend_id):
    """API для получения новых сообщений"""
    try:
        update_last_seen(current_user.id)
        mark_chat_read(current_user.id, friend_id)
        messages = get_messages(current_user.id, friend_id, limit=50)

        return jsonify({
            'messages': [
                {
                    'id': m['id'],
                    'sender_id': m['sender_id'],
                    'message': m['message'],
                    'created_at': m['created_at'],
                    'is_mine': m['sender_id'] == current_user.id
                }
                for m in messages
            ],
            'friend_online': is_user_online(friend_id)
        })
    except Exception as e:
        logger.error(f"Ошибка API сообщений: {e}")
        return jsonify({'messages': [], 'friend_online': False})

@app.route('/chat/api/unread-count')
@login_required
def chat_api_unread_count():
    """API для получения количества непрочитанных сообщений"""
    try:
        count = get_chat_unread(current_user.id)
        return jsonify({'count': count})
    except Exception as e:
        logger.error(f"Ошибка API unread: {e}")
        return jsonify({'count': 0})

# ============================================================
# УВЕДОМЛЕНИЯ (API)
# ============================================================

@app.route('/api/notifications/count')
@login_required
def api_notif_count():
    try:
        count = get_notif_unread(current_user.id)
        return jsonify({"count": count})
    except Exception as e:
        logger.error(f"Ошибка API notif count: {e}")
        return jsonify({"count": 0})

@app.route('/api/notifications')
@login_required
def api_notifications():
    try:
        notifs = get_recent_notifications(current_user.id, limit=15)
        mark_notif_read(current_user.id)
        return jsonify({"notifications": notifs})
    except Exception as e:
        logger.error(f"Ошибка API notifs: {e}")
        return jsonify({"notifications": []})

# ============================================================
# АДМИНСКИЕ МАРШРУТЫ
# ============================================================

@app.route('/admin/panel')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))

    users_ws = db.get_or_create_users_sheet()
    all_data = users_ws.get_all_values()
    total_users = len(all_data) - 1 if all_data and len(all_data) > 1 else 0
    total_visits = sum(int(row[5]) for row in all_data[1:] if len(row) > 5 and str(row[5]).isdigit())

    admin_count = 0
    for row in all_data[1:]:
        if len(row) > 8 and str(row[8]).strip() == "Да":
            admin_count += 1

    return render_template('admin/panel.html',
                         total_users=total_users,
                         total_visits=total_visits,
                         admin_count=admin_count)


@app.route('/admin/users-list')
@login_required
def admin_users_list():
    """Список всех пользователей"""
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))

    users_ws = db.get_or_create_users_sheet()
    all_data = users_ws.get_all_values()
    users = []

    if all_data and len(all_data) > 1:
        headers = all_data[0]
        col_indices = {}
        for i, header in enumerate(headers):
            header_lower = str(header).lower().strip()
            if 'топрас' in header_lower or 'topracer' in header_lower or header_lower == 'id':
                col_indices['id'] = i
            elif 'ник' in header_lower or 'nickname' in header_lower:
                col_indices['nickname'] = i
            elif 'телефон' in header_lower or 'phone' in header_lower:
                col_indices['phone'] = i
            elif 'уровен' in header_lower or 'level' in header_lower:
                col_indices['level'] = i
            elif 'посещ' in header_lower or 'visit' in header_lower:
                col_indices['visits'] = i
            elif 'topcoin' in header_lower:
                col_indices['topcoins'] = i
            elif 'админ' in header_lower or 'admin' in header_lower:
                col_indices['admin'] = i
            elif 'telegram' in header_lower:
                col_indices['telegram_id'] = i
            elif 'зарег' in header_lower or 'registered' in header_lower:
                col_indices['registered_by'] = i

        for row in all_data[1:]:
            if not row or len(row) < 2:
                continue

            user_id = row[col_indices.get('id', 0)] if col_indices.get('id', 0) < len(row) else None
            if not user_id:
                continue

            def safe_get(key, default=''):
                idx = col_indices.get(key)
                if idx is not None and idx < len(row):
                    val = row[idx]
                    return val if val else default
                return default

            try:
                topcoins = int(str(safe_get('topcoins', '0 TC')).replace('TC', '').strip() or 0)
            except:
                topcoins = 0
            try:
                visits = int(safe_get('visits', 0) or 0)
            except:
                visits = 0
            try:
                level = int(safe_get('level', 1) or 1)
            except:
                level = 1

            # Определяем кто зарегистрировал
            registered_by = safe_get('registered_by', 'self')
            if registered_by == 'self':
                registered_by_text = 'Самостоятельно'
            else:
                # Получаем никнейм админа
                admin_record = db.find_user_by_id(int(registered_by), users_ws)
                registered_by_text = admin_record.get(db.HEADER_NICKNAME,
                                                      'Неизвестно') if admin_record else 'Неизвестно'

            users.append({
                'id': str(user_id).strip(),
                'nickname': safe_get('nickname', 'Неизвестно'),
                'phone': safe_get('phone', 'Не указан'),
                'level': level,
                'visits': visits,
                'topcoins': topcoins,
                'is_admin': str(safe_get('admin', 'Нет')).strip() == "Да",
                'telegram_id': safe_get('telegram_id', ''),
                'registered_by': registered_by_text
            })

    return render_template('admin/users_list.html', users=users)

@app.route('/admin/user/<int:user_id>')
@login_required
def admin_user_detail(user_id):
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))

    users_ws = db.get_or_create_users_sheet()
    record = db.find_user_by_id(user_id, users_ws)

    if not record:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('admin_users_list'))

    tracerdb_id = record.get(db.HEADER_TOP_RACER_ID) or user_id
    nickname = record.get(db.HEADER_NICKNAME, 'Неизвестно')
    phone = record.get(db.HEADER_PHONE, 'Не указан')
    level = int(record.get(db.HEADER_LEVEL, 1) or 1)
    visits = int(record.get(db.HEADER_VISITS, 0) or 0)
    is_admin = str(record.get(db.HEADER_ADMIN, '')).strip() == "Да"
    telegram_id = record.get(db.HEADER_TELEGRAM_ID, '')
    reg_date = record.get(db.HEADER_REG_DATE, '')
    last_visit = record.get(db.HEADER_LAST_VISIT, '')
    topcoins = db.get_topcoins(user_id)
    bonus_minutes = db.get_bonus_minutes(user_id)
    bonus_expiry = record.get(db.HEADER_BONUS_EXPIRY, '')
    history = db.get_user_history(user_id)
    recent_history = history[-10:][::-1] if history else []

    return render_template('admin/user_detail.html',
                         user_id=user_id,
                         tracerdb_id=tracerdb_id,
                         nickname=nickname,
                         phone=phone,
                         level=level,
                         visits=visits,
                         is_admin=is_admin,
                         telegram_id=telegram_id,
                         reg_date=reg_date,
                         last_visit=last_visit,
                         topcoins=topcoins,
                         bonus_minutes=bonus_minutes,
                         bonus_expiry=bonus_expiry,
                         history=recent_history)

@app.route('/admin/user/<int:user_id>/add-coins', methods=['POST'])
@login_required
def admin_add_coins(user_id):
    if not current_user.is_admin:
        return jsonify({"error": "Доступ запрещен"}), 403

    amount = request.form.get('amount', type=int)
    if not amount or amount <= 0:
        flash('Введите корректную сумму', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    new_balance = db.update_topcoins(user_id, amount, "add")

    if new_balance is not None:
        # Уведомление пользователю
        notify_user(
            user_id,
            "coins",
            "💰 Начисление TopCoins",
            f"Администратор {current_user.nickname} начислил вам {amount} TC. Новый баланс: {new_balance} TC",
            "/dashboard"
        )
        flash(f'✅ Начислено {amount} TC. Новый баланс: {new_balance} TC', 'success')
    else:
        flash('❌ Ошибка при начислении', 'error')

    return redirect(url_for('admin_user_detail', user_id=user_id))

@app.route('/admin/user/<int:user_id>/spend-coins', methods=['POST'])
@login_required
def admin_spend_coins(user_id):
    if not current_user.is_admin:
        return jsonify({"error": "Доступ запрещен"}), 403

    amount = request.form.get('amount', type=int)
    if not amount or amount <= 0:
        flash('Введите корректную сумму', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    current_balance = db.get_topcoins(user_id)
    if current_balance < amount:
        flash(f'❌ Недостаточно TopCoins! Баланс: {current_balance} TC', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    new_balance = db.update_topcoins(user_id, amount, "subtract")

    if new_balance is not None:
        notify_user(
            user_id,
            "coins",
            "💸 Списание TopCoins",
            f"Администратор {current_user.nickname} списал {amount} TC. Новый баланс: {new_balance} TC",
            "/dashboard"
        )
        flash(f'✅ Списано {amount} TC. Новый баланс: {new_balance} TC', 'success')
    else:
        flash('❌ Ошибка при списании', 'error')

    return redirect(url_for('admin_user_detail', user_id=user_id))

@app.route('/admin/user/<int:user_id>/add-minutes', methods=['POST'])
@login_required
def admin_add_minutes(user_id):
    if not current_user.is_admin:
        return jsonify({"error": "Доступ запрещен"}), 403

    minutes = request.form.get('minutes', type=int)
    if not minutes or minutes <= 0:
        flash('Введите корректное количество минут', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    new_balance, expiry = db.add_bonus_minutes(user_id, minutes)

    if new_balance is not None:
        notify_user(
            user_id,
            "minutes",
            "⏰ Начисление бонусных минут",
            f"Администратор {current_user.nickname} начислил вам {minutes} мин. Новый баланс: {new_balance} мин (до {expiry})",
            "/dashboard"
        )
        flash(f'✅ Начислено {minutes} мин. Новый баланс: {new_balance} мин (до {expiry})', 'success')
    else:
        flash(' Ошибка при начислении', 'error')

    return redirect(url_for('admin_user_detail', user_id=user_id))

@app.route('/admin/user/<int:user_id>/spend-minutes', methods=['POST'])
@login_required
def admin_spend_minutes(user_id):
    if not current_user.is_admin:
        return jsonify({"error": "Доступ запрещен"}), 403

    minutes = request.form.get('minutes', type=int)
    if not minutes or minutes <= 0:
        flash('Введите корректное количество минут', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    current_minutes = db.get_bonus_minutes(user_id)
    if current_minutes < minutes:
        flash(f' Недостаточно минут! Баланс: {current_minutes} мин', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))

    new_balance = db.use_bonus_minutes(user_id, minutes)

    if new_balance is not None:
        notify_user(
            user_id,
            "minutes",
            "⏱️ Списание бонусных минут",
            f"Администратор {current_user.nickname} списал {minutes} мин. Новый баланс: {new_balance} мин",
            "/dashboard"
        )
        flash(f'✅ Списано {minutes} мин. Новый баланс: {new_balance} мин', 'success')
    else:
        flash('❌ Ошибка при списании', 'error')

    return redirect(url_for('admin_user_detail', user_id=user_id))

@app.route('/admin/create-admin', methods=['GET', 'POST'])
@login_required
def admin_create_admin():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nickname = request.form.get('nickname')
        phone = request.form.get('phone')
        password = request.form.get('password')

        if not all([nickname, phone, password]):
            flash('Заполните все обязательные поля', 'error')
            return redirect(url_for('admin_create_admin'))

        users_ws = db.get_or_create_users_sheet()
        existing_user = db.find_user_by_phone(phone, users_ws)
        if existing_user:
            flash('Пользователь с таким телефоном уже существует', 'error')
            return redirect(url_for('admin_create_admin'))

        password_hash = generate_password_hash(password)
        tracerdb_id = db.get_next_tracerdb_id(users_ws)
        reg_date = datetime.now().strftime("%d/%m/%Y %H:%M")
        expiry_date = (datetime.now() + timedelta(days=db.BONUS_VALIDITY_DAYS)).strftime("%d.%m.%Y")

        users_ws.append_row([
            tracerdb_id, nickname, "", reg_date, 1, 0,
            tracerdb_id, "", "Да", phone, "0 TC", "0 мин", expiry_date
        ])

        db.save_user_password(phone, password_hash, tracerdb_id, tracerdb_id, nickname)
        flash(f'Администратор {nickname} успешно создан!', 'success')
        return redirect(url_for('admin_panel'))

    return render_template('admin/create_admin.html')

@app.route('/admin/promote', methods=['GET', 'POST'])
@login_required
def admin_promote_user():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        identifier = request.form.get('identifier')
        if not identifier:
            flash('Введите ID или телефон пользователя', 'error')
            return redirect(url_for('admin_promote_user'))

        users_ws = db.get_or_create_users_sheet()
        user_record = db.find_user_by_phone(identifier, users_ws)

        if not user_record:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin_promote_user'))

        all_data = users_ws.get_all_values()
        user_row = None
        for i, row in enumerate(all_data[1:], start=2):
            if row and str(row[0]).strip() == str(user_record.get(db.HEADER_TOP_RACER_ID)).strip():
                user_row = i
                break

        if user_row:
            users_ws.update(f'I{user_row}', [['Да']])
            nickname = user_record.get(db.HEADER_NICKNAME, 'Неизвестно')
            flash(f'Пользователь {nickname} назначен администратором!', 'success')
            return redirect(url_for('admin_panel'))

        flash('Ошибка при обновлении', 'error')

    return render_template('admin/promote_user.html')

@app.route('/admin/scan', methods=['GET', 'POST'])
@login_required
def admin_scan():
    if not current_user.is_admin:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        identifier = request.form.get('identifier')
        action = request.form.get('action')
        users_ws = db.get_or_create_users_sheet()
        user_record = db.find_user_by_phone(identifier, users_ws)

        if not user_record:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin_scan'))

        tracerdb_id = user_record.get(db.HEADER_TOP_RACER_ID)

        if action == 'visit':
            result = db.record_visit(tracerdb_id, current_user.id, current_user.nickname, is_admin=True)
            if result['success']:
                flash(f'Посещение засчитано! +{result["topcoins_earned"]} TC', 'success')
            else:
                flash(f'Ошибка: {result.get("error")}', 'error')

        return redirect(url_for('admin_scan'))

    return render_template('admin/scan.html')

@app.route('/admin/camera-scan')
@login_required
def admin_camera_scan():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))
    return render_template('admin/camera_scan.html')

@app.route('/admin/analytics')
@login_required
def admin_analytics():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))
    try:
        from analytics import get_full_analytics
        analytics = get_full_analytics(db)
        return render_template('admin/analytics.html', analytics=analytics)
    except Exception as e:
        logger.error(f"Ошибка аналитики: {e}")
        flash('Ошибка загрузки аналитики', 'error')
        return redirect(url_for('admin_panel'))

# ============================================================
# PWA МАРШРУТЫ
# ============================================================

@app.route('/manifest.json')
def manifest():
    return send_file('manifest.json', mimetype='application/json')

@app.route('/sw.js')
def service_worker():
    return send_file('sw.js', mimetype='application/javascript')

@app.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    try:
        subscription = request.json
        save_user_subscription(current_user.id, subscription)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Ошибка подписки push: {e}")
        return jsonify({"success": False, "error": str(e)})

# ============================================================
# РЕФЕРАЛЬНАЯ СИСТЕМА
# ============================================================

@app.route('/referral')
@login_required
def referral_page():
    try:
        from referral import get_referral_stats, get_user_referral_code
        stats = get_referral_stats(current_user.id)
        code = get_user_referral_code(current_user.id)
        referral_link = f"{request.host_url}register?ref={code}"
        return render_template('referral.html', code=code, link=referral_link, stats=stats)
    except Exception as e:
        logger.error(f"Ошибка рефералов: {e}")
        flash('Раздел в разработке', 'info')
        return redirect(url_for('dashboard'))

@app.route('/tournament/<tournament_key>/results')
@login_required
def tournament_results(tournament_key):
    if tournament_key not in db.TOURNAMENT_INFO_TEXT:
        flash('Турнир не найден', 'error')
        return redirect(url_for('tournaments'))
    try:
        from tournaments import get_tournament_leaderboard, get_user_tournament_history
        leaderboard = get_tournament_leaderboard(db, tournament_key)
        user_history = get_user_tournament_history(db, current_user.id)
        return render_template('tournament_results.html',
                             tournament_key=tournament_key,
                             tournament=db.TOURNAMENT_INFO_TEXT[tournament_key],
                             leaderboard=leaderboard,
                             user_history=user_history)
    except Exception as e:
        logger.error(f"Ошибка результатов турнира: {e}")
        flash('Ошибка загрузки результатов', 'error')
        return redirect(url_for('tournaments'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        phone = request.form.get('phone')
        if not phone:
            flash('Введите номер телефона', 'error')
            return redirect(url_for('forgot_password'))

        phone_digits = re.sub(r'\D', '', phone)
        if phone_digits.startswith('8') and len(phone_digits) == 11:
            phone_digits = '7' + phone_digits[1:]

        users_ws = db.get_or_create_users_sheet()
        user_record = db.find_user_by_phone(phone, users_ws)

        if not user_record:
            flash('Пользователь с таким номером не найден', 'error')
            return redirect(url_for('forgot_password'))

        temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        password_hash = generate_password_hash(temp_password)

        auth_data = db._load_auth_data()
        auth_data[phone_digits] = {
            "user_id": user_record.get(db.HEADER_TOP_RACER_ID),
            "tracerdb_id": user_record.get(db.HEADER_TOP_RACER_ID),
            "password_hash": password_hash,
            "phone": phone,
            "nickname": user_record.get(db.HEADER_NICKNAME, "Пользователь"),
            "created_at": datetime.now().isoformat()
        }
        db._save_auth_data(auth_data)

        telegram_id = user_record.get(db.HEADER_TELEGRAM_ID)
        notification_sent = False
        if telegram_id:
            try:
                message = (
                    f"🔑 <b>СБРОС ПАРОЛЯ</b>\n\n"
                    f"Ваш новый временный пароль:\n"
                    f"<code>{temp_password}</code>\n\n"
                    f"⚠️ Смените пароль после входа!"
                )
                notification_sent = send_telegram_notification(telegram_id, message)
            except Exception as e:
                logger.error(f"Ошибка отправки Telegram: {e}")

        if notification_sent:
            flash('Новый пароль отправлен в Telegram!', 'success')
        else:
            flash(f'Пароль сброшен! Временный пароль: {temp_password}', 'success')

        return redirect(url_for('login'))

    return render_template('forgot_password.html')

# ============================================================
# ЗАПУСК
# ============================================================

# ============================================================
# НОВОСТИ (ЛЕНТА)
# ============================================================

@app.route('/news')
@login_required
def news_feed():
    """Лента новостей"""
    posts = get_posts(limit=50)

    # Проверяем лайки для текущего пользователя
    for post in posts:
        post['is_liked'] = is_liked(post['id'], current_user.id)
        post['comments'] = get_comments(post['id'], limit=3)  # Последние 3 комментария
        post['comments_count'] = post['comments_count']

    return render_template('news_feed.html', posts=posts)


@app.route('/news/create', methods=['GET', 'POST'])
@login_required
def create_news_post():
    """Создание поста (только для админов)"""
    if not current_user.is_admin:
        flash('Только администраторы могут создавать посты', 'error')
        return redirect(url_for('news_feed'))

    if request.method == 'POST':
        content = request.form.get('content', '').strip()

        if not content:
            flash('Пост не может быть пустым', 'error')
            return redirect(url_for('create_news_post'))

        if len(content) > 5000:
            flash('Пост слишком длинный (макс. 5000 символов)', 'error')
            return redirect(url_for('create_news_post'))

        # Обработка загрузки изображения
        image_path = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                ext = filename.rsplit('.', 1)[1].lower()
                new_filename = f"news_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{current_user.id}.{ext}"
                image_folder = os.path.join(app.static_folder, 'uploads', 'news')
                os.makedirs(image_folder, exist_ok=True)
                filepath = os.path.join(image_folder, new_filename)
                file.save(filepath)
                image_path = f"/static/uploads/news/{new_filename}"

        # Создаем пост
        post_id = create_post(
            current_user.id,
            current_user.nickname,
            content,
            image_path
        )

        # Уведомляем всех пользователей о новом посте
        try:
            users_ws = db.get_or_create_users_sheet()
            all_data = users_ws.get_all_values()
            if all_data and len(all_data) > 1:
                for row in all_data[1:]:
                    if len(row) > 0:
                        try:
                            user_id = int(row[0])
                            if user_id != current_user.id:
                                add_notification(
                                    user_id,
                                    "news",
                                    "📰 Новая новость",
                                    f"{current_user.nickname} опубликовал новость",
                                    "/news"
                                )
                        except:
                            pass
        except Exception as e:
            logger.error(f"Ошибка уведомления о новости: {e}")

        flash('Пост успешно опубликован!', 'success')
        return redirect(url_for('news_feed'))

    return render_template('create_post.html')


@app.route('/news/<int:post_id>/like', methods=['POST'])
@login_required
def like_news_post(post_id):
    """Лайк поста"""
    post = get_post(post_id)
    if not post:
        return jsonify({"error": "Пост не найден"}), 404

    if is_liked(post_id, current_user.id):
        unlike_post(post_id, current_user.id)
        liked = False
    else:
        like_post(post_id, current_user.id)
        liked = True

    # Получаем обновленное количество лайков
    updated_post = get_post(post_id)

    return jsonify({
        "success": True,
        "liked": liked,
        "likes_count": updated_post['likes_count']
    })


@app.route('/news/<int:post_id>/comment', methods=['POST'])
@login_required
def comment_news_post(post_id):
    """Добавление комментария"""
    post = get_post(post_id)
    if not post:
        flash('Пост не найден', 'error')
        return redirect(url_for('news_feed'))

    content = request.form.get('content', '').strip()
    if not content:
        flash('Комментарий не может быть пустым', 'error')
        return redirect(url_for('news_feed'))

    if len(content) > 1000:
        flash('Комментарий слишком длинный (макс. 1000 символов)', 'error')
        return redirect(url_for('news_feed'))

    add_comment(post_id, current_user.id, current_user.nickname, content)

    # Уведомляем автора поста
    if post['author_id'] != current_user.id:
        add_notification(
            post['author_id'],
            "comment",
            f"💬 Новый комментарий",
            f"{current_user.nickname} прокомментировал ваш пост",
            "/news"
        )

    flash('Комментарий добавлен', 'success')
    return redirect(url_for('news_feed'))


@app.route('/news/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_news_post(post_id):
    """Удаление поста (только для админов)"""
    if not current_user.is_admin:
        flash('Только администраторы могут удалять посты', 'error')
        return redirect(url_for('news_feed'))

    post = get_post(post_id)
    if not post:
        flash('Пост не найден', 'error')
        return redirect(url_for('news_feed'))

    # Удаляем изображение если есть
    if post.get('image_path'):
        try:
            image_full_path = os.path.join(app.root_path, post['image_path'][1:])
            if os.path.exists(image_full_path):
                os.remove(image_full_path)
        except Exception as e:
            logger.error(f"Ошибка удаления изображения: {e}")

    delete_post(post_id)
    flash('Пост удален', 'success')
    return redirect(url_for('news_feed'))


@app.route('/news/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_news_comment(comment_id):
    """Удаление комментария (только для админов или автора)"""
    comments = get_comments(999999)  # Получаем все комментарии для поиска
    comment = next((c for c in comments if c['id'] == comment_id), None)

    if not comment:
        flash('Комментарий не найден', 'error')
        return redirect(url_for('news_feed'))

    if not current_user.is_admin and comment['user_id'] != current_user.id:
        flash('Вы можете удалять только свои комментарии', 'error')
        return redirect(url_for('news_feed'))

    delete_comment(comment_id)
    flash('Комментарий удален', 'success')
    return redirect(url_for('news_feed'))


@app.route('/admin/register-user', methods=['GET', 'POST'])
@login_required
def admin_register_user():
    """Регистрация пользователя администратором"""
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nickname = request.form.get('nickname')
        phone = request.form.get('phone')
        password = request.form.get('password')

        if not all([nickname, phone, password]):
            flash('Заполните все поля', 'error')
            return redirect(url_for('admin_register_user'))

        if len(password) < 6:
            flash('Пароль должен быть не менее 6 символов', 'error')
            return redirect(url_for('admin_register_user'))

        phone_digits = re.sub(r'\D', '', phone)
        if not (10 <= len(phone_digits) <= 15):
            flash('Неверный формат телефона', 'error')
            return redirect(url_for('admin_register_user'))

        # Проверяем, не зарегистрирован ли уже
        auth_check = db._load_auth_data()
        if phone_digits in auth_check:
            flash('Пользователь с таким телефоном уже зарегистрирован', 'error')
            return redirect(url_for('admin_register_user'))

        password_hash = generate_password_hash(password)
        result = db.register_user(nickname, phone, password_hash, registered_by=current_user.id)

        if result['success']:
            flash(f'Пользователь {nickname} успешно зарегистрирован!', 'success')
            return redirect(url_for('admin_users_list'))
        else:
            flash(f'Ошибка регистрации: {result.get("error")}', 'error')

    return render_template('admin/register_user.html')


@app.route('/admin/user/<int:user_id>/add-lap-time', methods=['GET', 'POST'])
@login_required
def admin_add_lap_time(user_id):
    """Запись лучшего времени круга игрока"""
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('dashboard'))

    users_ws = db.get_or_create_users_sheet()
    record = db.find_user_by_id(user_id, users_ws)

    if not record:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('admin_users_list'))

    if request.method == 'POST':
        track_key = request.form.get('track')
        lap_time = request.form.get('lap_time')

        if not track_key or not lap_time:
            flash('Выберите трассу и введите время', 'error')
            return redirect(url_for('admin_add_lap_time', user_id=user_id))

        # Парсим время (формат MM:SS.ms или SS.ms)
        try:
            if ':' in lap_time:
                minutes, seconds = lap_time.split(':')
                total_seconds = float(minutes) * 60 + float(seconds)
            else:
                total_seconds = float(lap_time)

            if total_seconds <= 0:
                flash('Время должно быть больше 0', 'error')
                return redirect(url_for('admin_add_lap_time', user_id=user_id))

            # Сохраняем время
            result = db.save_lap_time(user_id, track_key, total_seconds, lap_time)

            if result['success']:
                flash(f'Время {lap_time} на трассе {db.GT_TRACKS[track_key]["name"]} сохранено!', 'success')
                return redirect(url_for('admin_user_detail', user_id=user_id))
            else:
                flash(f'Ошибка: {result.get("error")}', 'error')
        except ValueError:
            flash('Неверный формат времени. Используйте MM:SS.ms или SS.ms', 'error')

    return render_template('admin/add_lap_time.html',
                           user_id=user_id,
                           nickname=record.get(db.HEADER_NICKNAME, 'Неизвестно'),
                           tracks=db.GT_TRACKS)

if __name__ == '__main__':
    os.makedirs(app.config.get('QR_CODES_FOLDER', 'qr_codes'), exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)