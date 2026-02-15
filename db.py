# db.py (TOZA + YAKUNIY + FIX)

import json
import time
import random
import sqlite3
from pathlib import Path
from datetime import datetime

# =========================
# PATHS
# =========================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"

STORAGE_DIR = BASE_DIR / "storage"
RAW_TEST_DIR = STORAGE_DIR / "tests_raw"

STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# WinError 183 fix: agar tests_raw papka emas, fayl bo‘lib qolgan bo‘lsa
if RAW_TEST_DIR.exists() and RAW_TEST_DIR.is_file():
    RAW_TEST_DIR.rename(STORAGE_DIR / f"tests_raw_is_file_{int(time.time())}.bak")

RAW_TEST_DIR.mkdir(parents=True, exist_ok=True)


# =========================
# DB CONNECT
# =========================
def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # FK/ON DELETE CASCADE ishlashi uchun
    conn.execute("PRAGMA foreign_keys = ON;")

    # tezroq ishlashi uchun
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


# =========================
# CORE TABLES: users + feedback
# =========================
def init_db() -> None:
    with connect() as conn:
        cur = conn.cursor()

        # users jadvali (is_blocked ustuni qoldirilgan: eski DB bilan mos bo‘lishi uchun)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            is_blocked INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
# --- TEST ANSWERS TABLE (missing) ---
        cur.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            chosen_index INTEGER NOT NULL,
            is_correct INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_answers_session ON answers(session_id)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_answers_session_question ON answers(session_id, question_id)")

# =========================
# USERS
# =========================
def upsert_user(user_id: int, username: str | None, full_name: str) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO users(user_id, username, full_name)
        VALUES(?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
          username=excluded.username,
          full_name=excluded.full_name
        """, (int(user_id), username or "", full_name or ""))


def set_user_block_flag_in_users_table(user_id: int, is_blocked: bool) -> None:
    """
    ESKI/qo‘shimcha: users.is_blocked flag.
    Sizning sistemada asosiy blok: blocked_users jadvali.
    """
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_blocked=? WHERE user_id=?", (1 if is_blocked else 0, int(user_id)))


def is_user_blocked_flag_in_users_table(user_id: int) -> bool:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT is_blocked FROM users WHERE user_id=?", (int(user_id),))
        row = cur.fetchone()
    return bool(row["is_blocked"]) if row else False


# =========================
# GENERAL BOOKS (Umumiy kitoblar)
# =========================
def init_general_books_tables() -> None:
    with connect() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS general_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            topic_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS general_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            file_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(subject_id) REFERENCES general_subjects(id) ON DELETE CASCADE
        )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_general_files_subject ON general_files(subject_id);")


def get_general_subjects():
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, topic_id FROM general_subjects ORDER BY name COLLATE NOCASE")
        return cur.fetchall()


def add_general_subject(name: str, topic_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO general_subjects(name, topic_id) VALUES(?,?)", (name, int(topic_id)))


def get_general_subject_by_name(name: str):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, topic_id FROM general_subjects WHERE name=? LIMIT 1", (name,))
        return cur.fetchone()


def add_general_file(subject_id: int, message_id: int, file_name: str) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO general_files(subject_id, message_id, file_name) VALUES(?,?,?)",
            (int(subject_id), int(message_id), file_name or "")
        )


def get_general_files(subject_id: int):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, message_id, file_name FROM general_files WHERE subject_id=? ORDER BY id DESC",
            (int(subject_id),)
        )
        return cur.fetchall()


def delete_general_file(file_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM general_files WHERE id=?", (int(file_id),))


def delete_general_subject(subject_id: int) -> None:
    # general_files ON DELETE CASCADE bor, lekin safe uchun:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM general_files WHERE subject_id=?", (int(subject_id),))
        cur.execute("DELETE FROM general_subjects WHERE id=?", (int(subject_id),))


def search_general(query: str, limit: int = 50):
    """
    query bo‘yicha:
      1) general_subjects.name LIKE
      2) general_files.file_name LIKE (subject nomi bilan)
    """
    q = (query or "").strip().lower()
    if not q:
        return [], []

    like = f"%{q}%"

    with connect() as conn:
        cur = conn.cursor()

        # subject match
        cur.execute("""
            SELECT id, name
            FROM general_subjects
            WHERE lower(name) LIKE ?
            ORDER BY name COLLATE NOCASE
            LIMIT ?
        """, (like, int(limit)))
        subjects = [dict(r) for r in cur.fetchall()]

        # file match
        cur.execute("""
            SELECT gf.id as file_id, gf.message_id, gf.file_name, gs.id as subject_id, gs.name as subject_name
            FROM general_files gf
            JOIN general_subjects gs ON gs.id = gf.subject_id
            WHERE lower(gf.file_name) LIKE ? OR lower(gs.name) LIKE ?
            ORDER BY gs.name COLLATE NOCASE, gf.id DESC
            LIMIT ?
        """, (like, like, int(limit)))
        files = [dict(r) for r in cur.fetchall()]

    return subjects, files

# =========================
# FEEDBACK
# =========================
def save_feedback(user_id: int, username: str | None, text: str) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO feedback(user_id, username, text)
        VALUES(?,?,?)
        """, (int(user_id), username or "", text or ""))


def list_feedback(limit: int = 30) -> list[dict]:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT user_id, username, text, created_at
        FROM feedback
        ORDER BY id DESC
        LIMIT ?
        """, (int(limit),))
        rows = [dict(r) for r in cur.fetchall()]
    return rows


def clear_feedback() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM feedback")


# =========================
# BOT MESSAGES LOG (admin clean uchun)
# =========================
def init_bot_messages() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            message_id INTEGER,
            keep INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # MIGRATION: eski DBda keep ustun bo'lmasa qo‘shadi
        try:
            cur.execute("PRAGMA table_info(bot_messages)")
            cols = [r["name"] for r in cur.fetchall()]
            if "keep" not in cols:
                cur.execute("ALTER TABLE bot_messages ADD COLUMN keep INTEGER DEFAULT 0")
        except Exception:
            pass


def log_bot_message(user_id: int, chat_id: int, message_id: int, keep: int = 0) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO bot_messages(user_id, chat_id, message_id, keep) VALUES (?,?,?,?)",
            (int(user_id), int(chat_id), int(message_id), int(keep))
        )


def get_bot_messages(user_id: int | None = None, include_keep: bool = False):
    with connect() as conn:
        cur = conn.cursor()

        if user_id is None:
            if include_keep:
                cur.execute("SELECT user_id, chat_id, message_id, keep FROM bot_messages")
            else:
                cur.execute("SELECT user_id, chat_id, message_id FROM bot_messages WHERE keep=0")
            return cur.fetchall()

        if include_keep:
            cur.execute("SELECT chat_id, message_id, keep FROM bot_messages WHERE user_id=?", (int(user_id),))
        else:
            cur.execute("SELECT chat_id, message_id FROM bot_messages WHERE user_id=? AND keep=0", (int(user_id),))
        return cur.fetchall()


def get_all_bot_messages():
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, chat_id, message_id FROM bot_messages ORDER BY id ASC")
        return cur.fetchall()


def clear_bot_messages(user_id: int | None = None) -> None:
    with connect() as conn:
        cur = conn.cursor()
        if user_id is None:
            cur.execute("DELETE FROM bot_messages WHERE keep=0")
        else:
            cur.execute("DELETE FROM bot_messages WHERE user_id=? AND keep=0", (int(user_id),))


def clear_all_bot_messages() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM bot_messages")


# =========================
# LIBRARY
# =========================
def init_library_tables() -> None:
    with connect() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course INTEGER,
            semester INTEGER,
            name TEXT,
            topic_id INTEGER,
            UNIQUE(course, semester, name)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER,
            message_id INTEGER,
            file_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_subject ON files(subject_id);")


def get_subjects(course: int, semester: int):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, topic_id FROM subjects WHERE course=? AND semester=? ORDER BY name",
            (int(course), int(semester))
        )
        return cur.fetchall()


def add_subject(course: int, semester: int, name: str, topic_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO subjects(course, semester, name, topic_id) VALUES (?,?,?,?)",
            (int(course), int(semester), name, int(topic_id))
        )


def get_subject_by_name(course: int, semester: int, name: str):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, topic_id FROM subjects WHERE course=? AND semester=? AND name=?",
            (int(course), int(semester), name)
        )
        return cur.fetchone()


def add_file(subject_id: int, message_id: int, file_name: str) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO files(subject_id, message_id, file_name) VALUES (?,?,?)",
            (int(subject_id), int(message_id), file_name)
        )


def get_files(subject_id: int):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, message_id, file_name FROM files WHERE subject_id=? ORDER BY id DESC",
            (int(subject_id),)
        )
        return cur.fetchall()


def delete_file(file_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM files WHERE id=?", (int(file_id),))

def delete_subject(subject_id: int) -> None:
    """
    Kutubxona fanini o'chiradi: fan + ichidagi files yozuvlari.
    (Telegram supergroupdagi xabarlarni admin.py o'chiradi)
    """
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM files WHERE subject_id=?", (int(subject_id),))
        cur.execute("DELETE FROM subjects WHERE id=?", (int(subject_id),))


# =========================
# EXAM (IMTIHON)
# =========================
def init_exam_tables() -> None:
    with connect() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS exam_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course INTEGER,
            semester INTEGER,
            name TEXT,
            topic_id INTEGER,
            UNIQUE(course, semester, name)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS exam_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER,
            message_id INTEGER,
            file_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_exam_files_subject ON exam_files(subject_id);")


def get_exam_subjects(course: int, semester: int):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, topic_id FROM exam_subjects WHERE course=? AND semester=? ORDER BY name",
            (int(course), int(semester))
        )
        return cur.fetchall()


def add_exam_subject(course: int, semester: int, name: str, topic_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO exam_subjects(course, semester, name, topic_id) VALUES (?,?,?,?)",
            (int(course), int(semester), name, int(topic_id))
        )


def get_exam_subject_by_name(course: int, semester: int, name: str):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, topic_id FROM exam_subjects WHERE course=? AND semester=? AND name=?",
            (int(course), int(semester), name)
        )
        return cur.fetchone()


def add_exam_file(subject_id: int, message_id: int, file_name: str) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO exam_files(subject_id, message_id, file_name) VALUES (?,?,?)",
            (int(subject_id), int(message_id), file_name)
        )


def get_exam_files(subject_id: int):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, message_id, file_name FROM exam_files WHERE subject_id=? ORDER BY id DESC",
            (int(subject_id),)
        )
        return cur.fetchall()


def delete_exam_subject(subject_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM exam_files WHERE subject_id=?", (int(subject_id),))
        cur.execute("DELETE FROM exam_subjects WHERE id=?", (int(subject_id),))


# =========================
# TESTS
# =========================
def init_tests_tables() -> None:
    with connect() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course INTEGER NOT NULL,
            semester INTEGER NOT NULL,
            name TEXT NOT NULL,
            source_file TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(course, semester, name)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            options_json TEXT NOT NULL,
            correct_index INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(test_id) REFERENCES tests(id) ON DELETE CASCADE
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_questions_test ON questions(test_id);")


def add_test(course: int, semester: int, name: str) -> int:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO tests(course, semester, name) VALUES (?,?,?)", (int(course), int(semester), name))
        return int(cur.lastrowid)


def update_test_source_file(test_id: int, filename: str) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE tests SET source_file=? WHERE id=?", (filename, int(test_id)))


def list_tests(course: int, semester: int):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, created_at FROM tests WHERE course=? AND semester=? ORDER BY id DESC",
            (int(course), int(semester))
        )
        return cur.fetchall()


def add_question(test_id: int, question_text: str, options: list[str], correct_index: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO questions(test_id, question_text, options_json, correct_index) VALUES (?,?,?,?)",
            (int(test_id), question_text, json.dumps(options, ensure_ascii=False), int(correct_index))
        )


def count_questions(test_id: int) -> int:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM questions WHERE test_id=?", (int(test_id),))
        row = cur.fetchone()
    return int(row["c"])


def get_random_questions(test_id: int, limit: int = 35):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, question_text, options_json, correct_index FROM questions WHERE test_id=?",
            (int(test_id),)
        )
        rows = list(cur.fetchall())
    random.shuffle(rows)
    return rows[:limit]


def delete_test(test_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM questions WHERE test_id=?", (int(test_id),))
        cur.execute("DELETE FROM tests WHERE id=?", (int(test_id),))


# =========================
# TEST SESSIONS
# =========================
def init_test_sessions_tables() -> None:
    with connect() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS test_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            test_id INTEGER NOT NULL,
            test_name TEXT,
            started_at INTEGER NOT NULL,
            ends_at INTEGER NOT NULL,
            duration_sec INTEGER NOT NULL,
            current_index INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            is_finished INTEGER DEFAULT 0,
            timer_message_id INTEGER,
            question_message_id INTEGER
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS test_session_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            options_json TEXT NOT NULL,
            correct_index INTEGER NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS test_session_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            chosen_index INTEGER NOT NULL,
            is_correct INTEGER NOT NULL
        )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessq_session ON test_session_questions(session_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessa_session ON test_session_answers(session_id);")


def create_test_session(
    user_id: int,
    username: str,
    test_id: int,
    test_name: str,
    duration_sec: int = 50 * 60,
    questions_limit: int = 35
) -> int:
    now = int(time.time())
    ends = now + int(duration_sec)

    qs = get_random_questions(test_id, limit=int(questions_limit))

    with connect() as conn:
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO test_sessions(user_id, username, test_id, test_name, started_at, ends_at, duration_sec)
        VALUES (?,?,?,?,?,?,?)
        """, (int(user_id), username or "", int(test_id), test_name, now, ends, int(duration_sec)))
        session_id = int(cur.lastrowid)

        for q in qs:
            qid = int(q["id"])
            options = json.loads(q["options_json"])
            correct = int(q["correct_index"])

            indexed = list(enumerate(options))
            random.shuffle(indexed)
            new_options = [x[1] for x in indexed]

            old_to_new = {old_i: new_i for new_i, (old_i, _) in enumerate(indexed)}
            new_correct = old_to_new[correct]

            cur.execute("""
            INSERT INTO test_session_questions(session_id, question_id, options_json, correct_index)
            VALUES (?,?,?,?)
            """, (session_id, qid, json.dumps(new_options, ensure_ascii=False), int(new_correct)))

    return session_id


def get_session(session_id: int):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM test_sessions WHERE id=?", (int(session_id),))
        return cur.fetchone()


def set_session_messages(session_id: int, timer_message_id: int, question_message_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE test_sessions SET timer_message_id=?, question_message_id=? WHERE id=?",
            (int(timer_message_id), int(question_message_id), int(session_id))
        )


def get_session_question(session_id: int, index: int):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT * FROM test_session_questions
        WHERE session_id=?
        ORDER BY id ASC
        LIMIT 1 OFFSET ?
        """, (int(session_id), int(index)))
        return cur.fetchone()


def count_session_questions(session_id: int) -> int:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM test_session_questions WHERE session_id=?", (int(session_id),))
        row = cur.fetchone()
    return int(row["c"])


def save_answer(session_id: int, question_id: int, chosen_index: int, is_correct: int) -> None:
    with connect() as conn:
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO test_session_answers(session_id, question_id, chosen_index, is_correct)
        VALUES (?,?,?,?)
        """, (int(session_id), int(question_id), int(chosen_index), int(is_correct)))

        cur.execute("""
        UPDATE test_sessions
        SET correct_count = correct_count + ?, current_index = current_index + 1
        WHERE id=?
        """, (1 if int(is_correct) else 0, int(session_id)))


def finish_session(session_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE test_sessions SET is_finished=1 WHERE id=?", (int(session_id),))


# =========================
# SETTINGS
# =========================
SETTINGS_DEFAULTS = {
    "tests_enabled": "1",
    "sub_enabled": "1",
    "sub_pay_click_enabled": "1",
    "sub_pay_stars_enabled": "0",
    "sub_referral_enabled": "1",
    "sub_channel_enabled": "0",
    "ref_need_count": "3",
    "ref_bonus_days": "7",
    "channel_bonus_days": "7",
    "required_channels_json": "[]",
}


def init_settings_table() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
        for k, v in SETTINGS_DEFAULTS.items():
            cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?,?)", (k, v))


def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO settings(key, value) VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, value))


def is_tests_enabled() -> bool:
    return get_setting("tests_enabled", "1") == "1"


def get_bool_setting(key: str, default: str = "0") -> bool:
    return get_setting(key, default) == "1"


def toggle_bool_setting(key: str, default: str = "0") -> bool:
    curv = get_setting(key, default)
    newv = "0" if curv == "1" else "1"
    set_setting(key, newv)
    return newv == "1"


def set_bool_setting(key: str, val: bool) -> None:
    set_setting(key, "1" if val else "0")


# admin.py eski importlari uchun
def get_bool(key: str, default: bool = False) -> bool:
    return get_bool_setting(key, "1" if default else "0")


def toggle_bool(key: str, default: bool = False) -> bool:
    return toggle_bool_setting(key, "1" if default else "0")


# =========================
# SUBSCRIPTIONS
# =========================
def init_subscriptions_table() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            until_ts INTEGER NOT NULL
        )
        """)


def is_sub_active(user_id: int) -> bool:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT until_ts FROM subscriptions WHERE user_id=?", (int(user_id),))
        row = cur.fetchone()
    if not row:
        return False
    return int(row["until_ts"]) > int(time.time())


def grant_sub_days(user_id: int, days: int = 30) -> None:
    until = int(time.time()) + int(days) * 24 * 3600
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO subscriptions(user_id, until_ts)
        VALUES(?,?)
        ON CONFLICT(user_id) DO UPDATE SET until_ts=excluded.until_ts
        """, (int(user_id), until))


# =========================
# BLOCKED USERS (ASOSIY BLOK)
# =========================
def init_blocked_users_table() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS blocked_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            blocked_at TEXT DEFAULT (datetime('now'))
        )
        """)


def block_user(user_id: int, username: str = "", full_name: str = "") -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO blocked_users(user_id, username, full_name, blocked_at)
            VALUES(?,?,?, datetime('now'))
        """, (int(user_id), username or "", full_name or ""))


def unblock_user(user_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM blocked_users WHERE user_id=?", (int(user_id),))


def is_user_blocked(user_id: int) -> bool:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM blocked_users WHERE user_id=? LIMIT 1", (int(user_id),))
        row = cur.fetchone()
    return row is not None


def list_blocked_users(limit: int = 500) -> list[dict]:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, username, full_name, blocked_at
            FROM blocked_users
            ORDER BY blocked_at DESC
            LIMIT ?
        """, (int(limit),))
        rows = cur.fetchall()
    return [dict(r) for r in rows]


# =========================
# BROADCAST LOG (postlarni keyin o‘chirish uchun)
# =========================
def init_broadcast_tables() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            admin_id INTEGER
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_messages (
            broadcast_id INTEGER,
            user_id INTEGER,
            chat_id INTEGER,
            message_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (broadcast_id, user_id, message_id)
        )
        """)


def create_broadcast(admin_id: int) -> int:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO broadcasts(admin_id) VALUES(?)", (int(admin_id),))
        return int(cur.lastrowid)


def log_broadcast_message(broadcast_id: int, user_id: int, chat_id: int, message_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO broadcast_messages(broadcast_id, user_id, chat_id, message_id)
            VALUES(?,?,?,?)
        """, (int(broadcast_id), int(user_id), int(chat_id), int(message_id)))


def list_broadcasts(limit: int = 50) -> list[dict]:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, created_at, admin_id
            FROM broadcasts
            ORDER BY id DESC
            LIMIT ?
        """, (int(limit),))
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def list_broadcast_messages(broadcast_id: int) -> list[dict]:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, chat_id, message_id
            FROM broadcast_messages
            WHERE broadcast_id=?
            ORDER BY user_id ASC
        """, (int(broadcast_id),))
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def delete_broadcast(broadcast_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM broadcast_messages WHERE broadcast_id=?", (int(broadcast_id),))
        cur.execute("DELETE FROM broadcasts WHERE id=?", (int(broadcast_id),))

#====================
def search_general_subjects(q: str, limit: int = 30):
    conn = connect()
    cur = conn.cursor()
    like = f"%{q.strip()}%"
    cur.execute(
        "SELECT id, name FROM general_subjects WHERE name LIKE ? ORDER BY name ASC LIMIT ?",
        (like, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def search_general_files(q: str, limit: int = 30):
    conn = connect()
    cur = conn.cursor()
    like = f"%{q.strip()}%"
    cur.execute(
        """
        SELECT gf.id, gf.subject_id, gf.file_name, gf.message_id, gs.name AS subject_name
        FROM general_files gf
        JOIN general_subjects gs ON gs.id = gf.subject_id
        WHERE gf.file_name LIKE ?
        ORDER BY gf.file_name ASC
        LIMIT ?
        """,
        (like, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return rows

# =========================
# POLL STATS (poll natijalarini ko‘rish uchun)
# =========================
def init_poll_tables() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_id INTEGER,
            question TEXT,
            options_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS poll_instances (
            poll_id TEXT PRIMARY KEY,         -- Telegram poll_id
            poll_row_id INTEGER,              -- polls.id
            user_id INTEGER,
            sent_message_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS poll_votes (
            poll_id TEXT,
            user_id INTEGER,
            option_ids_json TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (poll_id, user_id)
        )
        """)


def create_poll_row(broadcast_id: int, question: str, options: list[str]) -> int:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO polls(broadcast_id, question, options_json) VALUES(?,?,?)",
            (int(broadcast_id), question, json.dumps(options, ensure_ascii=False))
        )
        return int(cur.lastrowid)


def save_poll_instance(poll_id: str, poll_row_id: int, user_id: int, sent_message_id: int) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO poll_instances(poll_id, poll_row_id, user_id, sent_message_id)
            VALUES(?,?,?,?)
        """, (poll_id, int(poll_row_id), int(user_id), int(sent_message_id)))


def upsert_poll_vote(poll_id: str, user_id: int, option_ids: list[int]) -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO poll_votes(poll_id, user_id, option_ids_json, updated_at)
            VALUES(?,?,?, datetime('now'))
        """, (poll_id, int(user_id), json.dumps(option_ids)))

def get_poll_row_id_by_poll_id(poll_id: str):
    """
    Telegram poll_id (string) -> polls jadvalidagi poll_row_id (int) ni qaytaradi.
    poll_instances jadvalidan olinadi.
    """
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT poll_row_id FROM poll_instances WHERE poll_id=? LIMIT 1", (poll_id,))
        row = cur.fetchone()

    if not row:
        return None

    # sqlite Row bo'lsa:
    try:
        return int(row["poll_row_id"])
    except Exception:
        # tuple bo'lsa:
        return int(row[0])


def list_polls(limit: int = 30) -> list[dict]:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, broadcast_id, question, created_at
            FROM polls
            ORDER BY id DESC
            LIMIT ?
        """, (int(limit),))
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_poll_summary(poll_row_id: int):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT question, options_json FROM polls WHERE id=?", (int(poll_row_id),))
        p = cur.fetchone()
        if not p:
            return None

        question = p["question"]
        options = json.loads(p["options_json"])

        cur.execute("SELECT poll_id FROM poll_instances WHERE poll_row_id=?", (int(poll_row_id),))
        poll_ids = [r["poll_id"] for r in cur.fetchall()]

        counts = [0] * len(options)
        if poll_ids:
            q = f"SELECT option_ids_json FROM poll_votes WHERE poll_id IN ({','.join(['?'] * len(poll_ids))})"
            cur.execute(q, poll_ids)
            for r in cur.fetchall():
                ids = json.loads(r["option_ids_json"])
                for i in ids:
                    if 0 <= i < len(counts):
                        counts[i] += 1

    return question, options, counts


def clear_poll_stats() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM poll_votes")
        cur.execute("DELETE FROM poll_instances")
        cur.execute("DELETE FROM polls")

# =========================
# ONE CALL INIT
# =========================
def init_all() -> None:
    init_db()
    init_bot_messages()
    init_library_tables()
    init_exam_tables()
    init_tests_tables()
    init_test_sessions_tables()
    init_settings_table()
    init_subscriptions_table()
    init_blocked_users_table()
    init_broadcast_tables()
    init_poll_tables()
    init_general_books_tables()

    try:
        migrate_questions_table()
    except Exception:
        pass