# helpers/tg.py

from __future__ import annotations

from typing import Optional, Any
from aiogram.types import Message
from aiogram import Bot

from db import log_bot_message


async def answer_and_log(
    message: Message,
    text: str,
    reply_markup: Any = None,
    protect_content: bool = False,
    keep: bool = False,
    **kwargs
):
    """
    message.answer(...) yuboradi va bot yuborgan xabarni DB ga log qiladi.
    keep=True bo'lsa log qilmaydi (menyu kabi doimiy xabarlar o'chmasin).
    """
    msg = await message.answer(
        text,
        reply_markup=reply_markup,
        protect_content=protect_content,
        **kwargs
    )

    if not keep:
        try:
            log_bot_message(message.from_user.id, msg.chat.id, msg.message_id)
        except Exception:
            pass

    return msg


async def copy_to_user_and_log(
    bot: Bot,
    user_id: int,
    from_chat_id: int,
    message_id: int,
    protect_content: bool = False,
    keep: bool = False,
    **kwargs
):
    """
    bot.copy_message(...) qiladi va natijadagi xabarni DB ga log qiladi.
    keep=True bo'lsa log qilmaydi (agar kerak bo'lsa).
    """
    msg = await bot.copy_message(
        chat_id=user_id,
        from_chat_id=from_chat_id,
        message_id=message_id,
        protect_content=protect_content,
        **kwargs
    )

    if not keep:
        try:
            log_bot_message(user_id, msg.chat.id, msg.message_id)
        except Exception:
            pass

    return msg
