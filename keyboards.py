from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
# --- USER MAIN MENU ---
def user_main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()

    kb.row(
        KeyboardButton(text="📚 KUTUBXONA"),
        KeyboardButton(text="📝 TESTLAR"),
    )

    # ✅ YANGI: IMTIHON SAVOLLARI
    kb.row(
        KeyboardButton(text="📄 IMTIHON SAVOLLARI"),
        KeyboardButton(text="⭐ OBUNA HAQIDA MA’LUMOT"),
    )

    kb.row(
        KeyboardButton(text="💬 SHIKOYAT VA TAKLIFLAR"),
    )

    kb.row(KeyboardButton(text="🏠 ASOSIY MENYU"))

    return kb.as_markup(resize_keyboard=True)


# --- ADMIN MAIN MENU ---
def admin_main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()

    kb.row(
        KeyboardButton(text="📚 Kutubxona boshqaruvi"),
        KeyboardButton(text="📄 Imtihon savollari boshqaruvi"),  # ✅ YANGI
    )

    kb.row(
        KeyboardButton(text="📝 Test boshqaruvi"),   # test qo‘shish/o‘chirish (oldingi)
    )

    kb.row(
        KeyboardButton(text="⚙️ Sozlamalar"),
    )

    kb.row(
        KeyboardButton(text="📩 Userlardan xabarlar"),
    )

    kb.row(
        KeyboardButton(text="🧹 User chatini tozalash"),
        KeyboardButton(text="📢 Post yuborish"),
    )

    kb.row(KeyboardButton(text="🏠 ASOSIY MENYU"))

    return kb.as_markup(resize_keyboard=True)


def admin_library_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="➕ Fayl qo‘shish"))
    kb.row(KeyboardButton(text="🗑 Fayl o‘chirish"))
    kb.row(KeyboardButton(text="🗑 Fan o‘chirish"))  # ✅ YANGI
    kb.row(KeyboardButton(text="⬅️ ORQAGA"), KeyboardButton(text="🏠 ASOSIY MENYU"))
    return kb.as_markup(resize_keyboard=True)

def back_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="⬅️ ORQAGA"), KeyboardButton(text="🏠 ASOSIY MENYU"))
    return kb.as_markup(resize_keyboard=True)

def admin_broadcast_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="📢 Post jo‘natish"))                 # oldingi broadcast (state)
    kb.row(KeyboardButton(text="📊 Poll natijalarini ko‘rish"))
    kb.row(KeyboardButton(text="🗑 Jo‘natilgan postlarni o‘chirish"))
    kb.row(KeyboardButton(text="🧹 Statistika (poll)ni tozalash"))
    kb.row(KeyboardButton(text="⬅️ ORQAGA"), KeyboardButton(text="🏠 ASOSIY MENYU"))
    return kb.as_markup(resize_keyboard=True)

def general_books_user_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="🔎 QIDIRUV"))
    kb.row(KeyboardButton(text="⬅️ ORQAGA"), KeyboardButton(text="🏠 ASOSIY MENYU"))
    return kb.as_markup(resize_keyboard=True)
    
# --- ADMIN SETTINGS ROOT MENU (reply keyboard) ---
def admin_settings_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="🛠 Bot sozlamalari"))
    kb.row(KeyboardButton(text="⭐ Obuna sozlamalari"))
    kb.row(KeyboardButton(text="🚫 Blockni boshqarish"))
    kb.row(KeyboardButton(text="⬅️ ORQAGA"), KeyboardButton(text="🏠 ASOSIY MENYU"))
    return kb.as_markup(resize_keyboard=True)


# --- inline: kurs tanlash (1..5) ---
def inline_courses(prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text=f"{i}-kurs", callback_data=f"{prefix}:course:{i}")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def inline_semesters(prefix: str, course: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="1-semestr", callback_data=f"{prefix}:sem:{course}:1")
    kb.button(text="2-semestr", callback_data=f"{prefix}:sem:{course}:2")
    kb.button(text="⬅️ Orqaga", callback_data=f"{prefix}:back:courses")
    kb.adjust(2, 1)
    return kb.as_markup()


def yes_no(prefix: str, payload: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data=f"{prefix}:yes:{payload}")
    kb.button(text="❌ Yo‘q", callback_data=f"{prefix}:no:{payload}")
    kb.adjust(2)
    return kb.as_markup()

def admin_clear_chat_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="🧹 Umumiy chat tozalash"))
    kb.row(KeyboardButton(text="🧹 1 ta userni tozalash"))
    kb.row(KeyboardButton(text="⬅️ ORQAGA"), KeyboardButton(text="🏠 ASOSIY MENYU"))
    return kb.as_markup(resize_keyboard=True)
    
def admin_exam_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="➕ Imtihon fayl qo‘shish"))
    kb.row(KeyboardButton(text="🗑 Imtihon fanini o‘chirish"))
    kb.row(KeyboardButton(text="⬅️ ORQAGA"), KeyboardButton(text="🏠 ASOSIY MENYU"))
    return kb.as_markup(resize_keyboard=True)

def admin_feedback_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="👀 Xabarlarni ko‘rish"))
    kb.row(KeyboardButton(text="🗑 Xabarlarni o‘chirish"))
    kb.row(KeyboardButton(text="⬅️ ORQAGA"), KeyboardButton(text="🏠 ASOSIY MENYU"))
    return kb.as_markup(resize_keyboard=True)
#===BLOCK UCHUN======
def blocked_user_menu():
    # Blocklangan user faqat shikoyat yozadi
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💬 SHIKOYAT VA TAKLIFLAR")],
        ],
        resize_keyboard=True
    )
#===================

def admin_block_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⛔ Blocklash"), KeyboardButton(text="✅ Blockdan chiqarish")],
            [KeyboardButton(text="📋 Blocklanganlar ro‘yxati")],
            [KeyboardButton(text="⬅️ ORQAGA")],
        ],
        resize_keyboard=True
    )
#=========================================
def inline_courses_with_general(prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text=f"{i}-kurs", callback_data=f"{prefix}:course:{i}")

    # ✅ eng pastga Umumiy kitoblar
    kb.button(text="📚 Umumiy kitoblar", callback_data=f"{prefix}:general")

    kb.adjust(2, 2, 1, 1)  # oxirida 1 ta tugma qoladi
    return kb.as_markup()

# --- inline: OBUNA SOZLAMALARI (admin) ---
def inline_sub_settings(
    sub_enabled: bool,
    click_enabled: bool,
    stars_enabled: bool,
    referral_enabled: bool,
    channel_enabled: bool,
) -> InlineKeyboardMarkup:
    def s(x: bool):
        return "✅" if x else "⛔"

    kb = InlineKeyboardBuilder()
    kb.button(text=f"{s(sub_enabled)} Obuna umumiy", callback_data="subset:toggle:sub_enabled")

    kb.button(text=f"{s(click_enabled)} Click/Payme", callback_data="subset:toggle:sub_pay_click_enabled")
    kb.button(text=f"{s(stars_enabled)} Telegram Stars", callback_data="subset:toggle:sub_pay_stars_enabled")

    kb.button(text=f"{s(referral_enabled)} Referral (odam qo‘shish)", callback_data="subset:toggle:sub_referral_enabled")
    kb.button(text=f"{s(channel_enabled)} Kanalga a’zo bo‘lib", callback_data="subset:toggle:sub_channel_enabled")

    kb.adjust(1, 2, 2)
    return kb.as_markup()
