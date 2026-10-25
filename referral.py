import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

REFERRAL_FILE = "referrals.json"
REFERRAL_BONUS_COINS = 200
REFERRAL_BONUS_MINUTES = 15


def load_referrals():
    if os.path.exists(REFERRAL_FILE):
        with open(REFERRAL_FILE, 'r') as f:
            return json.load(f)
    return {"users": {}, "history": []}


def save_referrals(data):
    with open(REFERRAL_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_referral_code(user_id):
    """Генерирует реферальный код"""
    import random
    import string
    code = 'TR' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    data = load_referrals()
    data["users"][str(user_id)] = {
        "code": code,
        "created_at": datetime.now().isoformat(),
        "referrals_count": 0,
        "total_bonus_coins": 0,
        "total_bonus_minutes": 0
    }
    save_referrals(data)
    return code


def get_user_referral_code(user_id):
    data = load_referrals()
    user_data = data["users"].get(str(user_id))
    if user_data:
        return user_data["code"]
    return generate_referral_code(user_id)


def apply_referral_code(new_user_id, referral_code):
    """Применяет реферальный код при регистрации"""
    data = load_referrals()

    # Находим владельца кода
    inviter_id = None
    for uid, udata in data["users"].items():
        if udata.get("code") == referral_code:
            inviter_id = uid
            break

    if not inviter_id:
        return {"success": False, "error": "Неверный реферальный код"}

    if str(inviter_id) == str(new_user_id):
        return {"success": False, "error": "Нельзя использовать свой код"}

    # Проверяем, не использовал ли уже код
    for entry in data["history"]:
        if entry.get("new_user_id") == str(new_user_id):
            return {"success": False, "error": "Реферальный код уже использован"}

    # Начисляем бонусы
    data["users"][inviter_id]["referrals_count"] += 1
    data["users"][inviter_id]["total_bonus_coins"] += REFERRAL_BONUS_COINS
    data["users"][inviter_id]["total_bonus_minutes"] += REFERRAL_BONUS_MINUTES

    data["history"].append({
        "inviter_id": inviter_id,
        "new_user_id": str(new_user_id),
        "code": referral_code,
        "date": datetime.now().isoformat(),
        "coins": REFERRAL_BONUS_COINS,
        "minutes": REFERRAL_BONUS_MINUTES
    })

    save_referrals(data)

    return {
        "success": True,
        "inviter_id": int(inviter_id),
        "coins_bonus": REFERRAL_BONUS_COINS,
        "minutes_bonus": REFERRAL_BONUS_MINUTES
    }


def get_referral_stats(user_id):
    """Статистика рефералов пользователя"""
    data = load_referrals()
    user_data = data["users"].get(str(user_id), {})

    referrals = [h for h in data["history"] if h.get("inviter_id") == str(user_id)]

    return {
        "code": user_data.get("code", ""),
        "total_referrals": user_data.get("referrals_count", 0),
        "total_coins_earned": user_data.get("total_bonus_coins", 0),
        "total_minutes_earned": user_data.get("total_bonus_minutes", 0),
        "recent_referrals": referrals[-5:]
    }


def get_friends_list(user_id):
    """Список друзей (рефералов)"""
    data = load_referrals()
    friends = []
    for entry in data["history"]:
        if entry.get("inviter_id") == str(user_id):
            friends.append({
                "user_id": entry["new_user_id"],
                "date": entry["date"],
                "bonus_coins": entry["coins"]
            })
    return friends