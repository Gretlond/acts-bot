# config.py
"""
Единая конфигурация бота: пути, токен, белый список пользователей.

Все пути считаются от каталога проекта (рядом с этим файлом), поэтому бот
можно запускать из любой рабочей директории.
"""
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


def _path_from_env(name: str, default: Path) -> Path:
    raw = (os.getenv(name) or "").strip()
    path = Path(raw).expanduser() if raw else default
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


# ---------- ПУТИ ----------
DB_PATH = _path_from_env("DB_PATH", ROOT_DIR / "acts.db")
PROJECT_DIR = _path_from_env("PROJECT_DIR", ROOT_DIR / "project")
ACTS_DIR = _path_from_env("ACTS_DIR", ROOT_DIR / "acts")
DELETED_DIR = ACTS_DIR / "_deleted"
TEMPLATE_PATH = _path_from_env("TEMPLATE_PATH", ROOT_DIR / "shablonact.docx")

# ---------- TELEGRAM ----------
# Проверка токена — при запуске bot.py; утилитам и seed-скриптам токен не нужен.
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()

MAX_TELEGRAM_SIZE_MB = int(os.getenv("MAX_TELEGRAM_SIZE_MB", "50"))


def _ids_from_env(name: str) -> set[int]:
    """'123, 456;789' -> {123, 456, 789}."""
    raw = os.getenv(name, "")
    result: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.lstrip("-").isdigit():
            result.add(int(chunk))
    return result


ADMIN_IDS = _ids_from_env("ADMIN_IDS")
ALLOWED_USER_IDS = _ids_from_env("ALLOWED_USER_IDS") | ADMIN_IDS

# Если список не заполнен — бот открыт для всех (с предупреждением при старте).
ACCESS_OPEN = not ALLOWED_USER_IDS


def is_user_allowed(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return ACCESS_OPEN or user_id in ALLOWED_USER_IDS


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in ADMIN_IDS


# ---------- ПУТИ: ХЕЛПЕРЫ ----------
def resolve_path(path: str | os.PathLike) -> Path:
    """Относительный путь из БД -> абсолютный путь на диске."""
    p = Path(str(path))
    if not p.is_absolute():
        p = ROOT_DIR / p
    return p.resolve()


def to_stored_path(path: str | os.PathLike) -> str:
    """Абсолютный путь -> относительный (для хранения в БД)."""
    p = Path(path).resolve()
    try:
        return p.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return str(p)


def ensure_dirs() -> None:
    for folder in (ACTS_DIR, DELETED_DIR, PROJECT_DIR, DB_PATH.parent):
        folder.mkdir(parents=True, exist_ok=True)
