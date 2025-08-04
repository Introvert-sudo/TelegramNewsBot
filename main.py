import asyncio
import logging

from aiogram import *

from app.data.db import init_db
from config import TELEGRAM_TOKEN

from app.handlers import router, setup_background_task

TOKEN = TELEGRAM_TOKEN

bot = Bot(token=TOKEN)
dp = Dispatcher()


async def main():
    dp.include_router(router)
    await init_db()
    setup_background_task(bot)
    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("exit")
