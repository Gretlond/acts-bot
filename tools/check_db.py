# tools/check_db.py
"""Показывает содержимое БД."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from db import (
    get_all_objects,
    get_positions_for_object,
    get_all_work_types,
    get_conn,
)


def main():
    # Типы работ
    wt = get_all_work_types()
    print(f"\n🔨 Типов работ в справочнике: {len(wt)}")
    for w in wt:
        print(f"   • {w['name']}")

    for obj in get_all_objects():
        print(f"\n🏗 Объект [{obj['id']}]: {obj['name'][:70]}")

        positions = get_positions_for_object(obj["id"])
        print(f"\n📍 Позиций: {len(positions)}\n")

        for p in positions:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM drawings " "WHERE object_id = ? AND position_number = ?",
                (obj["id"], p["position_number"]),
            )
            cnt = cur.fetchone()[0]
            conn.close()

            print(f"   поз. {p['position_number']:>7}  " f"{p['name']:<40}  PDF: {cnt}")

        # Разделы
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT section, COUNT(*) FROM drawings
            WHERE object_id = ? GROUP BY section ORDER BY COUNT(*) DESC
        """,
            (obj["id"],),
        )
        by_section = cur.fetchall()
        conn.close()

        print("\n📂 Всего PDF по разделам:")
        for sec, cnt in by_section:
            print(f"   {sec:>5}: {cnt}")


if __name__ == "__main__":
    main()
