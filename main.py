import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.data.db import init_db
from config import TELEGRAM_TOKEN

from app.handlers import router

from app import news_checker

TOKEN = TELEGRAM_TOKEN

bot = Bot(token=TOKEN)
dp = Dispatcher()


async def main():
    dp.include_router(router)
    await init_db()
    news_checker.run_checker()
    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("exit")
