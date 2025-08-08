from main import bot
from app import news_parser
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime
import asyncio
from app.data import db
from dateutil import parser

running = False

async def check_user_subscriptions():
    global running
    while running:
        subs = await db.get_all_subscriptions()
        if not subs:
            await asyncio.sleep(5)
            continue

        for sub in subs:
            sub_id = sub['id']
            raw_last = sub.get("latest_post_time")  # ISO-строка или None

            # 1) Парсим last_post_time в datetime, если он есть
            if raw_last:
                try:
                    last_dt = datetime.fromisoformat(raw_last)
                except ValueError:
                    # fallback на dateutil
                    last_dt = parser.parse(raw_last)
            else:
                last_dt = None

            source = await db.get_source_by_id(sub["source_id"])
            if not source:
                continue

            latest = await news_parser.get_latest(source["url"])
            if not latest:
                continue

            raw_new = latest.get("published")
            if not raw_new:
                continue

            # 2) Парсим новое время в datetime
            if isinstance(raw_new, str):
                try:
                    new_dt = datetime.fromisoformat(raw_new)
                except ValueError:
                    new_dt = parser.parse(raw_new)
            elif isinstance(raw_new, datetime):
                new_dt = raw_new
            else:
                # непонятный формат — пропустим
                continue

            # 3) Теперь корректно сравниваем
            if not last_dt or new_dt > last_dt:
                title   = latest.get("title", "")
                link    = latest.get("link", "")
                summary = latest.get("summary", "")

                msg  = f"<b>{title}</b>\n"
                msg += f"<i>{new_dt.isoformat()}</i>\n\n" if new_dt else ""
                msg += f"{summary}\n" if summary else ""
                msg += f"\n<a href='{link}'>Read more</a>" if link else ""

                try:
                    await bot.send_message(sub["user_id"], msg, parse_mode="HTML")
                    # 4) Сохраняем в БД именно строку ISO, чтобы следующий раз тоже смогли распарсить
                    await db.update_subscription_last_post_time_by_id(sub_id, new_dt.isoformat())
                except TelegramBadRequest as e:
                    print(f"Failed to send to {sub['user_id']}: {e}")

        await asyncio.sleep(5)


def pause_checker():
    """
    Pause the news checker loop.
    """
    global running
    running = False

def run_checker():
    """
    Run the news checker loop.
    """
    global running
    running = True

    asyncio.create_task(check_user_subscriptions())
