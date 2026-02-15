# handlers/admin.py

import asyncio
import time
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramRetryAfter

from docx import Document

from config import Config
from helpers.tg import answer_and_log
from keyboards import inline_courses_with_general
from db import (
    # general
    get_general_subjects, add_general_subject, get_general_subject_by_name,
    add_general_file, get_general_files, delete_general_file, delete_general_subject,
)

from keyboards import (
    admin_main_menu,
    admin_library_menu,
    admin_settings_menu,
    admin_exam_menu,
    admin_feedback_menu,
    admin_clear_chat_menu,
    admin_broadcast_menu,
    back_menu,
    user_main_menu,
    inline_courses,
    inline_semesters,
    inline_sub_settings,
    blocked_user_menu,
    admin_block_menu,
)

from db import (
    connect,
    delete_subject,


    # settings
    get_bool_setting,
    toggle_bool_setting,

    # library
    get_subjects, add_subject, get_subject_by_name,
    add_file, get_files, delete_file,

    # exam
    get_exam_subjects, add_exam_subject, get_exam_subject_by_name,
    add_exam_file, get_exam_files, delete_exam_subject,

    # feedback
    list_feedback,

    # clean
    get_bot_messages, clear_bot_messages,

    # tests
    add_test, add_question, list_tests, delete_test, count_questions,
    update_test_source_file,

    # block
    block_user, unblock_user, is_user_blocked, list_blocked_users,

    # broadcast + poll stats
    create_broadcast, log_broadcast_message,
    list_broadcasts, list_broadcast_messages, delete_broadcast,
    create_poll_row, save_poll_instance, list_polls, get_poll_summary, clear_poll_stats,
)

router = Router()

# --- Paths (raw test files) ---
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_TEST_DIR = BASE_DIR / "storage" / "tests_raw"
RAW_TEST_DIR.mkdir(parents=True, exist_ok=True)

STOP_TEXTS = ["⬅️ ORQAGA", "🏠 ASOSIY MENYU"]


# =========================
# STATES
# =========================
class BlockStates(StatesGroup):
    waiting_block_user_id = State()
    waiting_unblock_user_id = State()


class LibraryStates(StatesGroup):
    choosing_course = State()
    choosing_semester = State()
    choosing_subject = State()
    waiting_files = State()

    # ✅ GENERAL BOOKS uchun alohida state
    general_choosing_subject = State()

    deleting_choose_course = State()
    subj_del_choose_course = State()
    subj_del_choose_semester = State()
    subj_del_choose_subject = State()
    subj_del_confirm = State()



class ExamStates(StatesGroup):
    choosing_course = State()
    choosing_semester = State()
    choosing_subject = State()
    waiting_files = State()
    deleting_choose_course = State()
    deleting_choose_semester = State()
    deleting_confirm = State()


class TestStates(StatesGroup):
    add_choose_course = State()
    add_choose_semester = State()
    add_waiting_name = State()
    add_waiting_file = State()

    del_choose_course = State()
    del_choose_semester = State()
    del_confirm = State()


class ClearChatStates(StatesGroup):
    waiting_user_id = State()


class BroadcastStates(StatesGroup):
    waiting_post = State()


# =========================
# HELPERS
# =========================
async def _send_user_menu_after_clean(bot: Bot, user_id: int):
    """Tozalashdan keyin userda menyu tugmalari ko‘rinib turishi uchun."""
    try:
        await bot.send_message(user_id, "🏠 Asosiy menyu", reply_markup=user_main_menu())
    except Exception:
        pass


def parse_questions_from_text(text: str):
    """
    Format:
    ? Question
    + correct
    = wrong
    = wrong
    = wrong
    """
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    questions = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("?"):
            i += 1
            continue

        qtext = lines[i][1:].strip()
        i += 1

        options = []
        correct_index = None

        for _ in range(4):
            if i >= len(lines):
                raise ValueError(f"Variantlar yetarli emas: savol '{qtext}'")

            ln = lines[i]
            if not (ln.startswith("+") or ln.startswith("=")):
                raise ValueError(f"Variant format xato: '{ln}' (savol: '{qtext}')")

            opt_text = ln[1:].strip()
            options.append(opt_text)

            if ln.startswith("+"):
                correct_index = len(options) - 1

            i += 1

        if correct_index is None:
            raise ValueError(f"To‘g‘ri javob (+) topilmadi: savol '{qtext}'")

        questions.append((qtext, options, correct_index))

    if not questions:
        raise ValueError("Savollar topilmadi. Formatni tekshiring (? + =).")

    return questions


def _tests_toggle_markup(enabled: bool):
    kb = InlineKeyboardBuilder()
    kb.button(
        text=("⛔ Testni o‘chirish" if enabled else "✅ Testni yoqish"),
        callback_data="settings:toggle_tests"
    )
    kb.adjust(1)
    return kb.as_markup()


def _clear_feedback_db():
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM feedback")
    conn.commit()
    conn.close()


def _fmt_dt(ts: int) -> str:
    import time as _t
    return _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(ts))


def _get_all_bot_messages():
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id, chat_id, message_id FROM bot_messages ORDER BY id ASC")
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    return rows


def _clear_all_bot_messages():
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM bot_messages")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


# =========================
# ADMIN MAIN
# =========================
@router.message(F.text == "📚 Kutubxona boshqaruvi")
async def admin_library_root(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return
    await message.answer("📚 Kutubxona boshqaruvi", reply_markup=admin_library_menu())


@router.message(F.text == "📄 Imtihon savollari boshqaruvi")
async def admin_exam_root(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return
    await message.answer("📄 Imtihon savollari boshqaruvi", reply_markup=admin_exam_menu())


@router.message(F.text == "⚙️ Sozlamalar")
async def admin_settings_root(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return
    await message.answer("⚙️ Sozlamalar bo‘limi:", reply_markup=admin_settings_menu())


# =========================
# BLOCK (reply keyboard menu)
# =========================
@router.message(F.text == "🚫 Blockni boshqarish")
async def admin_block_root(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.clear()
    await message.answer("🚫 Blockni boshqarish:", reply_markup=admin_block_menu())


@router.message(F.text == "⛔ Blocklash")
async def admin_block_ask(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.set_state(BlockStates.waiting_block_user_id)
    await message.answer("⛔ Blocklash\n\nUser ID yuboring (faqat raqam):", reply_markup=admin_block_menu())


@router.message(BlockStates.waiting_block_user_id, F.text)
async def admin_block_do(message: Message, state: FSMContext, bot: Bot, config: Config):
    if message.from_user.id not in config.admins:
        return

    if not message.text.isdigit():
        await message.answer("❌ ID faqat raqam bo‘lishi kerak.", reply_markup=admin_block_menu())
        return

    uid = int(message.text)

    # users jadvalidan username/full_name olishga urinamiz
    username = ""
    full_name = ""
    try:
        conn = connect()
        cur = conn.cursor()
        cur.execute("SELECT username, full_name FROM users WHERE user_id=? LIMIT 1", (uid,))
        r = cur.fetchone()
        conn.close()
        if r:
            username = r["username"] or ""
            full_name = r["full_name"] or ""
    except Exception:
        pass

    # TG dan ham urinib ko‘ramiz
    if not username and not full_name:
        try:
            ch = await bot.get_chat(uid)
            username = getattr(ch, "username", "") or ""
            full_name = getattr(ch, "full_name", "") or ""
        except Exception:
            pass

    block_user(uid, username=username, full_name=full_name)

    # userga block menyu
    try:
        await bot.send_message(
            uid,
            "⛔ Siz bloklandingiz.\nFaqat '💬 SHIKOYAT VA TAKLIFLAR' orqali yozishingiz mumkin.",
            reply_markup=blocked_user_menu()
        )
    except Exception:
        pass

    await state.clear()
    await message.answer(f"✅ Blocklandi: {uid}", reply_markup=admin_block_menu())


@router.message(F.text == "✅ Blockdan chiqarish")
async def admin_unblock_ask(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.set_state(BlockStates.waiting_unblock_user_id)
    await message.answer("✅ Blockdan chiqarish\n\nUser ID yuboring (faqat raqam):", reply_markup=admin_block_menu())


@router.message(BlockStates.waiting_unblock_user_id, F.text)
async def admin_unblock_do(message: Message, state: FSMContext, bot: Bot, config: Config):
    if message.from_user.id not in config.admins:
        return

    if not message.text.isdigit():
        await message.answer("❌ ID faqat raqam bo‘lishi kerak.", reply_markup=admin_block_menu())
        return

    uid = int(message.text)

    if not is_user_blocked(uid):
        await state.clear()
        await message.answer("ℹ️ Bu user blockda emas.", reply_markup=admin_block_menu())
        return

    unblock_user(uid)

    # userga oddiy menyu
    try:
        await bot.send_message(
            uid,
            "✅ Siz blockdan chiqarildingiz. Endi botdan foydalanishingiz mumkin.",
            reply_markup=user_main_menu()
        )
    except Exception:
        pass

    await state.clear()
    await message.answer(f"✅ Blockdan chiqarildi: {uid}", reply_markup=admin_block_menu())


@router.message(F.text == "📋 Blocklanganlar ro‘yxati")
async def admin_blocked_list(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return

    rows = list_blocked_users(limit=200)
    if not rows:
        await message.answer("📭 Blocklangan userlar yo‘q.", reply_markup=admin_block_menu())
        return

    text = "📋 Blocklanganlar ro‘yxati:\n\n"
    for r in rows:
        # list_blocked_users dict qaytaradi deb olamiz
        uid = int(r.get("user_id", 0))
        username = (r.get("username", "") or "")
        full_name = (r.get("full_name", "") or "")
        blocked_at = r.get("blocked_at", "") or ""

        uname_show = f"@{username}" if username else "-"
        full_show = full_name or "-"
        text += f"{uid} | {full_show} | {uname_show} | {blocked_at}\n"

    await message.answer(text, reply_markup=admin_block_menu())


# =========================
# LIBRARY: ADD FILES
# =========================
@router.message(F.text == "➕ Fayl qo‘shish")
async def lib_add_start(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.clear()
    await state.set_state(LibraryStates.choosing_course)
    await message.answer("Kursni tanlang:", reply_markup=inline_courses_with_general("lib_add"))


@router.callback_query(F.data.startswith("lib_add:course:"))
async def lib_add_course(cb: CallbackQuery, state: FSMContext):
    course = int(cb.data.split(":")[-1])
    await state.update_data(course=course, gen_mode=False)  # ✅ oddiy rejim
    await state.set_state(LibraryStates.choosing_semester)
    await cb.message.edit_text(
        f"{course}-kurs. Semestrni tanlang:",
        reply_markup=inline_semesters("lib_add", course),
    )
    await cb.answer()


@router.callback_query(F.data == "lib_add:general")
async def lib_add_general(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(LibraryStates.general_choosing_subject)  # ✅ shu bo‘lsin

    subjects = get_general_subjects()

    if subjects:
        kb = InlineKeyboardBuilder()
        for s in subjects:
            kb.button(text=s["name"], callback_data=f"gen_add:sub:{s['id']}")
        kb.adjust(2)

        await cb.message.edit_text(
            "📚 Umumiy kitoblar\n"
            "📂 Bo‘limni tanlang yoki yangi bo‘lim nomini yozing (shu chatga).",
            reply_markup=kb.as_markup()
        )
    else:
        await cb.message.edit_text(
            "📚 Umumiy kitoblar\n"
            "Hozircha bo‘lim yo‘q.\n"
            "➕ Yangi bo‘lim/kitob nomini yozing (shu chatga)."
        )
    await cb.answer()

@router.callback_query(F.data.startswith("lib_add:sem:"))
async def lib_add_sem(cb: CallbackQuery, state: FSMContext):
    _, _, course, sem = cb.data.split(":")
    course_i = int(course)
    sem_i = int(sem)

    await state.update_data(semester=sem_i, gen_mode=False)  # ✅ oddiy rejim
    await state.set_state(LibraryStates.choosing_subject)

    subjects = get_subjects(course_i, sem_i)

    if subjects:
        kb = InlineKeyboardBuilder()
        for s in subjects:
            kb.button(text=s["name"], callback_data=f"lib_add:sub:{s['id']}")
        kb.adjust(2)

        await cb.message.edit_text(
            "📂 Fayl yuklamoqchi bo‘lgan faningizni tanlang.\n"
            "➕ Yangi fan ochmoqchi bo‘lsangiz fan nomini yozing (shu chatga).",
            reply_markup=kb.as_markup(),
        )
    else:
        await cb.message.edit_text(
            "Bu yerda hali fan yo‘q.\n"
            "➕ Yangi fan ochish uchun fan nomini yozing (shu chatga)."
        )
    await cb.answer()


@router.callback_query(F.data.startswith("lib_add:sub:"))
async def lib_add_existing_subject(cb: CallbackQuery, state: FSMContext):
    subject_id = int(cb.data.split(":")[-1])
    await state.update_data(subject_id=subject_id, gen_mode=False)  # ✅ oddiy
    await state.set_state(LibraryStates.waiting_files)
    await cb.message.edit_text("📎 Fayllarni yuboring (PDF/Video/Audio/Doc).")
    await cb.answer()


@router.callback_query(F.data.startswith("gen_add:sub:"))
async def gen_add_existing_subject(cb: CallbackQuery, state: FSMContext):
    subject_id = int(cb.data.split(":")[-1])
    await state.update_data(gen_subject_id=subject_id, gen_mode=True)  # ✅ general
    await state.set_state(LibraryStates.waiting_files)
    await cb.message.edit_text("📎 Umumiy kitoblar uchun fayllarni yuboring (PDF/Video/Audio/Doc/PPT).")
    await cb.answer()


# ✅ Bitta text handler: general bo'lsa general, bo'lmasa oddiy fan ochadi
@router.message(LibraryStates.general_choosing_subject, F.text, ~F.text.in_(STOP_TEXTS))
async def gen_add_new_subject_by_text(message: Message, state: FSMContext, bot: Bot, config: Config):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Nom juda qisqa. Qayta yozing.")
        return

    # GENERAL supergroupda topic ochamiz
    topic = await bot.create_forum_topic(
        chat_id=int(config.general_books_supergroup_id),
        name=f"UMUMIY | {name}",
    )

    try:
        add_general_subject(name, topic.message_thread_id)
    except Exception:
        await message.answer("❌ Bu nom avval qo‘shilgan. Boshqa nom yozing.")
        return

    row = get_general_subject_by_name(name)
    await state.update_data(gen_subject_id=int(row["id"]), gen_mode=True)
    await state.set_state(LibraryStates.waiting_files)

    await message.answer("✅ Bo‘lim yaratildi. Endi fayllarni yuboring.")

@router.message(LibraryStates.waiting_files, ~F.text)
async def lib_receive_files(message: Message, state: FSMContext, bot: Bot, config: Config):
    data = await state.get_data()

    # ===== GENERAL BOOKS MODE =====
    if data.get("gen_mode") and data.get("gen_subject_id"):
        subject_id = int(data["gen_subject_id"])

        conn = connect()
        cur = conn.cursor()
        cur.execute("SELECT topic_id FROM general_subjects WHERE id=?", (subject_id,))
        row = cur.fetchone()
        conn.close()

        if not row:
            await message.answer("❌ Umumiy bo‘lim topic topilmadi.")
            await state.clear()
            return

        topic_id = int(row["topic_id"])

        sent = await bot.copy_message(
            chat_id=int(config.general_books_supergroup_id),
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=topic_id,
            protect_content=True,
        )

        fname = (
            message.document.file_name if message.document else
            message.video.file_name if message.video else
            message.audio.file_name if message.audio else
            "media"
        )

        add_general_file(subject_id, int(sent.message_id), str(fname))
        await message.answer("✅ Umumiy kitoblarga fayl joylandi.")
        return

    # ===== NORMAL LIBRARY MODE =====
    if "subject_id" not in data:
        await message.answer("❌ Fan topilmadi. Qaytadan urinib ko‘ring.")
        await state.clear()
        return

    subject_id = int(data["subject_id"])

    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT topic_id FROM subjects WHERE id=?", (subject_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await message.answer("❌ Topic topilmadi.")
        await state.clear()
        return

    topic_id = int(row["topic_id"])

    sent = await bot.copy_message(
        chat_id=int(config.supergroup_id),
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        message_thread_id=topic_id,
        protect_content=True,
    )

    fname = (
        message.document.file_name if message.document else
        message.video.file_name if message.video else
        message.audio.file_name if message.audio else
        "media"
    )

    add_file(subject_id, int(sent.message_id), str(fname))
    await message.answer("✅ Fayl joylandi.")

#========================
@router.message(LibraryStates.choosing_subject, F.text, ~F.text.in_(STOP_TEXTS))
async def lib_add_new_subject(message: Message, state: FSMContext, bot: Bot, config: Config):
    """
    Oddiy kutubxona: kurs+semestr tanlangandan keyin fan nomini yozsa,
    supergroupda topic ochadi va DBga fan qo‘shadi.
    """
    if message.from_user.id not in config.admins:
        return

    data = await state.get_data()

    # gen rejimda bo‘lsa bu handler ishlamasin
    if data.get("gen_mode"):
        return

    if "course" not in data or "semester" not in data:
        await message.answer("❌ Kurs/semestr topilmadi. Qaytadan '➕ Fayl qo‘shish' dan boshlang.")
        await state.clear()
        return

    course = int(data["course"])
    semester = int(data["semester"])
    subject_name = message.text.strip()

    if len(subject_name) < 2:
        await message.answer("❗ Fan nomi juda qisqa. Qayta yozing.")
        return

    # topic ochamiz
    try:
        topic = await bot.create_forum_topic(
            chat_id=int(config.supergroup_id),
            name=f"{course}-kurs | {semester}-semestr | {subject_name}",
        )
    except Exception:
        await message.answer("❌ Topic ochib bo‘lmadi. Bot supergroupda adminmi va 'Manage topics' huquqi bormi?")
        return

    # DBga fan qo‘shamiz
    try:
        add_subject(course, semester, subject_name, int(topic.message_thread_id))
    except Exception:
        # agar fan nomi oldin bo‘lsa, DB xato chiqarishi mumkin
        await message.answer("❌ Bu fan nomi avval qo‘shilgan bo‘lishi mumkin. Boshqa nom yozing.")
        return

    row = get_subject_by_name(course, semester, subject_name)
    if not row:
        await message.answer("❌ Fan DBga yozildi, lekin qayta o‘qib bo‘lmadi. DB tekshiring.")
        await state.clear()
        return

    await state.update_data(subject_id=int(row["id"]), gen_mode=False)
    await state.set_state(LibraryStates.waiting_files)

    await message.answer("✅ Fan yaratildi. Endi fayllarni yuboring.")

@router.message(LibraryStates.waiting_files, F.text, ~F.text.in_(STOP_TEXTS))
async def lib_waiting_files_text(message: Message):
    await message.answer("📎 Hozir fayl qo‘shish rejimi. Fayl yuboring yoki ⬅️ ORQAGA / 🏠 ASOSIY MENYU bosing.")

# =========================
# LIBRARY: DELETE FILES
# =========================
@router.message(F.text == "🗑 Fayl o‘chirish")
async def del_file_start(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.clear()
    await state.set_state(LibraryStates.deleting_choose_course)
    await message.answer("Kursni tanlang:", reply_markup=inline_courses_with_general("lib_del"))

@router.callback_query(F.data.startswith("lib_del:course:"))
async def del_course(cb: CallbackQuery, state: FSMContext):
    course = int(cb.data.split(":")[-1])
    await state.update_data(course=course)
    await cb.message.edit_text(
        f"{course}-kurs. Semestrni tanlang:",
        reply_markup=inline_semesters("lib_del", course),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("lib_del:sem:"))
async def del_semester(cb: CallbackQuery, state: FSMContext):
    _, _, course, sem = cb.data.split(":")
    subjects = get_subjects(int(course), int(sem))

    if not subjects:
        await cb.message.edit_text("Bu kurs va semestrda fan yo‘q.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for s in subjects:
        kb.button(text=s["name"], callback_data=f"lib_del:sub:{s['id']}")
    kb.adjust(2)

    await cb.message.edit_text("📂 Fayl o‘chirmoqchi bo‘lgan fanni tanlang:", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("lib_del:sub:"))
async def del_choose_file(cb: CallbackQuery, state: FSMContext):
    subject_id = int(cb.data.split(":")[-1])
    await state.update_data(subject_id=subject_id)

    files = get_files(subject_id)
    if not files:
        await cb.message.edit_text("Bu fan ichida fayl yo‘q.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for f in files:
        kb.button(text=f["file_name"], callback_data=f"lib_del:file:{f['id']}:{f['message_id']}")
    kb.adjust(1)

    await cb.message.edit_text("🗑 O‘chirmoqchi bo‘lgan faylni tanlang:", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("lib_del:file:"))
async def del_confirm(cb: CallbackQuery, state: FSMContext):
    _, _, file_id, msg_id = cb.data.split(":")
    await state.update_data(file_id=int(file_id), msg_id=int(msg_id))

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data="lib_del:yes")
    kb.button(text="❌ Yo‘q", callback_data="lib_del:no")
    kb.adjust(2)

    await cb.message.edit_text("❗ Ushbu faylni o‘chirmoqchimisiz?", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data == "lib_del:yes")
async def del_yes(cb: CallbackQuery, state: FSMContext, bot: Bot, config: Config):
    data = await state.get_data()
    file_id = int(data["file_id"])
    msg_id = int(data["msg_id"])

    try:
        await bot.delete_message(chat_id=config.supergroup_id, message_id=msg_id)
    except Exception:
        pass

    delete_file(file_id)
    await state.clear()
    await cb.message.edit_text("✅ Fayl o‘chirildi.")
    await cb.answer()


@router.callback_query(F.data == "lib_del:no")
async def del_no(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Bekor qilindi.")
    await cb.answer()


@router.callback_query(F.data == "lib_del:general")
async def gen_del_pick_subject(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(gen_mode=True)
    subjects = get_general_subjects()

    if not subjects:
        await cb.message.edit_text("📭 Umumiy kitoblarda bo‘lim yo‘q.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for s in subjects:
        kb.button(text=s["name"], callback_data=f"gen_del:sub:{s['id']}")
    kb.adjust(2)

    await cb.message.edit_text("🗑 Umumiy kitoblar\nBo‘limni tanlang:", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("gen_del:sub:"))
async def gen_del_choose_file(cb: CallbackQuery, state: FSMContext):
    subject_id = int(cb.data.split(":")[-1])
    await state.update_data(gen_subject_id=subject_id, gen_mode=True)

    files = get_general_files(subject_id)
    if not files:
        await cb.message.edit_text("📭 Bu bo‘limda fayl yo‘q.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for f in files:
        kb.button(text=f["file_name"], callback_data=f"gen_del:file:{f['id']}:{f['message_id']}")
    kb.adjust(1)

    await cb.message.edit_text("🗑 O‘chirmoqchi bo‘lgan faylni tanlang:", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("gen_del:file:"))
async def gen_del_confirm(cb: CallbackQuery, state: FSMContext):
    _, _, file_id, msg_id = cb.data.split(":")
    await state.update_data(gen_file_id=int(file_id), gen_msg_id=int(msg_id), gen_mode=True)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data="gen_del:yes")
    kb.button(text="❌ Yo‘q", callback_data="gen_del:no")
    kb.adjust(2)

    await cb.message.edit_text("❗ Shu faylni o‘chirasizmi?", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data == "gen_del:yes")
async def gen_del_yes(cb: CallbackQuery, state: FSMContext, bot: Bot, config: Config):
    data = await state.get_data()
    file_id = int(data["gen_file_id"])
    msg_id = int(data["gen_msg_id"])

    try:
        await bot.delete_message(chat_id=int(config.general_books_supergroup_id), message_id=msg_id)
    except Exception:
        pass

    delete_general_file(file_id)
    await state.clear()
    await cb.message.edit_text("✅ Umumiy kitoblardan fayl o‘chirildi.")
    await cb.answer()


@router.callback_query(F.data == "gen_del:no")
async def gen_del_no(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Bekor qilindi.")
    await cb.answer()


# =========================
# LIBRARY: DELETE SUBJECT (FAN O'CHIRISH)
# =========================
@router.message(F.text == "🗑 Fan o‘chirish")
async def del_subject_start(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.clear()
    await state.set_state(LibraryStates.subj_del_choose_course)
    await message.answer("🗑 Fan o‘chirish\nKursni tanlang:", reply_markup=inline_courses_with_general("lib_subdel"))


@router.callback_query(F.data.startswith("lib_subdel:course:"))
async def del_subject_course(cb: CallbackQuery, state: FSMContext):
    course = int(cb.data.split(":")[-1])
    await state.update_data(course=course)
    await state.set_state(LibraryStates.subj_del_choose_semester)
    await cb.message.edit_text(
        f"🗑 Fan o‘chirish\n{course}-kurs. Semestrni tanlang:",
        reply_markup=inline_semesters("lib_subdel", course),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("lib_subdel:sem:"))
async def del_subject_sem(cb: CallbackQuery, state: FSMContext):
    _, _, course, sem = cb.data.split(":")
    course_i = int(course)
    sem_i = int(sem)

    await state.update_data(semester=sem_i)
    await state.set_state(LibraryStates.subj_del_choose_subject)

    subjects = get_subjects(course_i, sem_i)
    if not subjects:
        await cb.message.edit_text("Bu kurs va semestrda fan yo‘q.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for s in subjects:
        kb.button(text=s["name"], callback_data=f"lib_subdel:sub:{s['id']}")
    kb.adjust(2)

    await cb.message.edit_text("🗑 Qaysi fanni o‘chirasiz?", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("lib_subdel:sub:"))
async def del_subject_confirm(cb: CallbackQuery, state: FSMContext):
    subject_id = int(cb.data.split(":")[-1])
    await state.update_data(subject_id=subject_id)
    await state.set_state(LibraryStates.subj_del_confirm)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data="lib_subdel:yes")
    kb.button(text="❌ Yo‘q", callback_data="lib_subdel:no")
    kb.adjust(2)

    await cb.message.edit_text(
        "❗ Ushbu fanni va ichidagi barcha fayllarni o‘chirasizmi?",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


@router.callback_query(F.data == "lib_subdel:yes")
async def del_subject_yes(cb: CallbackQuery, state: FSMContext, bot: Bot, config: Config):
    data = await state.get_data()
    subject_id = int(data["subject_id"])

    # topic_id va fayl message_id larni olamiz
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT topic_id FROM subjects WHERE id=?", (subject_id,))
    srow = cur.fetchone()
    conn.close()

    files = get_files(subject_id)

    # supergroupdagi fayl-xabarlarni o'chiramiz
    for f in files:
        try:
            await bot.delete_message(chat_id=int(config.supergroup_id), message_id=int(f["message_id"]))
        except Exception:
            pass

    # forum topicni o'chiramiz (bo'lsa)
    try:
        if srow and srow["topic_id"]:
            await bot.delete_forum_topic(
                chat_id=int(config.supergroup_id),
                message_thread_id=int(srow["topic_id"])
            )
    except Exception:
        pass

    # DB dan fan + fayllar yozuvini o'chiramiz
    delete_subject(subject_id)

    await state.clear()
    await cb.message.edit_text("✅ Fan o‘chirildi.")
    await cb.answer()


@router.callback_query(F.data == "lib_subdel:no")
async def del_subject_no(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Bekor qilindi.")
    await cb.answer()

@router.callback_query(F.data == "lib_subdel:general")
async def gen_subdel_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(gen_mode=True)

    subjects = get_general_subjects()
    if not subjects:
        await cb.message.edit_text("📭 Umumiy kitoblarda bo‘lim yo‘q.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for s in subjects:
        kb.button(text=s["name"], callback_data=f"gen_subdel:sub:{s['id']}")
    kb.adjust(2)

    await cb.message.edit_text("🗑 Umumiy kitoblar\nQaysi bo‘limni o‘chirasiz?", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("gen_subdel:sub:"))
async def gen_subdel_confirm(cb: CallbackQuery, state: FSMContext):
    sid = int(cb.data.split(":")[-1])
    await state.update_data(gen_subject_id=sid, gen_mode=True)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data="gen_subdel:yes")
    kb.button(text="❌ Yo‘q", callback_data="gen_subdel:no")
    kb.adjust(2)

    await cb.message.edit_text("❗ Bo‘lim (topic) va ichidagi barcha fayllar o‘chadi. Rozimisiz?", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data == "gen_subdel:yes")
async def gen_subdel_yes(cb: CallbackQuery, state: FSMContext, bot: Bot, config: Config):
    data = await state.get_data()
    subject_id = int(data["gen_subject_id"])

    # topic_id olish
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT topic_id FROM general_subjects WHERE id=?", (subject_id,))
    row = cur.fetchone()
    conn.close()

    # fayl-xabarlarni o‘chirish
    files = get_general_files(subject_id)
    for f in files:
        try:
            await bot.delete_message(chat_id=int(config.general_books_supergroup_id), message_id=int(f["message_id"]))
        except Exception:
            pass

    # topicni o‘chirish
    try:
        if row and row["topic_id"]:
            await bot.delete_forum_topic(
                chat_id=int(config.general_books_supergroup_id),
                message_thread_id=int(row["topic_id"])
            )
    except Exception:
        pass

    # DBdan o‘chirish
    delete_general_subject(subject_id)

    await state.clear()
    await cb.message.edit_text("✅ Umumiy kitoblar bo‘limi o‘chirildi.")
    await cb.answer()


@router.callback_query(F.data == "gen_subdel:no")
async def gen_subdel_no(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Bekor qilindi.")
    await cb.answer()

# =========================
# EXAM: ADD/DELETE
# =========================
@router.message(F.text == "➕ Imtihon fayl qo‘shish")
async def exam_add_start(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.clear()
    await state.set_state(ExamStates.choosing_course)
    await message.answer("📄 Imtihon: Kursni tanlang:", reply_markup=inline_courses("exam_add"))


@router.callback_query(F.data.startswith("exam_add:course:"))
async def exam_add_course(cb: CallbackQuery, state: FSMContext):
    course = int(cb.data.split(":")[-1])
    await state.update_data(course=course)
    await state.set_state(ExamStates.choosing_semester)
    await cb.message.edit_text(
        f"📄 Imtihon: {course}-kurs. Semestrni tanlang:",
        reply_markup=inline_semesters("exam_add", course),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("exam_add:sem:"))
async def exam_add_sem(cb: CallbackQuery, state: FSMContext):
    _, _, course, sem = cb.data.split(":")
    course_i = int(course)
    sem_i = int(sem)

    await state.update_data(semester=sem_i)
    await state.set_state(ExamStates.choosing_subject)

    subjects = get_exam_subjects(course_i, sem_i)

    if subjects:
        kb = InlineKeyboardBuilder()
        for s in subjects:
            kb.button(text=s["name"], callback_data=f"exam_add:sub:{s['id']}")
        kb.adjust(2)
        await cb.message.edit_text(
            "📄 Imtihon: qaysi fan?\n"
            "➕ Yangi fan ochish uchun fan nomini yozing (shu chatga).",
            reply_markup=kb.as_markup(),
        )
    else:
        await cb.message.edit_text(
            "Bu kurs+semestrda hali imtihon fanlari yo‘q.\n"
            "➕ Fan nomini yozing (shu chatga)."
        )
    await cb.answer()


@router.callback_query(F.data.startswith("exam_add:sub:"))
async def exam_add_existing_subject(cb: CallbackQuery, state: FSMContext):
    subject_id = int(cb.data.split(":")[-1])
    await state.update_data(subject_id=subject_id)
    await state.set_state(ExamStates.waiting_files)
    await cb.message.edit_text("📎 Imtihon fayllarini yuboring (PDF/Doc/Media).")
    await cb.answer()


@router.message(ExamStates.choosing_subject, F.text, ~F.text.in_(STOP_TEXTS))
async def exam_add_new_subject(message: Message, state: FSMContext, bot: Bot, config: Config):
    data = await state.get_data()
    course = int(data["course"])
    semester = int(data["semester"])
    subject_name = message.text.strip()

    topic = await bot.create_forum_topic(
        chat_id=config.exam_supergroup_id,
        name=f"IMTIHON | {course}-kurs | {semester}-semestr | {subject_name}",
    )

    add_exam_subject(course, semester, subject_name, topic.message_thread_id)

    row = get_exam_subject_by_name(course, semester, subject_name)
    await state.update_data(subject_id=row["id"])
    await state.set_state(ExamStates.waiting_files)

    await message.answer("✅ Imtihon fani yaratildi. Endi fayllarni yuboring.")


@router.message(ExamStates.waiting_files, ~F.text)
async def exam_receive_files(message: Message, state: FSMContext, bot: Bot, config: Config):
    data = await state.get_data()
    subject_id = int(data["subject_id"])

    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT topic_id FROM exam_subjects WHERE id=?", (subject_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await message.answer("❌ Topic topilmadi. Qaytadan urinib ko‘ring.")
        await state.clear()
        return

    topic_id = row["topic_id"]

    sent = await bot.copy_message(
        chat_id=config.exam_supergroup_id,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        message_thread_id=topic_id,
        protect_content=True,
    )

    fname = (
        message.document.file_name if message.document else
        message.video.file_name if message.video else
        message.audio.file_name if message.audio else
        "media"
    )

    add_exam_file(subject_id, sent.message_id, str(fname))
    await message.answer("✅ Imtihon fayli joylandi. Yana fayl yuborishingiz mumkin.")


@router.message(ExamStates.waiting_files, F.text, ~F.text.in_(STOP_TEXTS))
async def exam_waiting_files_text(message: Message):
    await message.answer("📎 Hozir imtihon fayl qo‘shish rejimi. Fayl yuboring yoki ⬅️ ORQAGA / 🏠 ASOSIY MENYU bosing.")


@router.message(F.text == "🗑 Imtihon fanini o‘chirish")
async def exam_del_start(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.clear()
    await state.set_state(ExamStates.deleting_choose_course)
    await message.answer("🗑 Imtihon fanini o‘chirish\nKursni tanlang:", reply_markup=inline_courses("exam_del"))


@router.callback_query(F.data.startswith("exam_del:course:"))
async def exam_del_course(cb: CallbackQuery, state: FSMContext):
    course = int(cb.data.split(":")[-1])
    await state.update_data(course=course)
    await state.set_state(ExamStates.deleting_choose_semester)
    await cb.message.edit_text(
        f"🗑 Imtihon: {course}-kurs. Semestrni tanlang:",
        reply_markup=inline_semesters("exam_del", course),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("exam_del:sem:"))
async def exam_del_sem(cb: CallbackQuery, state: FSMContext):
    _, _, course, sem = cb.data.split(":")
    subjects = get_exam_subjects(int(course), int(sem))
    if not subjects:
        await cb.message.edit_text("Bu kurs va semestrda imtihon fanlari yo‘q.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for s in subjects:
        kb.button(text=s["name"], callback_data=f"exam_del:sub:{s['id']}")
    kb.adjust(2)

    await cb.message.edit_text("🗑 Qaysi imtihon fanini o‘chirasiz?", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("exam_del:sub:"))
async def exam_del_confirm(cb: CallbackQuery, state: FSMContext):
    subject_id = int(cb.data.split(":")[-1])
    await state.update_data(subject_id=subject_id)
    await state.set_state(ExamStates.deleting_confirm)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data="exam_del:yes")
    kb.button(text="❌ Yo‘q", callback_data="exam_del:no")
    kb.adjust(2)

    await cb.message.edit_text(
        "❗ Shu fanni va ichidagi barcha imtihon fayllarini o‘chirasizmi?",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


@router.callback_query(F.data == "exam_del:yes")
async def exam_del_yes(cb: CallbackQuery, state: FSMContext, bot: Bot, config: Config):
    data = await state.get_data()
    subject_id = int(data["subject_id"])

    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT topic_id FROM exam_subjects WHERE id=?", (subject_id,))
    row = cur.fetchone()
    conn.close()

    files = get_exam_files(subject_id)

    for f in files:
        try:
            await bot.delete_message(chat_id=config.exam_supergroup_id, message_id=int(f["message_id"]))
        except Exception:
            pass

    try:
        if row and row["topic_id"]:
            await bot.delete_forum_topic(chat_id=config.exam_supergroup_id, message_thread_id=int(row["topic_id"]))
    except Exception:
        pass

    delete_exam_subject(subject_id)

    await state.clear()
    await cb.message.edit_text("✅ Imtihon fani va barcha fayllari o‘chirildi.")
    await cb.answer()


@router.callback_query(F.data == "exam_del:no")
async def exam_del_no(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Bekor qilindi.")
    await cb.answer()


# =========================
# TESTS: ADD/DEL
# =========================
@router.message(F.text == "📝 Test boshqaruvi")
async def admin_test_root(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.clear()

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Test qo‘shish", callback_data="test:add")
    kb.button(text="🗑 Test o‘chirish", callback_data="test:del")
    kb.adjust(1)

    await message.answer("📝 Test boshqaruvi\nAmalni tanlang:", reply_markup=kb.as_markup())


@router.callback_query(F.data == "test:add")
async def test_add_start(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(TestStates.add_choose_course)
    await cb.message.edit_text("➕ Test qo‘shish\nKursni tanlang:", reply_markup=inline_courses("test_add"))
    await cb.answer()


@router.callback_query(F.data.startswith("test_add:course:"))
async def test_add_course(cb: CallbackQuery, state: FSMContext):
    course = int(cb.data.split(":")[-1])
    await state.update_data(course=course)
    await state.set_state(TestStates.add_choose_semester)
    await cb.message.edit_text(
        f"➕ Test qo‘shish\n{course}-kurs. Semestrni tanlang:",
        reply_markup=inline_semesters("test_add", course)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("test_add:sem:"))
async def test_add_sem(cb: CallbackQuery, state: FSMContext):
    _, _, course, sem = cb.data.split(":")
    await state.update_data(semester=int(sem))
    await state.set_state(TestStates.add_waiting_name)
    await cb.message.edit_text("Test nomini yozing (masalan: Anatomiya 2026):")
    await cb.answer()


@router.message(TestStates.add_waiting_name, F.text, ~F.text.in_(STOP_TEXTS))
async def test_add_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 3:
        await message.answer("Test nomi juda qisqa. Qayta yozing.")
        return

    await state.update_data(test_name=name)
    await state.set_state(TestStates.add_waiting_file)
    await message.answer("Endi test faylni yuboring (.docx yoki .txt).")


@router.message(TestStates.add_waiting_file)
async def test_add_file(message: Message, state: FSMContext):
    data = await state.get_data()
    course = int(data["course"])
    semester = int(data["semester"])
    test_name = data["test_name"]

    if not message.document:
        await message.answer("❌ Faqat .docx yoki .txt fayl yuboring.")
        return

    file_name = (message.document.file_name or "").lower()
    if not (file_name.endswith(".docx") or file_name.endswith(".txt")):
        await message.answer("❌ Faqat .docx yoki .txt fayl yuboring.")
        return

    test_id = add_test(course, semester, test_name)

    tg_file = await message.bot.get_file(message.document.file_id)
    file_bytes = await message.bot.download_file(tg_file.file_path)

    safe_name = test_name.replace(" ", "_")
    ext = ".docx" if file_name.endswith(".docx") else ".txt"
    saved_filename = f"test_{test_id}_{safe_name}{ext}"
    save_path = RAW_TEST_DIR / saved_filename

    with open(save_path, "wb") as f:
        f.write(file_bytes.read())

    update_test_source_file(test_id, saved_filename)

    if ext == ".txt":
        text = save_path.read_text(encoding="utf-8", errors="ignore")
    else:
        doc = Document(save_path)
        text = "\n".join(p.text for p in doc.paragraphs)

    questions = parse_questions_from_text(text)

    fail = 0
    for qtext, options, correct_index in questions:
        try:
            add_question(test_id, qtext, options, correct_index)
        except Exception:
            fail += 1

    db_count = count_questions(test_id)

    await state.clear()
    await message.answer(
        f"✅ Test qo‘shildi\n"
        f"📘 Nomi: {test_name}\n"
        f"🧾 Parse savollar: {len(questions)} ta\n"
        f"💾 DBga yozilgan: {db_count} ta\n"
        f"⚠️ Yozilmagan: {fail} ta",
        reply_markup=admin_main_menu()
    )


@router.callback_query(F.data == "test:del")
async def test_del_start(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(TestStates.del_choose_course)
    await cb.message.edit_text("🗑 Test o‘chirish\nKursni tanlang:", reply_markup=inline_courses("test_del"))
    await cb.answer()


@router.callback_query(F.data.startswith("test_del:course:"))
async def test_del_course(cb: CallbackQuery, state: FSMContext):
    course = int(cb.data.split(":")[-1])
    await state.update_data(course=course)
    await state.set_state(TestStates.del_choose_semester)
    await cb.message.edit_text(
        f"🗑 Test o‘chirish\n{course}-kurs. Semestrni tanlang:",
        reply_markup=inline_semesters("test_del", course)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("test_del:sem:"))
async def test_del_sem(cb: CallbackQuery, state: FSMContext):
    _, _, course, sem = cb.data.split(":")
    tests = list_tests(int(course), int(sem))
    if not tests:
        await cb.message.edit_text("Bu kurs va semestrda test yo‘q.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for t in tests:
        kb.button(text=t["name"], callback_data=f"test_del:pick:{t['id']}")
    kb.adjust(1)

    await cb.message.edit_text("🗑 Qaysi testni o‘chirasiz? Tanlang:", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("test_del:pick:"))
async def test_del_pick(cb: CallbackQuery, state: FSMContext):
    test_id = int(cb.data.split(":")[-1])
    await state.update_data(test_id=test_id)
    await state.set_state(TestStates.del_confirm)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data="test_del:yes")
    kb.button(text="❌ Yo‘q", callback_data="test_del:no")
    kb.adjust(2)

    await cb.message.edit_text("❗ Testni o‘chirishga rozimisiz?", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data == "test_del:yes")
async def test_del_yes(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    delete_test(int(data["test_id"]))
    await state.clear()
    await cb.message.edit_text("✅ Test o‘chirildi.")
    await cb.answer()


@router.callback_query(F.data == "test_del:no")
async def test_del_no(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Bekor qilindi. Test o‘chmadi.")
    await cb.answer()


# =========================
# SETTINGS
# =========================
@router.message(F.text == "🛠 Bot sozlamalari")
async def admin_bot_settings(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return
    enabled = get_bool_setting("tests_enabled", "1")
    status = "✅ YOQILGAN" if enabled else "⛔ O‘CHIRILGAN"
    await message.answer(
        f"🛠 Bot sozlamalari\n\n📝 Testlar holati: {status}",
        reply_markup=_tests_toggle_markup(enabled)
    )


@router.callback_query(F.data == "settings:toggle_tests")
async def toggle_tests(cb: CallbackQuery, config: Config):
    if cb.from_user.id not in config.admins:
        await cb.answer("Ruxsat yo‘q", show_alert=True)
        return

    enabled = toggle_bool_setting("tests_enabled", "1")
    status = "✅ YOQILGAN" if enabled else "⛔ O‘CHIRILGAN"

    await cb.message.edit_text(
        f"🛠 Testlar holati: {status}",
        reply_markup=_tests_toggle_markup(enabled)
    )
    await cb.answer("✅ Saqlandi")


@router.message(F.text == "⭐ Obuna sozlamalari")
async def admin_sub_settings(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return

    sub_enabled = get_bool_setting("sub_enabled", "1")
    click_enabled = get_bool_setting("sub_pay_click_enabled", "1")
    stars_enabled = get_bool_setting("sub_pay_stars_enabled", "0")
    referral_enabled = get_bool_setting("sub_referral_enabled", "1")
    channel_enabled = get_bool_setting("sub_channel_enabled", "0")

    await message.answer(
        "⭐ Obuna sozlamalari\n\n"
        "Qaysi usullar userlarga ko‘rinsin? (✅ yoqilgan / ⛔ o‘chiq)\n",
        reply_markup=inline_sub_settings(
            sub_enabled, click_enabled, stars_enabled, referral_enabled, channel_enabled
        )
    )


@router.callback_query(F.data.startswith("subset:toggle:"))
async def toggle_sub_setting(cb: CallbackQuery, config: Config):
    if cb.from_user.id not in config.admins:
        await cb.answer("Ruxsat yo‘q", show_alert=True)
        return

    key = cb.data.split(":")[-1]
    allowed = {
        "sub_enabled",
        "sub_pay_click_enabled",
        "sub_pay_stars_enabled",
        "sub_referral_enabled",
        "sub_channel_enabled",
    }
    if key not in allowed:
        await cb.answer("Noma’lum sozlama", show_alert=True)
        return

    toggle_bool_setting(key, "0")

    sub_enabled = get_bool_setting("sub_enabled", "1")
    click_enabled = get_bool_setting("sub_pay_click_enabled", "1")
    stars_enabled = get_bool_setting("sub_pay_stars_enabled", "0")
    referral_enabled = get_bool_setting("sub_referral_enabled", "1")
    channel_enabled = get_bool_setting("sub_channel_enabled", "0")

    await cb.message.edit_reply_markup(
        reply_markup=inline_sub_settings(
            sub_enabled, click_enabled, stars_enabled, referral_enabled, channel_enabled
        )
    )
    await cb.answer("✅ Saqlandi")


# =========================
# BROADCAST PANEL
# =========================
@router.message(F.text == "📢 Post yuborish")
async def broadcast_panel(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.clear()
    await message.answer("📢 Broadcast panel\nAmalni tanlang:", reply_markup=admin_broadcast_menu())


@router.message(F.text == "📢 Post jo‘natish")
async def broadcast_start(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.set_state(BroadcastStates.waiting_post)
    await message.answer(
        "📢 Post yuborish\n\nYubormoqchi bo‘lgan postni yuboring (text/media/poll/forward).",
        reply_markup=admin_broadcast_menu()
    )

# ===== BROADCAST RATE LIMIT =====
BATCH_SIZE = 25   # 20–30 oralig'ida
PAUSE_SEC = 1.2   # har 25 ta yuborishda pauza

@router.message(BroadcastStates.waiting_post)
async def broadcast_send_any(message: Message, state: FSMContext, bot: Bot):
    # 1) userlar ro'yxati
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = [int(r[0]) for r in cur.fetchall()]
    conn.close()

    if not users:
        await state.clear()
        await message.answer("📭 Userlar topilmadi.", reply_markup=admin_broadcast_menu())
        return

    # 2) broadcast id (keyin o'chirish uchun log)
    broadcast_id = create_broadcast(message.from_user.id)

    # 3) poll bo'lsa: oldindan row yaratamiz
    poll_row_id = None
    poll_question = None
    poll_options = None
    allows_multi = False

    is_poll = bool(message.poll)
    if is_poll:
        poll_question = message.poll.question
        poll_options = [o.text for o in message.poll.options]
        allows_multi = bool(message.poll.allows_multiple_answers)
        poll_row_id = create_poll_row(broadcast_id, poll_question, poll_options)

    sent = 0
    failed = 0
    flood_waits = 0

    # 4) yuborish
    for i, uid in enumerate(users, start=1):
        try:
            if is_poll and poll_row_id and poll_question and poll_options:
                # ✅ poll: alohida yuboriladi (copy_message pollga to'g'ri kelmaydi)
                m = await bot.send_poll(
                    chat_id=uid,
                    question=poll_question,
                    options=poll_options,
                    is_anonymous=False,  # ✅ statistika yig'ish uchun shart
                    allows_multiple_answers=allows_multi,
                )

                # log (keyin delete uchun)
                log_broadcast_message(broadcast_id, uid, uid, int(m.message_id))

                # poll instance (poll_id har userda boshqacha bo'ladi!)
                save_poll_instance(m.poll.id, poll_row_id, uid, int(m.message_id))

            else:
                # ✅ oddiy post/media: inline tugma ham ketsin
                m = await bot.copy_message(
                    chat_id=uid,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                    reply_markup=message.reply_markup
                )
                log_broadcast_message(broadcast_id, uid, uid, int(m.message_id))

            sent += 1

        except TelegramRetryAfter as e:
            # FloodWait: ko'rsatilgan vaqt + 1s kutamiz
            flood_waits += 1
            await asyncio.sleep(int(getattr(e, "retry_after", 1)) + 1)
            failed += 1

        except Exception:
            failed += 1

        # ✅ batch pause (har 25 ta yuborishda)
        if i % BATCH_SIZE == 0:
            await asyncio.sleep(PAUSE_SEC)

    # 5) yakun
    await state.clear()
    await message.answer(
        "✅ Broadcast yakunlandi.\n"
        f"🆔 Broadcast ID: {broadcast_id}\n"
        f"✅ Yuborildi: {sent}\n"
        f"⚠️ Xato: {failed}\n"
        f"⏳ FloodWait: {flood_waits}",
        reply_markup=admin_broadcast_menu()
    )

@router.message(F.text == "🗑 Jo‘natilgan postlarni o‘chirish")
async def admin_broadcast_delete_list(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return

    items = list_broadcasts(limit=20)
    if not items:
        await message.answer("📭 O‘chirish uchun broadcast topilmadi.", reply_markup=admin_broadcast_menu())
        return

    kb = InlineKeyboardBuilder()
    for b in items:
        kb.button(text=f"🗑 ID {b['id']} | {b['created_at']}", callback_data=f"bdel:{b['id']}")
    kb.adjust(1)

    await message.answer("🗑 Qaysi broadcastni o‘chirasiz?", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("bdel:"))
async def admin_broadcast_delete_do(cb: CallbackQuery, bot: Bot, config: Config):
    if cb.from_user.id not in config.admins:
        await cb.answer("Ruxsat yo‘q", show_alert=True)
        return

    bid = int(cb.data.split(":")[-1])
    rows = list_broadcast_messages(bid)

    deleted = 0
    failed = 0

    for r in rows:
        try:
            await bot.delete_message(int(r["chat_id"]), int(r["message_id"]))
            deleted += 1
        except Exception:
            failed += 1

    delete_broadcast(bid)

    await cb.message.answer(
        f"✅ Broadcast o‘chirildi.\n🆔 ID: {bid}\n🗑 O‘chirildi: {deleted}\n⚠️ O‘chmadi: {failed}",
        reply_markup=admin_broadcast_menu()
    )
    await cb.answer()


@router.message(F.text == "📊 Poll natijalarini ko‘rish")
async def admin_poll_list(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return

    items = list_polls(limit=20)
    if not items:
        await message.answer("📭 Hozircha poll statistika yo‘q.", reply_markup=admin_broadcast_menu())
        return

    kb = InlineKeyboardBuilder()
    for p in items:
        kb.button(text=f"#{p['id']} | {p['created_at']}", callback_data=f"pollstat:{p['id']}")
    kb.adjust(1)

    await message.answer("📊 Qaysi poll natijasini ko‘rasiz?", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("pollstat:"))
async def admin_poll_stat(cb: CallbackQuery, config: Config):
    if cb.from_user.id not in config.admins:
        await cb.answer("Ruxsat yo‘q", show_alert=True)
        return

    poll_row_id = int(cb.data.split(":")[-1])
    res = get_poll_summary(poll_row_id)
    if not res:
        await cb.message.answer("❌ Poll topilmadi.", reply_markup=admin_broadcast_menu())
        await cb.answer()
        return

    question, options, counts = res
    total = sum(counts)

    text = f"📊 Poll natijasi (ID: {poll_row_id})\n\n❓ {question}\n\n"
    for opt, c in zip(options, counts):
        text += f"• {opt} — {c}\n"
    text += f"\n👥 Jami ovozlar: {total}"

    await cb.message.answer(text, reply_markup=admin_broadcast_menu())
    await cb.answer()


@router.message(F.text == "🧹 Statistika (poll)ni tozalash")
async def admin_clear_poll_stats(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return
    clear_poll_stats()
    await message.answer("✅ Poll statistikalari tozalandi.", reply_markup=admin_broadcast_menu())


@router.message(F.text.startswith("/pollstat"))
async def poll_stat_cmd(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Foydalanish:\n/pollstat <poll_id>")
        return

    poll_row_id = int(parts[1])
    res = get_poll_summary(poll_row_id)

    if not res:
        await message.answer("❌ Poll topilmadi.")
        return

    q, opts, counts = res
    total = sum(counts)

    text = f"📊 POLL NATIJASI\n\n❓ {q}\n\n"
    for i, (opt, c) in enumerate(zip(opts, counts), start=1):
        percent = (c / total * 100) if total > 0 else 0
        text += f"{i}) {opt}\n   🗳 {c} ta ({percent:.1f}%)\n\n"
    text += f"📌 Jami ovoz: {total}"

    await message.answer(text)


# =========================
# FEEDBACK
# =========================
@router.message(F.text == "📩 Userlardan xabarlar")
async def admin_feedback_root(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return
    await message.answer("📩 Userlardan xabarlar", reply_markup=admin_feedback_menu())


@router.message(F.text == "👀 Xabarlarni ko‘rish")
async def admin_feedback_view(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return

    items = list_feedback(limit=50)
    if not items:
        await message.answer("📭 Hozircha xabarlar yo‘q.", reply_markup=admin_feedback_menu())
        return

    text = "📩 So‘nggi xabarlar:\n\n"
    for it in items:
        text += (
            f"🕒 {it['created_at']}\n"
            f"👤 @{it.get('username','')}\n"
            f"🆔 ID: {it['user_id']}\n"
            f"💬 {it['text']}\n"
            f"{'-'*24}\n"
        )

    await message.answer(text, reply_markup=admin_feedback_menu())


@router.message(F.text == "🗑 Xabarlarni o‘chirish")
async def admin_feedback_clear(message: Message, config: Config):
    if message.from_user.id not in config.admins:
        return
    _clear_feedback_db()
    await message.answer("✅ Barcha user xabarlari o‘chirildi.", reply_markup=admin_feedback_menu())


# =========================
# CLEAN USER CHAT
# =========================
@router.message(F.text == "🧹 User chatini tozalash")
async def clear_chat_root(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.clear()
    await message.answer("🧹 Chat tozalash menyusi:", reply_markup=admin_clear_chat_menu())


@router.message(F.text == "🧹 1 ta userni tozalash")
async def clear_one_user_start(message: Message, state: FSMContext, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.set_state(ClearChatStates.waiting_user_id)
    await message.answer("🧹 1 ta userni tozalash\n\nUser ID yuboring (faqat raqam):", reply_markup=admin_clear_chat_menu())


@router.message(F.text == "🧹 Umumiy chat tozalash")
async def clear_all_users_chat(message: Message, state: FSMContext, bot: Bot, config: Config):
    if message.from_user.id not in config.admins:
        return
    await state.clear()

    rows = _get_all_bot_messages()
    if not rows:
        await message.answer("📭 Hozir bot yuborgan xabarlar logi bo‘sh.", reply_markup=admin_clear_chat_menu())
        return

    deleted = 0
    failed = 0
    cleaned_users = set()

    for r in rows:
        # sqlite.Row bo'lishi mumkin, dict ham bo'lishi mumkin
        uid = int(r["user_id"]) if isinstance(r, (dict,)) or hasattr(r, "__getitem__") else int(r[0])
        cleaned_users.add(uid)

        chat_id = int(r["chat_id"])
        msg_id = int(r["message_id"])

        try:
            await bot.delete_message(chat_id, msg_id)
            deleted += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(int(e.retry_after) + 1)
            try:
                await bot.delete_message(chat_id, msg_id)
                deleted += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

        if (deleted + failed) % 25 == 0:
            await asyncio.sleep(0.5)

    _clear_all_bot_messages()

    for uid in cleaned_users:
        await _send_user_menu_after_clean(bot, uid)

    await message.answer(
        f"✅ Umumiy tozalash tugadi.\n"
        f"🗑 O‘chirildi: {deleted}\n"
        f"⚠️ O‘chmadi: {failed}\n\n"
        f"Eslatma: faqat bot yuborgan xabarlar o‘chadi.",
        reply_markup=admin_clear_chat_menu()
    )


@router.message(ClearChatStates.waiting_user_id, F.text, ~F.text.in_(STOP_TEXTS))
async def clear_chat_execute(message: Message, state: FSMContext, bot: Bot, config: Config):
    if message.from_user.id not in config.admins:
        return

    if not message.text.isdigit():
        await message.answer("❌ Noto‘g‘ri ID. Raqam kiriting.", reply_markup=admin_clear_chat_menu())
        return

    user_id = int(message.text)

    rows = get_bot_messages(user_id)
    deleted = 0
    failed = 0

    for row in rows:
        try:
            await bot.delete_message(chat_id=int(row["chat_id"]), message_id=int(row["message_id"]))
            deleted += 1
        except Exception:
            failed += 1

    clear_bot_messages(user_id)
    await _send_user_menu_after_clean(bot, user_id)

    await state.clear()
    await message.answer(
        f"✅ Tozalandi.\n🗑 O‘chirildi: {deleted}\n⚠️ O‘chmadi: {failed}",
        reply_markup=admin_clear_chat_menu()
    )
