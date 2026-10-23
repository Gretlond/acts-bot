# storage.py
"""Файловые операции с готовыми актами."""
import logging
import shutil
from datetime import datetime

from config import DELETED_DIR, resolve_path


logger = logging.getLogger(__name__)


def archive_act_file(file_path):
    """
    Переносит файл акта в acts/_deleted/ с отметкой времени.

    Возвращает новый путь или None, если файла нет/перенести не удалось.
    """
    if not file_path:
        return None
    source = resolve_path(file_path)
    if not source.exists():
        return None

    DELETED_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = DELETED_DIR / f"{stamp}_{source.name}"
    counter = 1
    while target.exists():
        target = DELETED_DIR / f"{stamp}_{counter}_{source.name}"
        counter += 1

    try:
        shutil.move(str(source), str(target))
        return target
    except OSError as e:
        logger.warning("Не удалось перенести %s в архив: %s", source, e)
        return None
