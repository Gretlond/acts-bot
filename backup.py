# backup.py
"""Резервные копии SQLite и файлов актов/сертификатов."""

import asyncio
import logging
import os
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    ACTS_DIR,
    BACKUP_RETENTION,
    BACKUPS_DIR,
    CERTIFICATES_DIR,
    DB_PATH,
    ensure_dirs,
)

logger = logging.getLogger(__name__)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _cleanup(prefix: str, suffix: str) -> None:
    files = sorted(
        BACKUPS_DIR.glob(f"{prefix}_*{suffix}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old in files[BACKUP_RETENTION:]:
        try:
            old.unlink()
        except OSError as exc:
            logger.warning("Не удалось удалить старый бэкап %s: %s", old, exc)


def backup_database(reason: str = "manual") -> Path | None:
    """Копия через SQLite backup API — безопасно при работающем боте."""
    ensure_dirs()
    if not DB_PATH.exists():
        return None
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUPS_DIR / f"acts_{_stamp()}_{reason}.db"
    temp = target.with_suffix(".db.tmp")
    temp.unlink(missing_ok=True)
    source = sqlite3.connect(str(DB_PATH), timeout=30)
    try:
        destination = sqlite3.connect(str(temp))
        try:
            source.backup(destination)
            destination.commit()
        finally:
            destination.close()
        os.replace(temp, target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    finally:
        source.close()
    _cleanup("acts", ".db")
    logger.info("Резервная копия БД: %s", target.name)
    return target


def _iter_files(folder: Path):
    if not folder.exists():
        return
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(folder)
        if any(part in {"_deleted", "_old", "_archive", "_packages"} for part in relative.parts):
            continue
        if path.name.startswith(".") or path.name.startswith("~$"):
            continue
        if path.suffix.lower() in {".bak", ".tmp"}:
            continue
        yield path, Path(folder.name) / relative


def backup_files(reason: str = "manual") -> Path | None:
    """ZIP с текущими актами и сертификатами (без служебных архивов)."""
    ensure_dirs()
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUPS_DIR / f"files_{_stamp()}_{reason}.zip"
    temp = target.with_suffix(".zip.tmp")
    temp.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
            for folder in (ACTS_DIR, CERTIFICATES_DIR):
                for path, arcname in _iter_files(folder):
                    archive.write(path, arcname.as_posix())
        os.replace(temp, target)
        _cleanup("files", ".zip")
        logger.info("Резервная копия файлов: %s", target.name)
        return target
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def run_backup(reason: str = "manual") -> tuple[Path | None, Path | None]:
    """Последовательно делает обе копии; ошибка одной не мешает другой."""
    db_copy = files_copy = None
    try:
        db_copy = backup_database(reason)
    except Exception:
        logger.exception("Ошибка резервной копии БД")
    try:
        files_copy = backup_files(reason)
    except Exception:
        logger.exception("Ошибка резервной копии файлов")
    return db_copy, files_copy


async def backup_loop() -> None:
    """Ежедневно в 03:00 по локальному времени."""
    while True:
        now = datetime.now()
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep(max(60, (next_run - now).total_seconds()))
        await asyncio.to_thread(run_backup, "daily")
