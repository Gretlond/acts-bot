# diag_senazh.py
from db import get_conn, get_positions_for_object, get_all_objects

obj = get_all_objects()[0]
print("=== Позиции со словом 'сенаж' ===")
for p in get_positions_for_object(obj["id"]):
    name = (p.get("name") or "").lower()
    if "сенаж" in name:
        print(f"  id={p['id']:>4} num={p['position_number']:>4} name={p['name']}")

print("\n=== Чертежи КЖ по позициям 20..35 ===")
conn = get_conn()
rows = conn.execute(
    "SELECT position_number, cipher, file_path FROM drawings "
    "WHERE CAST(position_number AS INTEGER) BETWEEN 20 AND 35 "
    "AND section='КЖ' "
    "ORDER BY CAST(position_number AS INTEGER)"
).fetchall()
for r in rows:
    print(f"  поз.{r['position_number']:>3} | {r['cipher']:<25} | {r['file_path']}")
conn.close()