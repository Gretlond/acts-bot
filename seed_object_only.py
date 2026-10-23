# seed_object_only.py
"""Создаёт объект и заполняет справочник типов работ."""
from db import (
    init_db, add_object, get_all_objects,
    add_work_type, get_all_work_types,
)

init_db()


# ---------- Объект ----------
if get_all_objects():
    print("Объект уже есть — пропускаю.")
else:
    add_object({
        "name": "Пример: жилой дом по ул. Центральной",
        "customer": "ООО «Заказчик»",
        "gen_contractor": "ООО «Генподрядчик»",
        "gen_person_post": "мастера",
        "gen_person": "Иванова Ивана Ивановича",
        "gen_short": "Иванов И.И.",
        "tech_post": "инженера",
        "tech_place": "ООО «Технадзор»",
        "tech_name": "Петрова Петра Петровича",
        "tech_short": "Петров П.П.",
        "author_post": "ГИП",
        "author_place": "ООО «Проектировщик»",
        "author_name": "Сидорова Сидора Сидоровича",
        "author_short": "Сидоров С.С.",
        "project_firm": "ООО «Проектировщик»",
        "project_date": "01.2026",
    })
    print("✅ Объект добавлен.")


# ---------- Типы работ ----------
DEFAULT_WORK_TYPES = [
    "Земляные работы",
    "Армирование",
    "Бетонирование",
    "Установка опалубки",
    "Установка анкеров",
    "Гидроизоляция",
    "Монтаж",
    "Обратная засыпка",
    "Устройство песчаного основания",
    "Устройство щебёночной подсыпки",
]

existing = {wt["name"] for wt in get_all_work_types()}
added = 0
for name in DEFAULT_WORK_TYPES:
    if name not in existing:
        _, created = add_work_type(name)
        if created:
            print(f"   ➕ Тип работ: «{name}»")
            added += 1

if added == 0:
    print("Типы работ уже заполнены.")
else:
    print(f"✅ Добавлено типов работ: {added}")