# generate_act.py
"""Генерация акта из шаблона .docx."""

import logging
from datetime import datetime
from pathlib import Path

from docxtpl import DocxTemplate

from config import ACTS_DIR, TEMPLATE_PATH

logger = logging.getLogger(__name__)


class TemplateDataError(RuntimeError):
    """В данных не хватает переменных, которые требует шаблон."""


def split_with_limits(text, limits):
    """
    Разбивает текст на строки с индивидуальными лимитами символов.
    limits — список максимальных длин для каждой строки.
    """
    if not text:
        return ["" for _ in limits]

    text = text.strip()
    total = sum(limits)
    if len(text) > total:
        text = text[: total - 1].rstrip() + "…"

    lines = []
    remaining = text
    for limit in limits:
        if not remaining:
            lines.append("")
            continue
        if len(remaining) <= limit:
            lines.append(remaining.strip())
            remaining = ""
            continue
        cut = remaining.rfind(" ", 0, limit + 1)
        if cut == -1:
            cut = limit
        lines.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    return lines


def build_act(
    data: dict,
    template: str | Path | None = None,
    out_path: str | Path | None = None,
) -> Path:
    """
    Заполняет шаблон данными и сохраняет готовый акт.

    Возвращает фактический путь сохранённого файла. Если целевой файл занят
    (открыт в Word), сохраняет рядом с суффиксом времени и возвращает новый путь.
    """
    template_path = Path(template) if template else TEMPLATE_PATH
    target = Path(out_path) if out_path else ACTS_DIR / "act.docx"
    target.parent.mkdir(parents=True, exist_ok=True)

    doc = DocxTemplate(template_path)

    required = doc.get_undeclared_template_variables()
    missing = required - set(data.keys())
    if missing:
        names = ", ".join(sorted(missing))
        raise TemplateDataError(f"В данных не хватает переменных: {names}")

    doc.render(data)

    try:
        doc.save(target)
        return target
    except PermissionError:
        stamp = datetime.now().strftime("%H%M%S")
        new_path = target.with_name(f"{target.stem}_{stamp}{target.suffix}")
        doc.save(new_path)
        logger.warning("Файл %s занят, сохранено как %s", target, new_path)
        return new_path
