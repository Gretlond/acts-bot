# utils.py
"""
Общие утилиты для handlers_*.py.
Чистые функции без aiogram-роутеров.
"""
import re
import json

from db import get_conn, get_positions_for_object
from generate_act import split_with_limits
from keyboards import positions_grouped_kb


MONTHS_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

CERT_DOC_TYPES = {
    "passport_quality": "паспорт качества",
    "cert_quality": "сертификат качества",
    "cert_conformity": "сертификат соответствия",
}


def _date_dict(d, m, y):
    if not (1 <= d <= 31 and 1 <= m <= 12 and 2000 <= y <= 2100):
        raise ValueError("Некорректная дата")
    return {
        "day": str(d).zfill(2),
        "month_num": str(m).zfill(2),
        "month_name": MONTHS_RU[m],
        "year": str(y),
        "full": f"{str(d).zfill(2)}.{str(m).zfill(2)}.{y} г.",
    }


def parse_date(text: str) -> dict:
    text = text.strip().replace("/", ".").replace("-", ".")
    text = text.rstrip(" г.").rstrip("г.").rstrip()
    parts = text.split(".")
    if len(parts) != 3:
        raise ValueError("Ожидается формат ДД.ММ.ГГГГ")
    return _date_dict(int(parts[0]), int(parts[1]), int(parts[2]))


def parse_dates_range(text: str):
    text = text.strip()
    m = re.match(
        r'^(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\s*[-\u2013\u2014]\s*'
        r'(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})$',
        text
    )
    if m:
        start = _date_dict(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        end = _date_dict(int(m.group(4)), int(m.group(5)), int(m.group(6)))
        return start, end
    m = re.match(r'^(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})$', text)
    if m:
        d = _date_dict(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d, d
    raise ValueError("Формат: ДД.ММ.ГГГГ или ДД.ММ.ГГГГ - ДД.ММ.ГГГГ")


def format_materials_with_certs(selected, certs_result):
    if not selected:
        return ""
    parts = []
    for m in selected:
        cert = (certs_result or {}).get(str(m["id"]), "")
        cert = (cert or "").strip()
        if cert:
            parts.append(f"{m['name']} ({cert})")
        else:
            parts.append(m["name"])
    return ", ".join(parts)


def safe_filename(act_number, cipher):
    safe = "".join(c if c.isalnum() else "_" for c in (cipher or "na"))[:30]
    return f"act_{act_number}_{safe}.docx"


def strip_outer_quotes(text):
    """Убирает внешние кавычки, если шаблон сам их добавляет."""
    value = (text or "").strip()
    for left, right in (("«", "»"), ("“", "”"), ('"', '"')):
        if len(value) >= 2 and value.startswith(left) and value.endswith(right):
            return value[1:-1].strip()
    return value


def _join_nonempty(*parts):
    return " ".join(str(p).strip() for p in parts if p and str(p).strip())


def build_template_data(obj, full_work, sheets, cipher,
                        start_date, end_date, act_date,
                        materials_str, act_number,
                        author_supervision=False):
    top = split_with_limits(full_work, [74, 74])
    bot = split_with_limits(full_work, [25, 90, 90])
    project_name = strip_outer_quotes(obj.get("name"))
    obj_lines = split_with_limits(project_name, [70, 90])

    tech_full = _join_nonempty(
        obj.get("tech_post"), obj.get("tech_place"), obj.get("tech_name")
    )
    tech = split_with_limits(tech_full, [50, 90])

    if author_supervision:
        author_full = _join_nonempty(
            obj.get("author_post"), obj.get("author_place"),
            obj.get("author_name")
        )
    else:
        author_full = ""
    author = split_with_limits(author_full, [50, 90])

    project_firm = (obj.get("project_firm") or "").strip()
    project_date = (obj.get("project_date") or "").strip()
    project_parts = []
    if project_firm:
        project_parts.append(project_firm)
    project_parts.append(f"шифр {cipher or '—'}")
    sheets_part = f"листы № {sheets}" if sheets else "листы не указаны"
    if project_date:
        sheets_part += f" от {project_date}"
    project_parts.append(sheets_part)
    proj_full = ", ".join(project_parts)
    proj = split_with_limits(proj_full, [30, 90])

    mat = split_with_limits(materials_str, [74, 74, 74])

    return {
        "act_number": act_number,
        "work_top_1": top[0], "work_top_2": top[1],
        "work_bot_1": bot[0], "work_bot_2": bot[1], "work_bot_3": bot[2],
        "project_full_name1": obj_lines[0], "project_full_name2": obj_lines[1],
        "act_day": act_date["day"], "act_month": act_date["month_name"],
        "act_year": act_date["year"],
        "gen_person_post": obj.get("gen_person_post") or "",
        "gen_person_firm": obj.get("gen_contractor") or "",
        "gen_person": obj.get("gen_person") or "",
        "gen_short": obj.get("gen_short") or "",
        "subgen_person": obj.get("subgen_person") or "",
        "subgen_short": obj.get("subgen_short") or "",
        "tech_1": tech[0], "tech_2": tech[1],
        "tech_short": obj.get("tech_short") or "",
        "author_1": author[0], "author_2": author[1],
        "author_short": (obj.get("author_short") or "") if author_supervision else "",
        "project_doc_1": proj[0], "project_doc_2": proj[1],
        "materials_1": mat[0], "materials_2": mat[1], "materials_3": mat[2],
        "start_date": start_date["full"],
        "end_date": end_date["full"],
        "sign_d": act_date["full"],
        "sign_d_s": act_date["full"] if obj.get("subgen_short") else "",
        "sign_d_t": act_date["full"] if obj.get("tech_short") else "",
        "sign_d_a": act_date["full"] if author_supervision else "",
    }


def resolve_section_hint(item, available_sections):
    hint = item.get("section_hint")
    if hint and hint in available_sections:
        return hint
    if len(available_sections) == 1:
        return available_sections[0]
    return None


def cert_type_label(doc_type):
    """Код → человекочитаемое имя. Если не из словаря — как есть."""
    if not doc_type:
        return ""
    return CERT_DOC_TYPES.get(doc_type, doc_type)


def cert_label(cert):
    num = (cert.get("number") or "").strip()
    doc_type = (cert.get("doc_type") or "").strip()
    type_label = cert_type_label(doc_type)
    date_from = (cert.get("date_from") or "").strip()

    if not num and not type_label:
        return ""

    prefix = type_label if type_label else "сертификат"
    parts = [prefix]
    if num:
        parts.append(f"№{num}")
    if date_from:
        parts.append(f"от {date_from}")
    return " ".join(parts)


def materials_to_json(selected, certs_result):
    result = []
    for m in selected:
        cert = (certs_result or {}).get(str(m["id"]), "") or ""
        result.append({"id": m["id"], "name": m["name"], "cert": cert})
    return json.dumps(result, ensure_ascii=False)


def materials_from_json(raw):
    if not raw:
        return [], {}
    try:
        data = json.loads(raw)
    except Exception:
        return [], {}
    selected_ids = []
    certs_result = {}
    for item in data:
        mid = item.get("id")
        if mid is None:
            continue
        selected_ids.append(mid)
        if item.get("cert"):
            certs_result[str(mid)] = item["cert"]
    return selected_ids, certs_result


def _parse_date_or_none(raw):
    if not raw:
        return None
    try:
        return parse_date(raw)
    except Exception:
        return None


def _range_str_from_numbers(numbers):
    nums = []
    for n in numbers:
        try:
            nums.append(int(n))
        except (ValueError, TypeError):
            pass
    if not nums:
        return ""
    nums = sorted(set(nums))
    if len(nums) == 1:
        return str(nums[0])
    if nums == list(range(nums[0], nums[-1] + 1)):
        return f"{nums[0]}-{nums[-1]}"
    return ",".join(str(n) for n in nums)


def _first_position_number(numbers):
    nums = []
    for n in numbers:
        try:
            nums.append((int(n), n))
        except (ValueError, TypeError):
            pass
    if not nums:
        return numbers[0] if numbers else ""
    nums.sort()
    return nums[0][1]


def _get_cipher_map(object_id):
    """position_number → первый cipher по этой позиции."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT position_number, cipher FROM drawings "
        "WHERE object_id = ? ORDER BY position_number, cipher",
        (object_id,)
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        pos = r["position_number"]
        if pos and pos not in result:
            result[pos] = r["cipher"]
    return result


def build_position_groups(positions, cipher_map=None):
    """Группировка по (имя, cipher). Разделяет 21-28 и 29-32."""
    from collections import OrderedDict
    cipher_map = cipher_map or {}
    real, virtual = [], []
    for p in positions:
        num = (p.get("position_number") or "").strip()
        if num:
            real.append(p)
        else:
            virtual.append(p)

    groups_map = OrderedDict()
    for p in real:
        num = (p.get("position_number") or "").strip()
        key = (
            (p.get("name") or "").strip().lower(),
            cipher_map.get(num, ""),
        )
        groups_map.setdefault(key, []).append(p)

    result = []
    for _, items in groups_map.items():
        result.append({
            "name": items[0].get("name") or "",
            "positions": items,
            "numbers": [x.get("position_number") or "" for x in items],
        })
    for p in virtual:
        result.append({
            "name": p.get("name") or "",
            "positions": [p],
            "numbers": [],
        })
    return result


def split_materials_by_work_type(materials, work_type):
    """Множество id материалов, подходящих по типу работы."""
    if not work_type:
        return set()
    wt_lower = work_type.strip().lower()
    result = set()
    for m in materials:
        raw = (m.get("work_types") or "").lower()
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        if any(wt_lower == p or wt_lower in p for p in parts):
            result.add(m["id"])
    return result


async def _show_positions_menu(message, state, prefix="📍 Выберите позицию:"):
    """Показывает сгруппированный список позиций."""
    data = await state.get_data()
    object_id = data["object_id"]
    positions = get_positions_for_object(object_id)
    cipher_map = _get_cipher_map(object_id)
    groups = build_position_groups(positions, cipher_map)
    await state.update_data(position_groups=groups)
    await message.answer(prefix,
                         reply_markup=positions_grouped_kb(groups))