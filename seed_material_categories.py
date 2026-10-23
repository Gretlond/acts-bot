# seed_material_categories.py
# Заполняет базовые категории материалов.
# Запуск: python seed_material_categories.py

from db import init_db, get_all_material_categories, add_material_category

DEFAULT_CATEGORIES = [
    ("Арматура", 10),
    ("Бетон", 20),
    ("Раствор", 30),
    ("Опалубка", 40),
    ("Метизы и крепёж", 50),
    ("Грунт", 60),
    ("Песок", 70),
    ("Щебень", 80),
    ("Гидроизоляция", 90),
    ("Прочее", 999),
]


def main():
    init_db()
    existing = {c["name"] for c in get_all_material_categories()}
    added = 0
    for name, order in DEFAULT_CATEGORIES:
        if name in existing:
            print(f"ℹ️  «{name}» уже есть")
            continue
        add_material_category(name, sort_order=order)
        print(f"➕ {name}")
        added += 1
    print(f"\n✅ Добавлено категорий: {added}")
    print("\n📁 Категории в БД:")
    for c in get_all_material_categories():
        print(f"  [{c['id']}] {c['name']} (order={c['sort_order']})")


if __name__ == "__main__":
    main()