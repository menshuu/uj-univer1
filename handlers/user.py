# handlers/user.py

import asyncio
import time
import json


from keyboards import inline_courses_with_general, general_books_user_menu
from db import get_general_subjects, get_general_files, search_general
from db import search_general_subjects, search_general_files

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import PollAnswer
from db import upsert_poll_vote, get_poll_row_id_by_poll_id

from db import is_user_blocked
from keyboards import blocked_user_menu

from helpers.tg import answer_and_log, copy_to_user_and_log
from config import Config
from keyboards import user_main_menu, back_menu, inline_courses, inline_semesters
from states import FeedbackStates

def rget(row, key, default=None):
    try:
        return row[key]
    except Exception:
        return default

from db import (
    # subscription + settings
    get_bool_setting, is_sub_active,

    # tests enabled
    is_tests_enabled,

    # feedback + users
    save_feedback, upsert_user,

    # library
    get_subjects, get_files,

    # exams
    get_exam_subjects, get_exam_files,

    # tests
    list_tests,
    create_test_session, get_session, set_session_messages,
    get_session_question, count_session_questions,
    save_answer, finish_session,
    connect,
)

router = Router()

def row_to_dict(row):
    # sqlite3.Row -> dict
    try:
        return dict(row)
    except Exception:
        return row  # dict bo'lsa o'zini qaytaradi

def _advance_session(session_id: int, is_correct: int):
    # save_answer current_indexni oshirmasa ham, shu yerda oshiramiz
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE test_sessions
        SET current_index = COALESCE(current_index, 0) + 1,
            correct_count = COALESCE(correct_count, 0) + ?
        WHERE id = ?
    """, (int(is_correct), int(session_id)))
    conn.commit()
    conn.close()

class GeneralSearchStates(StatesGroup):
    waiting_query = State()

# session_id -> asyncio.Task
TIMER_TASKS: dict[int, asyncio.Task] = {}

SEP_LINE = "——————————————"

# =========================
# GUARDS (BLOCK + SUBSCRIPTION + TESTS)
# =========================
async def guard_blocked(obj) -> bool:
    uid = obj.from_user.id
    if is_user_blocked(uid):
        text = "⛔ Siz blocklangansiz. Faqat '💬 SHIKOYAT VA TAKLIFLAR' orqali yozishingiz mumkin."
        if isinstance(obj, CallbackQuery):
            await obj.answer(text, show_alert=True)
            try:
                await obj.message.answer(text, reply_markup=blocked_user_menu())
            except Exception:
                pass
        else:
            await obj.answer(text, reply_markup=blocked_user_menu())
        return False
    return True


async def guard_subscription(obj) -> bool:
    """
    sub_enabled=1 bo'lsa va userda obuna aktiv bo'lmasa -> blok.
    Adminlar doim o'tadi.
    Blocklangan userlar esa /start va menyuda bloklangan rejimga tushadi (common.py),
    bu yerda ham xavfsizlik uchun tekshirib qo'yamiz.
    """
    # 1) blocked guard
    ok = await guard_blocked(obj)
    if not ok:
        return False

    # 2) subscription guard
    cfg: Config | None = getattr(obj, "config", None)  # odatda yo‘q, shunchaki ehtiyot
    # admin checkni ko‘pchilik joyda config orqali qilishadi,
    # lekin bu guard ichida config har doim kelmasligi mumkin.
    # Shuning uchun adminlarni bu guard tashqarisida ham tekshirayotgan bo‘lishingiz mumkin.
    # Bu yerda esa faqat obuna yoqilganligini tekshiramiz.
    sub_enabled = get_bool_setting("sub_enabled", "1")
    if not sub_enabled:
        return True

    # obuna tekshiruvi
    # is_sub_active() sizning db.py dagi mavjud funksiyangiz bo‘lishi kerak
    if is_sub_active(obj.from_user.id):
        return True

    text = "⭐ Botdan foydalanish uchun obuna kerak. (Obuna aktiv emas)"
    if isinstance(obj, CallbackQuery):
        await obj.answer(text, show_alert=True)
        try:
            await obj.message.answer(text, reply_markup=back_menu())
        except Exception:
            pass
    else:
        await obj.answer(text, reply_markup=back_menu())
    return False


async def guard_tests_entry(obj) -> bool:
    """
    tests_enabled=0 bo'lsa:
      - testga KIRISH (start) blok
    """
    if not is_tests_enabled():
        text = "⛔ Bu funksiya vaqtinchalik o‘chirilgan."
        if isinstance(obj, CallbackQuery):
            await obj.answer(text, show_alert=True)
            try:
                await obj.message.answer(text)
            except Exception:
                pass
        else:
            await obj.answer(text)
        return False
    return True


@router.callback_query(F.data.startswith("ugen:file:"))
async def ugen_send_file(cb: CallbackQuery, bot: Bot, config: Config):
    mid = int(cb.data.split(":")[-1])
    try:
        await copy_to_user_and_log(
            bot,
            user_id=cb.from_user.id,
            from_chat_id=int(config.general_books_supergroup_id),
            message_id=mid,
            protect_content=True
        )
    except Exception:
        await cb.message.answer("❌ Fayl yuborib bo‘lmadi.")
    await cb.answer()

# =========================
# USER: IMTIHON SAVOLLARI
# =========================
@router.message(F.text == "📄 IMTIHON SAVOLLARI")
async def user_exam_root(message: Message):
    if not await guard_subscription(message):
        return

    await answer_and_log(message, "📄 Imtihon savollari\nQaysi kursni tanlaysiz?", reply_markup=back_menu())
    await answer_and_log(message, "Kursni tanlang:", reply_markup=inline_courses("user_exam"))


@router.callback_query(F.data == "user_exam:back:courses")
async def user_exam_back_courses(cb: CallbackQuery):
    if not await guard_subscription(cb):
        return
    try:
        await cb.message.edit_text("📄 Imtihon savollari\nKursni tanlang:", reply_markup=inline_courses("user_exam"))
    except Exception:
        await cb.message.answer("📄 Imtihon savollari\nKursni tanlang:", reply_markup=inline_courses("user_exam"))
    await cb.answer()

@router.callback_query(F.data.startswith("user_exam:course:"))
async def user_exam_course(cb: CallbackQuery):
    if not await guard_subscription(cb):
        return

    course = int(cb.data.split(":")[-1])

    # semestrlarni chiqaramiz
    await cb.message.edit_text(
        f"📄 Imtihon savollari\n{course}-kurs tanlandi.\nSemestrni tanlang:",
        reply_markup=inline_semesters("user_exam", course)
    )
    await cb.answer()

@router.callback_query(F.data.startswith("user_exam:fan:"))
async def user_exam_files(cb: CallbackQuery, bot, config: Config):
    if not await guard_subscription(cb):
        return

    subject_id = int(cb.data.split(":")[-1])
    files = get_exam_files(subject_id)

    if not files:
        await cb.message.answer("📭 Bu fan uchun imtihon fayllari yo‘q.")
        await cb.answer()
        return

    ok = 0
    fail = 0
    last_err = ""

    for f in files:
        try:
            await copy_to_user_and_log(
                bot,
                user_id=cb.from_user.id,
                from_chat_id=int(config.exam_supergroup_id),
                message_id=int(f["message_id"]),
                protect_content=True
            )
            ok += 1
        except Exception as e:
            fail += 1
            last_err = str(e)

    if ok == 0:
        await cb.message.answer(
            "❌ Fayllarni yuborib bo‘lmadi.\n"
            f"Xato: {last_err}\n\n"
            "✅ Tekshiruv:\n"
            "1) Bot EXAM superguruhda bormi/adminmi?\n"
            "2) Guruhda 'Protect content/Restrict saving content' o‘chiqmi?\n"
            "3) EXAM_SUPERGROUP_ID -100... formatdami?"
        )
    else:
        await cb.message.answer(f"✅ Yuborildi: {ok} ta. Xato: {fail} ta.")

    await cb.answer()

@router.poll_answer()
async def on_poll_answer(ans: PollAnswer):
    poll_id = ans.poll_id
    user_id = ans.user.id
    option_ids = ans.option_ids

    # DBga yozamiz
    upsert_poll_vote(poll_id, user_id, option_ids)
    
@router.callback_query(F.data.startswith("user_exam:sem:"))
async def user_exam_sem(cb: CallbackQuery):
    if not await guard_subscription(cb):
        return

    _, _, course, sem = cb.data.split(":")
    subjects = get_exam_subjects(int(course), int(sem))

    if not subjects:
        await cb.message.edit_text("Bu kurs va semestr uchun imtihon savollari hali qo‘shilmagan.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for s in subjects:
        kb.button(text=s["name"], callback_data=f"user_exam:fan:{s['id']}")
    kb.adjust(2)

    await cb.message.edit_text("📄 Fanni tanlang:", reply_markup=kb.as_markup())
    await cb.answer()

# ===== GENERAL BOOKS SEARCH =====
class GeneralSearchStates(StatesGroup):
    waiting_query = State()


@router.message(F.text == "🔎 QIDIRUV")
async def gb_search_start(message: Message, state: FSMContext):
    if not await guard_subscription(message):
        return
    await state.set_state(GeneralSearchStates.waiting_query)
    await message.answer(
        "🔎 Qidirayotgan fan/bo‘lim/kitob nomining bir qismini yozing.\n"
        "Masalan: anat / anato / anatomiya",
        reply_markup=general_books_user_menu()
    )


@router.message(GeneralSearchStates.waiting_query, F.text, ~F.text.in_(["⬅️ ORQAGA", "🏠 ASOSIY MENYU"]))
async def gb_search_do(message: Message, state: FSMContext):
    if not await guard_subscription(message):
        return

    query = message.text.strip().lower()
    if len(query) < 2:
        await message.answer("❗ Kamida 2 ta harf yozing.")
        return

    subjects = search_general_subjects(query, limit=20)
    files = search_general_files(query, limit=30)

    if not subjects and not files:
        await message.answer("🔎 Hech narsa topilmadi.")
        return

    kb = InlineKeyboardBuilder()

    for s in subjects:
        kb.button(text=f"📚 {s['name']}", callback_data=f"ugen:sub:{s['id']}")

    for f in files:
        kb.button(text=f"📄 {f['file_name']}"[:60], callback_data=f"ugen:file:{int(f['message_id'])}")

    kb.adjust(1)
    await message.answer("🔎 Qidiruv natijalari:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("ugen:sub:"))
async def ugen_open_subject(cb: CallbackQuery, bot: Bot, config: Config):
    if not await guard_subscription(cb):
        return

    sid = int(cb.data.split(":")[-1])
    files = get_general_files(sid)
    if not files:
        await cb.message.answer("📭 Bu bo‘limda fayl yo‘q.")
        await cb.answer()
        return

    for f in files:
        try:
            await copy_to_user_and_log(
                bot,
                user_id=cb.from_user.id,
                from_chat_id=int(config.general_books_supergroup_id),
                message_id=int(f["message_id"]),
                protect_content=True
            )
        except Exception:
            pass

    await cb.answer()


@router.callback_query(F.data.startswith("ugen:file:"))
async def ugen_send_file(cb: CallbackQuery, bot: Bot, config: Config):
    if not await guard_subscription(cb):
        return

    mid = int(cb.data.split(":")[-1])
    try:
        await copy_to_user_and_log(
            bot,
            user_id=cb.from_user.id,
            from_chat_id=int(config.general_books_supergroup_id),
            message_id=mid,
            protect_content=True
        )
    except Exception:
        await cb.message.answer("❌ Fayl yuborib bo‘lmadi.")
    await cb.answer()

# =========================
# TEST STATES
# =========================
class UserTestStates(StatesGroup):
    choosing_course = State()
    choosing_semester = State()
    choosing_test = State()
    confirm_start = State()
    running = State()


def _fmt_dt(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def _format_timer(rem: int) -> str:
    if rem < 0:
        rem = 0
    mm = rem // 60
    ss = rem % 60
    return f"{mm:02d}:{ss:02d}"


async def _stop_timer_task(session_id: int):
    task = TIMER_TASKS.pop(session_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except Exception:
            pass


async def _finish_and_show_result(bot, config: Config, session_id: int, user_chat_id: int, reason: str = "Tugadi"):
    sess = get_session(session_id)
    if not sess:
        return

    sess = row_to_dict(sess)  # ✅ Row bo'lsa dict qilamiz

    # timer va savol xabarlarini o‘chirish
    try:
        tm = sess.get("timer_message_id") if isinstance(sess, dict) else sess["timer_message_id"]
        if tm:
            await bot.delete_message(user_chat_id, int(tm))
    except Exception:
        pass

    try:
        qm = sess.get("question_message_id") if isinstance(sess, dict) else sess["question_message_id"]
        if qm:
            await bot.delete_message(user_chat_id, int(qm))
    except Exception:
        pass

    total_q = int(count_session_questions(session_id) or 0)
    correct = int(sess.get("correct_count", 0)) if isinstance(sess, dict) else int(sess["correct_count"])
    wrong = max(0, total_q - correct)
    score = correct * 2

    started_at = int(sess.get("started_at", 0)) if isinstance(sess, dict) else int(sess["started_at"])
    ends_at = int(sess.get("ends_at", started_at)) if isinstance(sess, dict) else int(sess["ends_at"])
    now = int(time.time())
    used = max(0, min(now, ends_at) - started_at)
    used_min = used // 60
    used_sec = used % 60

    uname = (sess.get("username") or "no_username") if isinstance(sess, dict) else (sess["username"] or "no_username")
    uid = int(sess.get("user_id", user_chat_id)) if isinstance(sess, dict) else int(sess["user_id"])
    test_name = sess.get("test_name", "-") if isinstance(sess, dict) else sess["test_name"]

    text = (
        f"✅ TEST YAKUNLANDI ({reason})\n\n"
        f"👤 @{uname} | ID: {uid}\n"
        f"📅 Sana/vaqt: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}\n\n"
        f"📘 Test: {test_name}\n"
        f"📌 Savollar: {total_q}\n"
        f"✅ To‘g‘ri: {correct}\n"
        f"❌ Noto‘g‘ri: {wrong}\n"
        f"🏁 Ball: {score}\n"
        f"⏱ Sarflangan vaqt: {used_min:02d}:{used_sec:02d}\n"
    )

    # ✅ natija yuborilgandan keyin sessionni yakunlaymiz
    try:
        await bot.send_message(user_chat_id, text, reply_markup=user_main_menu(), protect_content=True)
    except Exception:
        await bot.send_message(user_chat_id, text, reply_markup=user_main_menu())

    finish_session(session_id)

async def _timer_loop(bot, config: Config, session_id: int, user_chat_id: int, timer_message_id: int):
    while True:
        sess = get_session(session_id)
        if not sess:
            return

        # sqlite3.Row bo'lishi mumkin
        try:
            if int(sess["is_finished"]) == 1:
                return
        except Exception:
            pass

        if not is_tests_enabled():
            await _stop_timer_task(session_id)
            await _finish_and_show_result(bot, config, session_id, user_chat_id, reason="Admin vaqtincha o‘chirdi")
            return

        now = int(time.time())
        ends_at = int(sess["ends_at"])
        rem = ends_at - now

        if rem <= 0:
            await _stop_timer_task(session_id)
            await _finish_and_show_result(bot, config, session_id, user_chat_id, reason="Vaqt tugadi")
            return

        timer_text = (
            "⏳ TEST VAQTI\n"
            f"Qolgan vaqt: {_format_timer(rem)}\n\n"
            "⚠️ Vaqt tugasa test avtomatik yakunlanadi."
        )

        try:
            await bot.edit_message_text(timer_text, chat_id=user_chat_id, message_id=int(timer_message_id))
        except Exception:
            pass

        # ✅ Har 5 minutda yangilaydi, oxirgi 5 minutda 1 minutda
        await asyncio.sleep(60 if rem <= 300 else 300)


@router.callback_query(UserTestStates.confirm_start, F.data == "ut:go")
async def user_start_test(cb: CallbackQuery, state: FSMContext, bot: Bot, config: Config):
    if not await guard_subscription(cb):
        return
    if not await guard_tests_entry(cb):
        return

    data = await state.get_data()
    test_id = int(data["test_id"])
    test_name = data["test_name"]

    u = cb.from_user
    upsert_user(u.id, u.username, u.full_name)

    session_id = create_test_session(
        user_id=u.id,
        username=u.username or "",
        test_id=test_id,
        test_name=test_name,
        duration_sec=50 * 60,
        questions_limit=35
    )

    await state.set_state(UserTestStates.running)

    timer_msg = await bot.send_message(
        u.id,
        "⏳ TEST VAQTI\nQolgan vaqt: 50:00\n\n⚠️ Vaqt tugasa test avtomatik yakunlanadi.",
        protect_content=True
    )

    # bitta "savol oynasi" – keyin edit qilib turamiz
    q_msg = await bot.send_message(u.id, "✅ Test boshlandi...", protect_content=True)

    set_session_messages(session_id, timer_msg.message_id, q_msg.message_id)

    task = asyncio.create_task(_timer_loop(bot, config, session_id, u.id, timer_msg.message_id))
    TIMER_TASKS[session_id] = task

    q_count = count_session_questions(session_id)
    if not q_count or int(q_count) <= 0:
        await bot.send_message(u.id, "❌ Test savollari topilmadi (session_questions bo‘sh). Admin testni qayta yuklasin.")
        await _stop_timer_task(session_id)
        finish_session(session_id)
        await state.clear()
        await cb.answer()
        return

    # ✅ ENG MUHIMI: birinchi savolni chiqaramiz
    await _render_question(bot, config, session_id, u.id)
    await cb.answer()

async def _render_question(bot: Bot, config: Config, session_id: int, user_chat_id: int):
    sess = get_session(session_id)
    if not sess:
        return

    if not is_tests_enabled():
        await _stop_timer_task(session_id)
        await _finish_and_show_result(bot, config, session_id, user_chat_id, reason="Admin vaqtincha o‘chirdi")
        return

    now = int(time.time())
    if now >= int(sess["ends_at"]):
        await _stop_timer_task(session_id)
        await _finish_and_show_result(bot, config, session_id, user_chat_id, reason="Vaqt tugadi")
        return

    total_q = int(count_session_questions(session_id) or 0)

    # ✅ Indeks faqat session.current_index dan olinadi (answers table kerak emas)
    idx = int(rget(sess, "current_index", 0) or 0)

    if idx >= total_q:
        await _stop_timer_task(session_id)
        await _finish_and_show_result(bot, config, session_id, user_chat_id, reason="Savollar tugadi")
        return

    row = get_session_question(session_id, idx)
    if not row:
        await _stop_timer_task(session_id)
        await _finish_and_show_result(bot, config, session_id, user_chat_id, reason="Savol topilmadi")
        return

    options = json.loads(row["options_json"])
    qid = int(row["question_id"])

    uid = int(sess["user_id"])
    uname = sess["username"] or "no_username"

    who = f"@{uname} | ID:{uid}"
    dt = _fmt_dt(now)

    header = (
        f"👤 {who}\n"
        f"🕒 {dt}\n"
        f"📘 {sess['test_name']}\n"
        f"🧩 Savol: {idx + 1}/{total_q}\n"
        f"{'-' * 24}\n"
    )

    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT question_text FROM questions WHERE id=?", (qid,))
    qtext_row = cur.fetchone()
    conn.close()

    qtext = qtext_row["question_text"] if qtext_row else "Savol topilmadi"

    body = f"❓ {qtext}\n\n"
    letters = ["A", "B", "C", "D"]
    for i, opt in enumerate(options):
        body += f"{letters[i]}) {opt}  | {who}\n{SEP_LINE}\n"

    footer = "\n🛑 Pastdan 'TUGATISH' bosib testni yakunlashingiz mumkin."
    text = header + body + footer

    kb = InlineKeyboardBuilder()
    for i, letter in enumerate(letters):
        kb.button(text=letter, callback_data=f"ut:ans:{session_id}:{qid}:{i}")
    kb.adjust(2)
    kb.button(text="🛑 TUGATISH", callback_data=f"ut:finish:{session_id}")
    kb.adjust(2, 2, 1)

    try:
        await bot.edit_message_text(
            text,
            chat_id=user_chat_id,
            message_id=int(sess["question_message_id"]),
            reply_markup=kb.as_markup()
        )
    except Exception:
        msg = await bot.send_message(user_chat_id, text, reply_markup=kb.as_markup(), protect_content=True)
        set_session_messages(session_id, int(sess["timer_message_id"] or 0), msg.message_id)


# =========================
# USER: Kutubxona
# =========================
@router.callback_query(F.data == "user_lib:general")
async def user_general_books(cb: CallbackQuery):
    if not await guard_subscription(cb):
        return

    items = get_general_subjects()
    if not items:
        await cb.message.edit_text("📚 Umumiy kitoblar\nHozircha bo‘lim yo‘q.")
        await cb.message.answer("🔎 Qidiruv ishlashi uchun bo‘limlar kerak.", reply_markup=general_books_user_menu())
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for s in items:
        kb.button(text=s["name"], callback_data=f"user_gb:sub:{s['id']}")
    kb.adjust(2)

    await cb.message.edit_text("📚 Umumiy kitoblar\nBo‘limni tanlang:", reply_markup=kb.as_markup())
    await cb.message.answer("🔎 Qidiruv", reply_markup=general_books_user_menu())
    await cb.answer()
@router.callback_query(F.data.startswith("user_gb:sub:"))
async def user_gb_files(cb: CallbackQuery, bot, config: Config):
    if not await guard_subscription(cb):
        return

    subject_id = int(cb.data.split(":")[-1])
    files = get_general_files(subject_id)

    if not files:
        await cb.message.answer("📭 Bu bo‘limda fayl yo‘q.", reply_markup=general_books_user_menu())
        await cb.answer()
        return

    for f in files:
        try:
            await copy_to_user_and_log(
                bot,
                user_id=cb.from_user.id,
                from_chat_id=int(config.general_books_supergroup_id),
                message_id=int(f["message_id"]),
                protect_content=True
            )
        except Exception:
            pass

    await cb.answer()

@router.message(F.text == "📚 KUTUBXONA")
async def user_library(message: Message):
    if not await guard_subscription(message):
        return

    await answer_and_log(message, "📚 Kutubxona\nQaysi kursni tanlaysiz?", reply_markup=back_menu())
    await answer_and_log(message, "Kursni tanlang:", reply_markup=inline_courses_with_general("user_lib"))



@router.callback_query(F.data == "user_lib:back:courses")
async def user_lib_back_courses(cb: CallbackQuery):
    if not await guard_subscription(cb):
        return
    try:
        await cb.message.edit_text("📚 Kutubxona\nKursni tanlang:", reply_markup=inline_courses_with_general("user_lib"))
    except Exception:
        await cb.message.answer("📚 Kutubxona\nKursni tanlang:", reply_markup=inline_courses("user_lib"))
    await cb.answer()


@router.callback_query(F.data.startswith("user_lib:course:"))
async def user_lib_course(cb: CallbackQuery):
    if not await guard_subscription(cb):
        return

    course = int(cb.data.split(":")[-1])
    await cb.message.edit_text(
        f"📚 {course}-kurs tanlandi.\nSemestrni tanlang:",
        reply_markup=inline_semesters("user_lib", course)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("user_lib:sem:"))
async def user_lib_sem(cb: CallbackQuery):
    if not await guard_subscription(cb):
        return

    _, _, course, sem = cb.data.split(":")
    subjects = get_subjects(int(course), int(sem))

    if not subjects:
        await cb.message.edit_text("Bu kurs va semestr uchun fanlar hali qo‘shilmagan.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for s in subjects:
        kb.button(text=s["name"], callback_data=f"user_lib:fan:{s['id']}")
    kb.adjust(2)

    await cb.message.edit_text("📚 Fanni tanlang:", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("user_lib:fan:"))
async def user_view_files(cb: CallbackQuery, bot, config: Config):
    if not await guard_subscription(cb):
        return

    subject_id = int(cb.data.split(":")[-1])
    files = get_files(subject_id)

    if not files:
        await cb.message.answer("📭 Bu fan uchun hali materiallar yo‘q.")
        await cb.answer()
        return

    for f in files:
        try:
            await copy_to_user_and_log(
                bot,
                user_id=cb.from_user.id,
                from_chat_id=int(config.supergroup_id),
                message_id=int(f["message_id"]),
                protect_content=True
            )
        except Exception:
            pass

    await cb.answer()


# =========================
# USER: Testlar
# =========================
@router.message(F.text == "📝 TESTLAR")
async def user_tests(message: Message, state: FSMContext):
    if not await guard_subscription(message):
        return
    if not await guard_tests_entry(message):
        return

    await state.clear()
    await state.set_state(UserTestStates.choosing_course)

    await answer_and_log(message, "📝 Testlar\nQaysi kursni tanlaysiz?", reply_markup=back_menu())
    await answer_and_log(message, "Kursni tanlang:", reply_markup=inline_courses("user_test"))


@router.callback_query(F.data == "user_test:back:courses")
async def user_test_back_courses(cb: CallbackQuery, state: FSMContext):
    if not await guard_subscription(cb):
        return
    if not await guard_tests_entry(cb):
        return
    await state.clear()
    try:
        await cb.message.edit_text("📝 Testlar\nKursni tanlang:", reply_markup=inline_courses("user_test"))
    except Exception:
        await cb.message.answer("📝 Testlar\nKursni tanlang:", reply_markup=inline_courses("user_test"))
    await cb.answer()


@router.callback_query(F.data.startswith("user_test:course:"))
async def user_test_course(cb: CallbackQuery, state: FSMContext):
    if not await guard_subscription(cb):
        return
    if not await guard_tests_entry(cb):
        return

    course = int(cb.data.split(":")[-1])
    await state.update_data(course=course)
    await state.set_state(UserTestStates.choosing_semester)

    await cb.message.edit_text(
        f"📝 {course}-kurs testlari.\nSemestrni tanlang:",
        reply_markup=inline_semesters("user_test", course)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("user_test:sem:"))
async def user_test_sem(cb: CallbackQuery, state: FSMContext):
    if not await guard_subscription(cb):
        return
    if not await guard_tests_entry(cb):
        return

    _, _, course, sem = cb.data.split(":")
    course_i = int(course)
    sem_i = int(sem)

    await state.update_data(semester=sem_i)
    await state.set_state(UserTestStates.choosing_test)

    tests = list_tests(course_i, sem_i)
    if not tests:
        await cb.message.edit_text("Bu kurs va semestrda hozircha test yo‘q.")
        await cb.answer()
        return

    kb = InlineKeyboardBuilder()
    for t in tests:
        kb.button(text=t["name"], callback_data=f"ut:pick:{t['id']}")
    kb.adjust(1)

    await cb.message.edit_text("🧾 Testni tanlang:", reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data.startswith("ut:pick:"))
async def user_pick_test(cb: CallbackQuery, state: FSMContext):
    if not await guard_subscription(cb):
        return
    if not await guard_tests_entry(cb):
        return

    test_id = int(cb.data.split(":")[-1])

    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT name FROM tests WHERE id=?", (test_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await cb.message.edit_text("❌ Test topilmadi.")
        await cb.answer()
        return

    test_name = row["name"]

    await state.update_data(test_id=test_id, test_name=test_name)
    await state.set_state(UserTestStates.confirm_start)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ HA", callback_data="ut:go")
    kb.button(text="❌ YO‘Q", callback_data="ut:cancel")
    kb.adjust(2)

    await cb.message.edit_text(
        f"📘 Test: {test_name}\n\n"
        "Testga tayyormisiz?\n"
        "⏳ Vaqt: 50 daqiqa\n"
        "📌 Savol: 35 ta (random)\n"
        "✅ Har to‘g‘ri javob: 2 ball",
        reply_markup=kb.as_markup()
    )
    await cb.answer()


@router.callback_query(UserTestStates.confirm_start, F.data == "ut:cancel")
async def user_cancel_test(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.edit_text("❌ Bekor qilindi.", reply_markup=None)
    except Exception:
        pass

    await cb.message.answer("🏠 Asosiy menyu", reply_markup=user_main_menu())
    await cb.answer()



@router.callback_query(F.data.startswith("ut:ans:"))
async def user_answer(cb: CallbackQuery, bot: Bot, config: Config):
    if not is_tests_enabled():
        session_id = int(cb.data.split(":")[2])
        await _stop_timer_task(session_id)
        await _finish_and_show_result(bot, config, session_id, cb.from_user.id, reason="Admin vaqtincha o‘chirdi")
        await cb.answer()
        return

    if not await guard_subscription(cb):
        return

    parts = cb.data.split(":")
    session_id = int(parts[2])
    qid = int(parts[3])
    chosen = int(parts[4])

    sess = get_session(session_id)
    if not sess or int(sess["is_finished"]) == 1:
        await cb.answer("Test yakunlangan.", show_alert=True)
        return

    now = int(time.time())
    if now >= int(sess["ends_at"]):
        await _stop_timer_task(session_id)
        await _finish_and_show_result(bot, config, session_id, cb.from_user.id, reason="Vaqt tugadi")
        await cb.answer()
        return

    idx = int(rget(sess, "current_index", 0) or 0)
    row = get_session_question(session_id, idx)
    if not row:
        await cb.answer("Savol topilmadi", show_alert=True)
        return

    correct_index = int(row["correct_index"])
    is_correct = 1 if chosen == correct_index else 0

    # javobni saqlaymiz
    save_answer(session_id, qid, chosen, is_correct)

    # ✅ keyingi savolga o'tish uchun index + correct_count oshiramiz
    _advance_session(session_id, is_correct)

    total_q = int(count_session_questions(session_id) or 0)
    sess2 = get_session(session_id)
    idx2 = int(rget(sess2, "current_index", 0) or 0)

    # ✅ 35 savolning hammasi belgilansa – tugaydi
    if idx2 >= total_q:
        await _stop_timer_task(session_id)
        await _finish_and_show_result(bot, config, session_id, cb.from_user.id, reason="Savollar tugadi")
        await cb.answer()
        return

    await _render_question(bot, config, session_id, cb.from_user.id)
    await cb.answer()

@router.callback_query(F.data.startswith("ut:finish:"))
async def user_finish(cb: CallbackQuery, bot, config: Config):

    if not await guard_subscription(cb):
        return

    session_id = int(cb.data.split(":")[-1])

    sess = get_session(session_id)
    if not sess or int(sess["is_finished"]) == 1:
        await cb.answer("Test yakunlangan.", show_alert=True)
        return

    await _stop_timer_task(session_id)
    await _finish_and_show_result(bot, config, session_id, cb.from_user.id, reason="User tugatdi")
    await cb.answer()

# =========================
# USER: Feedback
# =========================
@router.message(F.text == "💬 SHIKOYAT VA TAKLIFLAR")
async def user_feedback_start(message: Message, state: FSMContext):
    await state.set_state(FeedbackStates.waiting_text)
    await answer_and_log(
        message,
        "💬 Shikoyat yoki taklifingizni yozing.\nBiz albatta ko‘rib chiqamiz.",
        reply_markup=back_menu()
    )


@router.message(
    FeedbackStates.waiting_text,
    F.text,
    ~F.text.in_(["⬅️ ORQAGA", "🏠 ASOSIY MENYU"])
)
async def user_feedback_save_handler(message: Message, state: FSMContext):
    u = message.from_user
    upsert_user(u.id, u.username, u.full_name)
    save_feedback(u.id, u.username, message.text)

    await state.clear()

    await answer_and_log(
        message,
        "✅ Xabaringiz qabul qilindi.",
        reply_markup=user_main_menu(),
        keep=True
    )


# =========================
# USER: Obuna info (placeholder)
# =========================
@router.message(F.text == "⭐ OBUNA HAQIDA MA’LUMOT")
async def user_sub_info(message: Message):
    await answer_and_log(
        message,
        "⭐ Obuna haqida\n\n"
        "• Obuna yoqilgan bo‘lsa, botdan foydalanish uchun obuna talab qilinadi.\n"
        "• Materiallarni tarqatish qat’iyan taqiqlanadi. Qoidabuzarlik bo‘lsa bloklanasiz.\n\n"
        "Hozircha to‘lov moduli ulanmagan.\n"
        "Keyingi bosqichda: Stars / Click-Payme (admin tanlagan) bo‘yicha to‘lov tugmasi shu yerda chiqadi.",
        reply_markup=back_menu()
    )
