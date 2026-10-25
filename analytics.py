import logging
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


def get_full_analytics(db):
    """Полная аналитика для администраторов"""
    try:
        users_ws = db.get_or_create_users_sheet()
        all_data = users_ws.get_all_values()

        if not all_data or len(all_data) < 2:
            return {"error": "Нет данных"}

        headers = all_data[0]
        users = []
        for row in all_data[1:]:
            if not row:
                continue
            record = {}
            for i, h in enumerate(headers):
                record[h] = row[i] if i < len(row) else ""
            users.append(record)

        # Базовая статистика
        total_users = len(users)
        total_visits = sum(int(u.get(db.HEADER_VISITS, 0) or 0) for u in users)
        total_coins = sum(
            int(str(u.get(db.HEADER_TOPCOINS, '0')).replace('TC', '').strip() or 0)
            for u in users
        )
        total_bonus_minutes = sum(
            int(str(u.get(db.HEADER_BONUS_MINUTES, '0')).replace('мин', '').strip() or 0)
            for u in users
        )

        # По уровням
        levels = defaultdict(int)
        for u in users:
            level = int(u.get(db.HEADER_LEVEL, 1) or 1)
            levels[level] += 1

        # По филиалам (из турниров)
        branches_stats = {"summer": 0, "prospekt": 0, "raduga": 0}
        for key in ["cs2", "mk", "gt", "ufc"]:
            try:
                sheet_name = db.TOURNAMENT_INFO_TEXT[key]["sheet"]
                ws = db.sheet.worksheet(sheet_name)
                records = ws.get_all_records()
                for r in records:
                    branch = r.get("Филиал", "")
                    if "Лето" in branch:
                        branches_stats["summer"] += 1
                    elif "Проспект" in branch:
                        branches_stats["prospekt"] += 1
                    elif "Радуга" in branch:
                        branches_stats["raduga"] += 1
            except:
                pass

        # Активность по дням (последние 30 дней)
        daily_activity = []
        for i in range(30, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime("%d.%m.%Y")
            count = 0
            for u in users:
                last_visit = str(u.get(db.HEADER_LAST_VISIT, ""))
                if date in last_visit:
                    count += 1
            daily_activity.append({"date": date, "visits": count})

        # Топ-10 пользователей по посещениям
        top_users = sorted(users, key=lambda x: int(x.get(db.HEADER_VISITS, 0) or 0), reverse=True)[:10]

        # Топ-10 по TopCoins
        top_coins_users = sorted(
            users,
            key=lambda x: int(str(x.get(db.HEADER_TOPCOINS, '0')).replace('TC', '').strip() or 0),
            reverse=True
        )[:10]

        return {
            "total_users": total_users,
            "total_visits": total_visits,
            "total_coins": total_coins,
            "total_bonus_minutes": total_bonus_minutes,
            "avg_visits_per_user": round(total_visits / total_users, 2) if total_users else 0,
            "levels_distribution": dict(levels),
            "branches_stats": branches_stats,
            "daily_activity": daily_activity,
            "top_users_by_visits": [
                {
                    "nickname": u.get(db.HEADER_NICKNAME, ""),
                    "visits": int(u.get(db.HEADER_VISITS, 0) or 0),
                    "level": int(u.get(db.HEADER_LEVEL, 1) or 1)
                } for u in top_users
            ],
            "top_users_by_coins": [
                {
                    "nickname": u.get(db.HEADER_NICKNAME, ""),
                    "coins": int(str(u.get(db.HEADER_TOPCOINS, '0')).replace('TC', '').strip() or 0)
                } for u in top_coins_users
            ]
        }
    except Exception as e:
        logger.error(f"Аналитика ошибка: {e}")
        return {"error": str(e)}