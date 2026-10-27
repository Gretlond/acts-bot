# docs.py
"""Работа с PDF: поиск по позиции и разделу, отправка в Telegram."""

import os
from pathlib import Path

from aiogram.types import FSInputFile

from config import MAX_TELEGRAM_SIZE_MB, PROJECT_DIR
from db import get_drawing


def get_pdf_path(object_id, position_number, section):
    """
    Находит PDF. Возвращает (full_path, record, error).
    """
    rec = get_drawing(object_id, position_number, section)
    if not rec:
        return None, None, "PDF для этой позиции и раздела не найден"

    full_path = Path(PROJECT_DIR) / rec["file_path"]
    if not full_path.exists():
        return None, rec, f"Файл отсутствует на диске: {rec['file_path']}"

    return full_path, rec, None


def check_size(full_path):
    """Проверяет, что файл не слишком большой для Telegram."""
    size_bytes = os.path.getsize(full_path)
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > MAX_TELEGRAM_SIZE_MB:
        return (
            False,
            size_mb,
            (
                f"Файл {size_mb:.1f} МБ — больше лимита Telegram "
                f"({MAX_TELEGRAM_SIZE_MB} МБ). Откройте его из папки project/"
            ),
        )
    return True, size_mb, None


def make_input_file(full_path):
    return FSInputFile(full_path)
