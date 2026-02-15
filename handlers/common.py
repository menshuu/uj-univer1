# handlers/common.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, Command
from aiogram.types import PollAnswer
from db import upsert_poll_vote, is_user_blocked

from helpers.tg import answer_and_log
from config import Config
from db import is_user_blocked

from keyboards import admin_main_menu, user_main_menu, blocked_user_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, config: Config):
    # Har qanday holatda jarayon bekor bo‘lsin
    await state.clear()

    # ✅ BLOCK CHECK (admin bo'lsa ham tekshiradi, xohlasang adminni chetlab o'tkazamiz)
    if is_user_blocked(message.from_user.id):
        await message.answer(
            "⛔ Siz blocklangansiz.\n"
            "Faqat '💬 SHIKOYAT VA TAKLIFLAR' orqali yozishingiz mumkin.",
            reply_markup=blocked_user_menu()
        )
        return

    # Admin / user menyu
    if message.from_user.id in config.admins:
        await message.answer("✅ Bot ishga tushdi.\n🏠 Admin menyu:", reply_markup=admin_main_menu())
    else:
        await message.answer("✅ Bot ishga tushdi.\n🏠 Asosiy menyu:", reply_markup=user_main_menu())


@router.poll_answer()
async def on_poll_answer(poll_answer: PollAnswer):
    # poll_answer: user + poll_id + option_ids
    try:
        upsert_poll_vote(poll_answer.poll_id, poll_answer.user.id, poll_answer.option_ids)
    except Exception:
        pass

@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, config: Config):
    await state.clear()

    # ✅ Block bo'lsa faqat blocked menu
    if is_user_blocked(message.from_user.id):
        await message.answer(
            "⛔ Siz blocklangansiz.\n"
            "Faqat '💬 SHIKOYAT VA TAKLIFLAR' orqali yozishingiz mumkin.",
            reply_markup=blocked_user_menu()
        )
        return

    if message.from_user.id in config.admins:
        await message.answer("🏠 Admin menyu:", reply_markup=admin_main_menu())
    else:
        await message.answer("🏠 Asosiy menyu:", reply_markup=user_main_menu())


@router.message(F.text == "🏠 ASOSIY MENYU")
async def go_home(message: Message, state: FSMContext, config: Config):
    await state.clear()

    # ✅ Block bo'lsa faqat blocked menu
    if is_user_blocked(message.from_user.id):
        await message.answer(
            "⛔ Siz blocklangansiz.\n"
            "Faqat '💬 SHIKOYAT VA TAKLIFLAR' orqali yozishingiz mumkin.",
            reply_markup=blocked_user_menu()
        )
        return

    # ⚠️ Agar answer_and_log keep'ni qabul qilmasa -> pastdagi "keep"ni olib tashla
    if message.from_user.id in config.admins:
        await answer_and_log(message, "🏠 Asosiy menyu", reply_markup=admin_main_menu(), keep=True)
    else:
        await answer_and_log(message, "🏠 Asosiy menyu", reply_markup=user_main_menu(), keep=True)


@router.message(F.text == "⬅️ ORQAGA")
async def go_back(message: Message, state: FSMContext, config: Config):
    await state.clear()

    # ✅ Block bo'lsa faqat blocked menu
    if is_user_blocked(message.from_user.id):
        await message.answer(
            "⛔ Siz blocklangansiz.\n"
            "Faqat '💬 SHIKOYAT VA TAKLIFLAR' orqali yozishingiz mumkin.",
            reply_markup=blocked_user_menu()
        )
        return

    # ⚠️ Agar answer_and_log keep'ni qabul qilmasa -> pastdagi "keep"ni olib tashla
    if message.from_user.id in config.admins:
        await answer_and_log(message, "⬅️ Orqaga", reply_markup=admin_main_menu(), keep=True)
    else:
        await answer_and_log(message, "⬅️ Orqaga", reply_markup=user_main_menu(), keep=True)
