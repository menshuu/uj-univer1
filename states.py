from aiogram.fsm.state import State, StatesGroup

class FeedbackStates(StatesGroup):
    waiting_text = State()

class AdminStates(StatesGroup):
    # Keyingi bosqichlarda bo‘lim qo‘shish/o‘chirish, fayl qo‘shish/o‘chirish, test qo‘shish/o‘chirish
    dummy = State()
