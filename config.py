# config.py
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# .env har doim shu fayl (config.py) turgan papkadan olinadi
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)


def _read_str_env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(f"{name} topilmadi. Kutilgan joy: {ENV_PATH}")
    return val


def _read_int_env(name: str) -> int:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(f"{name} .env ichida yo‘q. Kutilgan joy: {ENV_PATH}")
    # -100... ham o‘tadi
    if not val.lstrip("-").isdigit():
        raise RuntimeError(f"{name} raqam bo‘lishi kerak (masalan: -1001234567890). Hozir: {val}")
    return int(val)


def _parse_admins(raw: str) -> set[int]:
    raw = (raw or "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for x in raw.split(","):
        x = x.strip()
        if x.lstrip("-").isdigit():
            out.add(int(x))
    return out


@dataclass(frozen=True)
class Config:
    bot_token: str
    admins: set[int]
    owner_id: int

    supergroup_id: int
    exam_supergroup_id: int
    general_books_supergroup_id: int


def load_config() -> Config:
    token = _read_str_env("BOT_TOKEN")

    admins = _parse_admins(os.getenv("ADMINS", ""))
    owner_id = _read_int_env("OWNER_ID")

    supergroup_id = _read_int_env("SUPERGROUP_ID")
    exam_supergroup_id = _read_int_env("EXAM_SUPERGROUP_ID")
    general_books_supergroup_id = _read_int_env("GENERAL_BOOKS_SUPERGROUP_ID")

    return Config(
        bot_token=token,
        admins=admins,
        owner_id=owner_id,
        supergroup_id=supergroup_id,
        exam_supergroup_id=exam_supergroup_id,
        general_books_supergroup_id=general_books_supergroup_id,
    )
