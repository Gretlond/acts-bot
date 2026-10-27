# act_service.py
"""Сохранение акта: файл и запись БД не должны расходиться."""

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from config import to_stored_path
from db import save_act, update_act
from generate_act import build_act
from storage import archive_old_act_file
from utils import date_range_is_valid

logger = logging.getLogger(__name__)


def _temp_path(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.with_name(f".{target.stem}.{uuid.uuid4().hex}.tmp.docx")


def _fallback_path(target: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for index in range(100):
        suffix = f"_{stamp}" + (f"_{index}" if index else "")
        candidate = target.with_name(f"{target.stem}{suffix}{target.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("Не удалось подобрать имя файла: слишком много копий")


def _install_temp(temp: Path, target: Path):
    """Ставит temp на место target. Возвращает final, backup, original."""
    original = target
    backup = None
    if target.exists():
        backup_candidate = target.with_name(f".{target.name}.{uuid.uuid4().hex}.bak")
        try:
            os.replace(target, backup_candidate)
            backup = backup_candidate
        except PermissionError:
            # Старый файл занят Word: оставляем его, новый положим рядом.
            backup = None

    try:
        os.replace(temp, target)
        return target, backup, original
    except PermissionError:
        if backup and backup.exists():
            os.replace(backup, original)
            backup = None
    except Exception:
        if backup and backup.exists():
            try:
                os.replace(backup, original)
            except OSError:
                pass
        temp.unlink(missing_ok=True)
        raise

    fallback = _fallback_path(target)
    try:
        os.replace(temp, fallback)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return fallback, None, original


def _rollback(final: Path, backup: Path | None, original: Path) -> None:
    try:
        if final.exists():
            final.unlink()
    except OSError as exc:
        logger.warning("Не удалось удалить новый файл %s: %s", final, exc)
    if backup and backup.exists():
        try:
            os.replace(backup, original)
        except OSError as exc:
            logger.error("Не удалось восстановить старый файл %s: %s", original, exc)


def _finalize(
    backup: Path | None, old_path: str | Path | None, final: Path, original: Path
) -> None:
    if backup and backup.exists():
        archive_old_act_file(backup)
    if old_path:
        old = Path(old_path)
        if not old.is_absolute():
            from config import resolve_path

            old = resolve_path(old)
        if old != final and old.exists():
            archive_old_act_file(old)


def create_act_with_file(template_data: dict, target: str | Path, **save_kwargs):
    """Собрать .docx, поставить файл, затем записать акт в БД.

    Если запись в БД не удалась, файл откатывается/удаляется. При успехе
    предыдущая версия файла (если была) уходит в acts/_old/.
    """
    target = Path(target)
    save_kwargs.pop("file_path", None)
    temp = _temp_path(target)
    final = None
    original = target
    backup = None
    try:
        built = Path(build_act(template_data, out_path=temp))
        if built != temp:
            temp = built
        final, backup, original = _install_temp(temp, target)
        act_id = save_act(file_path=to_stored_path(final), **save_kwargs)
    except Exception:
        if final is not None:
            _rollback(final, backup, original)
        else:
            temp.unlink(missing_ok=True)
        raise
    _finalize(backup, None, final, original)
    return final, act_id


def update_act_with_file(
    act_id: int,
    template_data: dict,
    target: str | Path,
    old_path: str | Path | None = None,
    **update_kwargs,
):
    """Пересобрать существующий акт и обновить запись атомарно."""
    target = Path(target)
    update_kwargs.pop("file_path", None)
    temp = _temp_path(target)
    final = None
    original = target
    backup = None
    try:
        built = Path(build_act(template_data, out_path=temp))
        if built != temp:
            temp = built
        final, backup, original = _install_temp(temp, target)
        update_act(act_id, file_path=to_stored_path(final), **update_kwargs)
    except Exception:
        if final is not None:
            _rollback(final, backup, original)
        else:
            temp.unlink(missing_ok=True)
        raise
    _finalize(backup, old_path, final, original)
    return final


def validate_act_payload(
    *,
    act_number,
    work_type_name,
    work_name,
    full_work,
    start_date,
    end_date,
    position_number,
    selected_materials,
    certs_result,
    duplicate=None,
):
    """Возвращает (ошибки, предупреждения) перед финальным сохранением."""
    errors: list[str] = []
    warnings: list[str] = []

    if not str(act_number or "").strip():
        errors.append("не указан номер акта")
    if not str(full_work or "").strip() and not (
        str(work_type_name or "").strip() or str(work_name or "").strip()
    ):
        errors.append("не указана работа")
    if not start_date or not end_date:
        errors.append("не указаны даты начала/окончания")
    elif not date_range_is_valid(start_date, end_date):
        errors.append("дата окончания раньше даты начала")
    if not str(position_number or "").strip():
        warnings.append("позиция не указана (акт без номера позиции)")

    selected = list(selected_materials or [])
    if not selected:
        warnings.append("материалы не выбраны")
    else:
        missing = [
            (m.get("name") or f"ID {m.get('id')}")
            for m in selected
            if not str((certs_result or {}).get(str(m.get("id")), "")).strip()
        ]
        if missing:
            warnings.append("нет сертификата/паспорта у материалов: " + ", ".join(missing))

    if duplicate:
        duplicate_number = duplicate.get("act_number") or "?"
        duplicate_date = duplicate.get("act_date") or "дата не указана"
        warnings.append(
            f"похожий акт уже есть: №{duplicate_number} "
            f"({duplicate_date}). Проверьте, не создаёте ли дубль"
        )
    return errors, warnings


def validation_text(errors, warnings) -> str:
    parts = []
    if errors:
        parts.append("❌ Нельзя сохранить:\n• " + "\n• ".join(errors))
    if warnings:
        parts.append("⚠️ Проверка комплектности:\n• " + "\n• ".join(warnings))
    return "\n\n".join(parts)
