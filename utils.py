from aiogram.types import Message
from db import log_bot_message

async def send_and_log(message: Message, text: str, reply_markup=None):
    sent = await message.answer(text, reply_markup=reply_markup)
    log_bot_message(
        user_id=message.from_user.id,
        chat_id=sent.chat.id,
        message_id=sent.message_id
    )
    return sent
