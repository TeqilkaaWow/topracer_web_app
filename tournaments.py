import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def save_tournament_result(db, tournament_key, user_id, username, score, position, details=None):
    """Сохраняет результат турнира"""
    try:
        sheet_name = f"{tournament_key.upper()}_Results"
        try:
            ws = db.sheet.worksheet(sheet_name)
        except:
            ws = db.sheet.add_worksheet(title=sheet_name, rows="1000", cols="10")
            ws.append_row(["Дата", "Турнир", "User ID", "Никнейм", "Позиция",
                           "Очки/Время", "Детали", "Награда"])

        ws.append_row([
            datetime.now().strftime("%d.%m.%Y %H:%M"),
            tournament_key,
            str(user_id),
            username,
            position,
            str(score),
            details or "",
            ""
        ])
        return {"success": True}
    except Exception as e:
        logger.error(f"Ошибка сохранения результата: {e}")
        return {"success": False, "error": str(e)}


def get_tournament_leaderboard(db, tournament_key, limit=50):
    """Получает таблицу лидеров турнира"""
    try:
        sheet_name = f"{tournament_key.upper()}_Results"
        ws = db.sheet.worksheet(sheet_name)
        records = ws.get_all_records()

        # Сортировка по позиции
        records.sort(key=lambda x: int(x.get("Позиция", 999)))

        return records[:limit]
    except:
        return []


def get_user_tournament_history(db, user_id):
    """История турниров пользователя"""
    try:
        results = []
        for key in ["cs2", "mk", "gt", "ufc"]:
            sheet_name = f"{key.upper()}_Results"
            try:
                ws = db.sheet.worksheet(sheet_name)
                records = ws.get_all_records()
                for r in records:
                    if str(r.get("User ID", "")) == str(user_id):
                        r["tournament"] = key
                        results.append(r)
            except:
                pass

        results.sort(key=lambda x: x.get("Дата", ""), reverse=True)
        return results
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return []


def assign_tournament_rewards(db, tournament_key, results):
    """Начисляет награды за турнир"""
    rewards = {
        1: {"coins": 1000, "minutes": 60, "title": "🥇 Победитель"},
        2: {"coins": 500, "minutes": 30, "title": "🥈 Второе место"},
        3: {"coins": 300, "minutes": 15, "title": " Третье место"}
    }

    awarded = []
    for result in results:
        position = int(result.get("Позиция", 999))
        if position in rewards:
            user_id = result.get("User ID")
            reward = rewards[position]
            db.update_topcoins(user_id, reward["coins"], "add")
            db.add_bonus_minutes(user_id, reward["minutes"])
            awarded.append({
                "user_id": user_id,
                "nickname": result.get("Никнейм"),
                "position": position,
                "reward": reward
            })

    return awarded