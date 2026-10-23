# sync.py
"""
Синхронизация проектной документации из папки project/ в БД.
"""
import os
import re

from config import PROJECT_DIR
from db import (
    init_db, get_all_objects,
    add_position, add_drawing, clear_drawings_for_object,
    get_positions_for_object,
)

SKIP_PREFIXES = ["1. Инжереные сети и ГП", "Сметная документация"]

SECTIONS = [
    "АОВ", "ЭОМ", "НВКТ", "НВК", "АМВ", "ЭМО",
    "АР", "КЖ", "КМ", "ТХ", "ВК", "ОВ", "ЭГ",
    "МВ", "ПЗ", "ГП", "ЭС", "ЭН", "ТК", "ОДД",
]


def parse_positions_list(s):
    out = []
    # Нормализация: '29...32' или '29..32' → '29-32'
    s = s.replace('...', '-').replace('..', '-')
    for token in re.split(r'[,;]', s):
        token = token.strip().replace(' ', '')
        if not token:
            continue
        rng = re.match(r'^(\d+)-(\d+)$', token)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            if a <= b and (b - a) < 30:
                out.extend(str(x) for x in range(a, b + 1))
            continue
        if re.match(r'^\d+(\.\d+)?$', token):
            out.append(token)
    return out


def compress_positions_to_str(positions):
    if not positions:
        return ""
    ints, other = [], []
    for p in positions:
        try:
            ints.append(int(p))
        except (ValueError, TypeError):
            other.append(str(p))
    ints = sorted(set(ints))
    parts = []
    if ints:
        start = prev = ints[0]
        for n in ints[1:]:
            if n == prev + 1:
                prev = n
                continue
            parts.append(str(start) if start == prev else f"{start}-{prev}")
            start = prev = n
        parts.append(str(start) if start == prev else f"{start}-{prev}")
    parts.extend(other)
    return ",".join(parts)


def parse_folder(folder_name):
    name = re.sub(r'^\d+\.\s*', '', folder_name)
    parts = re.split(r'поз\.?\s*', name, flags=re.IGNORECASE)
    if len(parts) == 1:
        return {}

    pos_to_name = {}
    current_name = parts[0].strip().rstrip(',').strip()

    for part in parts[1:]:
        part = part.strip()
        m = re.match(r'^([\d.,\-\s]+?)(?:,\s*([А-ЯЁа-яёA-Za-z].*))?$', part)
        if not m:
            continue
        nums = m.group(1).strip()
        tail = m.group(2)
        for pos in parse_positions_list(nums):
            if pos not in pos_to_name and current_name:
                pos_to_name[pos] = current_name
        if tail:
            current_name = tail.strip().rstrip(',').strip()

    return pos_to_name


def clean_folder_name(folder_name):
    return re.sub(r'^\d+\.\s*', '', folder_name).strip()


def parse_filename(filename):
    base = re.sub(r'\.pdf$', '', filename, flags=re.IGNORECASE)
    base_norm = base.replace('_', '-').replace(' ', '-')
    upper = base_norm.upper()

    m = re.search(r'08-ПР-25-([\d,.\-\s]+?)-([А-ЯЁ]{2,4})', upper)
    if not m:
        m = re.search(r'08-ПР25-([\d,.\-\s]+?)-([А-ЯЁ]{2,4})', upper)
    if not m:
        return [], None

    pos_str = m.group(1)
    section = m.group(2)
    if section not in SECTIONS:
        return [], None
    return parse_positions_list(pos_str), section


def should_skip(folder_name):
    for pref in SKIP_PREFIXES:
        if folder_name.strip().startswith(pref):
            return True
    return False


def collect_folders():
    result = []
    for dirpath, dirnames, filenames in os.walk(PROJECT_DIR):
        pdfs = [f for f in filenames if f.lower().endswith(".pdf")]
        if pdfs:
            result.append((os.path.basename(dirpath), dirpath))
    return result


def scan_only():
    result = {
        "positions": [],
        "drawings": [],
        "folders_count": 0,
        "skipped": [],
        "unassigned": [],
    }

    seen_positions = set()
    seen_virtual = set()

    folders = collect_folders()
    filtered = []
    for name, path in folders:
        if should_skip(name):
            result["skipped"].append(name)
        else:
            filtered.append((name, path))
    filtered.sort(key=lambda x: x[0])
    result["folders_count"] = len(filtered)

    for folder_name, _ in filtered:
        for pos, name in parse_folder(folder_name).items():
            key = (name, pos)
            if key not in seen_positions:
                seen_positions.add(key)
                result["positions"].append({"number": pos, "name": name})

    for folder_name, folder_path in filtered:
        pdfs = sorted([f for f in os.listdir(folder_path)
                       if f.lower().endswith(".pdf")])
        if not pdfs:
            continue

        folder_positions = parse_folder(folder_name)
        virtual_name = None
        if not folder_positions:
            virtual_name = clean_folder_name(folder_name)
            if virtual_name and virtual_name not in seen_virtual:
                seen_virtual.add(virtual_name)
                result["positions"].append({
                    "number": "", "name": virtual_name,
                })

        for pdf_name in pdfs:
            file_positions, section = parse_filename(pdf_name)
            if not section:
                continue

            rel_path = os.path.relpath(
                os.path.join(folder_path, pdf_name), PROJECT_DIR
            )

            if folder_positions:
                if file_positions:
                    cipher_pos_str = compress_positions_to_str(file_positions)
                    cipher = f"08-ПР/25-{cipher_pos_str}-{section}"
                else:
                    folder_pos_list = list(folder_positions.keys())
                    cipher_pos_str = compress_positions_to_str(folder_pos_list)
                    cipher = f"08-ПР/25-{cipher_pos_str}-{section}"
                for pos in folder_positions.keys():
                    result["drawings"].append({
                        "position_number": pos,
                        "section": section,
                        "cipher": cipher,
                        "file_path": rel_path,
                    })
            else:
                if 1 <= len(file_positions) <= 2:
                    cipher_pos_str = compress_positions_to_str(file_positions)
                    cipher = f"08-ПР/25-{cipher_pos_str}-{section}"
                    for pos in file_positions:
                        result["drawings"].append({
                            "position_number": pos,
                            "section": section,
                            "cipher": cipher,
                            "file_path": rel_path,
                        })
                elif len(file_positions) >= 3:
                    if virtual_name:
                        result["drawings"].append({
                            "position_number": "",
                            "section": section,
                            "cipher": f"08-ПР/25-?-{section}",
                            "file_path": rel_path,
                        })
                    else:
                        result["unassigned"].append({
                            "file": rel_path, "section": section,
                        })
                else:
                    if virtual_name:
                        result["drawings"].append({
                            "position_number": "",
                            "section": section,
                            "cipher": f"08-ПР/25-?-{section}",
                            "file_path": rel_path,
                        })
                    else:
                        result["unassigned"].append({
                            "file": rel_path, "section": section,
                        })

    return result


def apply_scan(object_id, scan_result):
    existing = set()
    for p in get_positions_for_object(object_id):
        key = ((p.get("name") or ""), (p.get("position_number") or ""))
        existing.add(key)

    added_pos = 0
    for p in scan_result["positions"]:
        name = p.get("name") or ""
        number = p.get("number") or ""
        key = (name, number)
        if key not in existing:
            add_position(object_id, name, number)
            existing.add(key)
            added_pos += 1

    clear_drawings_for_object(object_id)
    for d in scan_result["drawings"]:
        add_drawing(
            object_id=object_id,
            position_number=d.get("position_number") or "",
            section=d["section"],
            cipher=d["cipher"],
            file_path=d["file_path"],
        )

    return added_pos, len(scan_result["drawings"])


def sync(object_id):
    scan_result = scan_only()
    added_pos, added_drws = apply_scan(object_id, scan_result)
    print(f"✅ Позиций добавлено: {added_pos}")
    print(f"✅ Чертежей записано: {added_drws}")
    print(f"📂 Папок обработано: {scan_result['folders_count']}")
    if scan_result["unassigned"]:
        print(f"\n⚠️  Не привязано: {len(scan_result['unassigned'])}")
        for u in scan_result["unassigned"][:20]:
            print(f"   [{u['section']}] {u['file']}")


def main():
    init_db()
    objects = get_all_objects()
    if not objects:
        print("⚠️  В БД нет объектов. Запустите seed_object_only.py.")
        return
    obj = objects[0]
    print(f"🏗 Объект: {obj['name'][:70]}\n")
    sync(obj["id"])


if __name__ == "__main__":
    main()