import json
import os
import logging
import requests
from datetime import datetime
from notifications_db import get_admin_ids

logger = logging.getLogger(__name__)

PUSH_SUBSCRIPTIONS_FILE = "push_subscriptions.json"
TELEGRAM_BOT_TOKEN = "8226120070:AAGM5ISjCMc1ITy8uOgrGhfjEzGpX9TZIms"

async def notify_admins(db_instance, title, message, link="/admin/panel"):
    """Отправляет уведомление всем администраторам"""
    admin_ids = get_admin_ids(db_instance)
    for admin_id in admin_ids:
        await send_push_notification(admin_id, title, message, link)
        # Здесь можно добавить отправку в Telegram, если у админа есть Telegram ID
        # (нужно будет добавить функцию get_telegram_id_by_user_id в database.py)

def load_subscriptions():
    if os.path.exists(PUSH_SUBSCRIPTIONS_FILE):
        with open(PUSH_SUBSCRIPTIONS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_subscriptions(data):
    with open(PUSH_SUBSCRIPTIONS_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_user_subscription(user_id, subscription):
    subs = load_subscriptions()
    subs[str(user_id)] = subscription
    save_subscriptions(subs)
    logger.info(f"💾 Push subscription сохранена для user {user_id}")


def remove_user_subscription(user_id):
    subs = load_subscriptions()
    if str(user_id) in subs:
        del subs[str(user_id)]
        save_subscriptions(subs)


async def send_push_notification(user_id, title, body, url="/"):
    """Отправляет Web Push уведомление"""
    subs = load_subscriptions()
    subscription = subs.get(str(user_id))

    if not subscription:
        logger.warning(f"Push subscription не найдена для {user_id}")
        return False

    try:
        from pywebpush import webpush, WebPushException
        VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')

        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": "mailto:admin@toprace.ru"}
        )
        logger.info(f"✅ Push отправлен: {title} -> user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Push ошибка: {e}")
        return False


def send_telegram_notification(telegram_id, message):
    """Отправляет уведомление через Telegram бота"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": telegram_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=data, timeout=10)
        return response.json().get('ok', False)
    except Exception as e:
        logger.error(f"Telegram ошибка: {e}")
        return False


async def notify_booking_created(user_id, user_nickname, booking_text, branch_name, admin_telegram_ids):
    """Уведомление о новой заявке на бронирование"""
    title = "📝 Новая заявка на посещение"
    body = f"{user_nickname} хочет записаться в филиал {branch_name}"

    # Push всем админам
    for admin_id in admin_telegram_ids:
        await send_push_notification(admin_id, title, body, "/admin/bookings")

        # Telegram fallback
        message = (
            f"📝 <b>НОВАЯ ЗАЯВКА</b>\n\n"
            f"👤 <b>Геймер:</b> {user_nickname}\n"
            f"🏢 <b>Филиал:</b> {branch_name}\n"
            f"📋 <b>Текст:</b> {booking_text}\n"
            f"⏰ <b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        send_telegram_notification(admin_id, message)


async def notify_user_booking_status(user_id, status, details=""):
    """Уведомление пользователю о статусе заявки"""
    title = "📋 Статус заявки"
    if status == "approved":
        body = f"✅ Ваша заявка подтверждена! {details}"
    elif status == "rejected":
        body = f"❌ Заявка отклонена. {details}"
    else:
        body = f"ℹ️ {details}"

    await send_push_notification(user_id, title, body, "/dashboard")