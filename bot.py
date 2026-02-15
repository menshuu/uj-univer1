import asyncio
import logging
import types
from db import init_all
from db import init_all

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from config import load_config
from db import init_db
init_db()

config = load_config()

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "bot.log"

handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=7, encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,  # INFO yoki WARNING qilsa ham bo'ladi
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[handler, logging.StreamHandler()],
)

init_all()

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import load_config, Config
from handlers import common_router, admin_router, user_router
from db import init_all, log_bot_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def patch_bot_logging(bot: Bot):
    """
    Bot yuborgan xabarlarni (send/copy) DBga avtomatik yozib boradi.
    MUHIM: MethodType bilan bog‘lanadi, aks holda bot “sinadi”.
    """

    orig_send_message = bot.send_message
    orig_copy_message = bot.copy_message

    async def send_message_logged(self: Bot, chat_id, *args, **kwargs):
        msg = await orig_send_message(chat_id, *args, **kwargs)

        # faqat user (private chat)larni log qilamiz
        if isinstance(chat_id, int) and chat_id > 0:
            try:
                log_bot_message(
                    user_id=int(chat_id),
                    chat_id=int(chat_id),
                    message_id=int(msg.message_id),
                )
            except Exception:
                pass
        return msg

    async def copy_message_logged(self: Bot, chat_id, *args, **kwargs):
        res = await orig_copy_message(chat_id, *args, **kwargs)

        if isinstance(chat_id, int) and chat_id > 0:
            try:
                log_bot_message(
                    user_id=int(chat_id),
                    chat_id=int(chat_id),
                    message_id=int(res.message_id),
                )
            except Exception:
                pass
        return res

    # ✅ SHU JOY MUHIM (to‘g‘ri bind)
    bot.send_message = types.MethodType(send_message_logged, bot)
    bot.copy_message = types.MethodType(copy_message_logged, bot)


async def main():
    init_all()

    config: Config = load_config()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    await bot.delete_webhook(drop_pending_updates=True)

    patch_bot_logging(bot)

    dp = Dispatcher()
    dp["config"] = config

    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)

    await dp.start_polling(bot, config=config)


if __name__ == "__main__":
    asyncio.run(main())
