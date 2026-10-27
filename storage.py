# storage.py
"""Перемещение файлов актов в служебные архивы."""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from config import ACTS_DIR, ARCHIVE_DIR, DELETED_DIR, OLD_DIR, resolve_path

logger = logging.getLogger(__name__)


def _unique_target(folder: Path, source: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = folder / f"{stamp}_{source.name}"
    counter = 1
    while target.exists():
        target = folder / f"{stamp}_{counter}_{source.name}"
        counter += 1
    return target


def _move(source: Path, folder: Path) -> Path | None:
    if not source.exists():
        return None
    target = _unique_target(folder, source)
    try:
        shutil.move(str(source), str(target))
        return target
    except OSError as exc:
        logger.warning("Не удалось переместить %s в %s: %s", source, folder, exc)
        return None


def archive_act_file(file_path):
    """Удалённый акт -> acts/_deleted/."""
    if not file_path:
        return None
    return _move(resolve_path(file_path), DELETED_DIR)


def archive_old_act_file(file_path):
    """Старая версия акта после редактирования -> acts/_old/."""
    if not file_path:
        return None
    return _move(resolve_path(file_path), OLD_DIR)


def archive_act_to_archive(file_path, year: str | int | None = None):
    """Акт, выведенный из активной работы -> acts/_archive/[год]/."""
    if not file_path:
        return None
    folder = ARCHIVE_DIR / str(year) if year else ARCHIVE_DIR
    return _move(resolve_path(file_path), folder)


def restore_archived_act(file_path):
    """Возвращает файл из acts/_archive обратно в acts/ (для «вернуть»)."""
    if not file_path:
        return None
    source = resolve_path(file_path)
    if source.exists():
        return source
    name = source.name
    matches = list(ARCHIVE_DIR.rglob(name)) if ARCHIVE_DIR.exists() else []
    if not matches:
        return None
    ACTS_DIR.mkdir(parents=True, exist_ok=True)
    target = ACTS_DIR / name
    counter = 1
    while target.exists():
        target = ACTS_DIR / f"{source.stem}_{counter}{source.suffix}"
        counter += 1
    try:
        shutil.move(str(matches[0]), str(target))
        return target
    except OSError as exc:
        logger.warning("Не удалось вернуть акт из архива %s: %s", source, exc)
        return None


def move_legacy_bak_files():
    """Переносит старые *.bak из acts/ в acts/_old/ (однократное обслуживание)."""
    if not ACTS_DIR.exists():
        return 0
    moved = 0
    for path in ACTS_DIR.glob("*.bak"):
        if path.is_file() and archive_old_act_file(path):
            moved += 1
    if moved:
        logger.info("Перенесено старых .bak в acts/_old: %s", moved)
    return moved
