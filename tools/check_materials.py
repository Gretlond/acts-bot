# tools/check_materials.py
"""Показывает материалы, категории и сертификаты в БД."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from db import get_conn, get_all_objects


def main():
    conn = get_conn()
    cur = conn.cursor()

    print("📁 Категории:")
    cats = cur.execute(
        "SELECT id, name, sort_order FROM material_categories " "ORDER BY sort_order, name"
    ).fetchall()
    if not cats:
        print("   (нет)")
    else:
        for c in cats:
            cnt = cur.execute(
                "SELECT COUNT(*) FROM materials WHERE category_id = ?", (c["id"],)
            ).fetchone()[0]
            print(f"   [{c['id']:>3}] {c['name']:<25} ({cnt} мат.)")

    print("\n📦 Материалы:")
    rows = cur.execute("""
        SELECT m.id, m.object_id, m.name, m.quality_doc, m.work_types,
               c.name AS cat_name
        FROM materials m
        LEFT JOIN material_categories c ON c.id = m.category_id
        ORDER BY COALESCE(c.sort_order, 9999), c.name, m.name
    """).fetchall()
    if not rows:
        print("   (нет)")
    else:
        for r in rows:
            cat = r["cat_name"] or "без категории"
            wt = r["work_types"] or "—"
            print(f"   [{r['id']:>3}] {cat:<20} {r['name']}")
            print(f"        объект={r['object_id']}  " f"норматив={r['quality_doc'] or '—'}")
            print(f"        работы={wt}")

    print("\n📜 Сертификаты / паспорта:")
    certs = cur.execute("""
        SELECT ce.id, ce.material_id, m.name AS mat_name,
               ce.number, ce.date_from, ce.doc_type
        FROM certificates ce
        LEFT JOIN materials m ON m.id = ce.material_id
        ORDER BY ce.material_id, ce.created_at
    """).fetchall()
    if not certs:
        print("   (нет)")
    else:
        for c in certs:
            print(f"   [{c['id']:>3}] {c['mat_name'] or '?'}")
            print(
                f"        №{c['number']}  "
                f"от {c['date_from'] or '—'}  "
                f"тип={c['doc_type'] or '—'}"
            )

    print("\n🏗 Всего объектов:", len(get_all_objects()))
    conn.close()


if __name__ == "__main__":
    main()
