# materials_view.py
"""
Общий показ материалов по категориям для актов NewAct / CycleRun / EditAct.
Используется в handlers.py / handlers_cycles.py / handlers_my_acts.py.
"""

from db import (
    get_materials_for_object,
    get_all_material_categories,
    get_material_category,
)
from keyboards import (
    material_categories_select_kb,
    materials_in_category_kb,
)
from states import NewAct, CycleRun, EditAct
from utils import split_materials_by_work_type

# =====================================================================
#  КОНТЕКСТ
# =====================================================================


def selected_key(ctx):
    if ctx == "newact":
        return "selected_materials"
    if ctx == "cycle":
        return "cycle_selected_materials"
    if ctx == "edit":
        return "edit_selected_materials"
    return "selected_materials"


def work_type_key(ctx):
    if ctx == "edit":
        return "edit_work_type_name"
    return "work_type_name"


def state_for(ctx):
    if ctx == "newact":
        return NewAct.choosing_materials
    if ctx == "cycle":
        return CycleRun.item_materials
    if ctx == "edit":
        return EditAct.choosing_materials
    return NewAct.choosing_materials


def get_selected(state_data, ctx):
    return list(state_data.get(selected_key(ctx), []) or [])


def get_work_type(state_data, ctx):
    return state_data.get(work_type_key(ctx)) or ""


# =====================================================================
#  ВЫБОР КАТЕГОРИИ (первый экран)
# =====================================================================


async def show_material_categories(message, state, ctx):
    data = await state.get_data()
    object_id = data.get("object_id")
    selected_ids = get_selected(data, ctx)

    materials_all = get_materials_for_object(object_id)
    cats = get_all_material_categories()
    work_type_name = get_work_type(data, ctx)
    matched_all = split_materials_by_work_type(materials_all, work_type_name)

    # сколько выбрано в каждой категории
    selected_per_cat = {}
    for m in materials_all:
        if m["id"] in selected_ids:
            cid = m.get("category_id")
            selected_per_cat[cid] = selected_per_cat.get(cid, 0) + 1

    cats_with_selected = []
    for c in cats:
        cnt = sum(1 for m in materials_all if m.get("category_id") == c["id"])
        star = sum(
            1 for m in materials_all if m.get("category_id") == c["id"] and m["id"] in matched_all
        )
        cats_with_selected.append(
            {
                "id": c["id"],
                "name": c["name"],
                "count": cnt,
                "selected": selected_per_cat.get(c["id"], 0),
                "matched": star,
            }
        )

    # материалы без категории
    none_cnt = sum(1 for m in materials_all if not m.get("category_id"))
    if none_cnt:
        cats_with_selected.append(
            {
                "id": -1,
                "name": "Без категории",
                "count": none_cnt,
                "selected": selected_per_cat.get(None, 0),
                "matched": 0,
            }
        )

    total_count = len(materials_all)
    any_selected = bool(selected_ids)

    # сохраняем текущую категорию как None (чтобы возврат шёл на категории)
    await state.update_data(_mat_current_cat=None)
    await state.set_state(state_for(ctx))

    text = (
        f"📦 Материалы\n"
        f"Всего: {total_count}, выбрано: {len(selected_ids)}\n\n"
        f"Выбери категорию:"
    )
    await message.answer(
        text,
        reply_markup=material_categories_select_kb(
            cats_with_selected,
            total_count=total_count,
            any_selected=any_selected,
        ),
    )


# =====================================================================
#  ВЫБОР МАТЕРИАЛОВ ВНУТРИ КАТЕГОРИИ (второй экран)
# =====================================================================


async def show_materials_in_category(message, state, ctx, cat_id):
    """
    cat_id = 0  → все материалы
    cat_id = -1 → без категории
    cat_id > 0  → конкретная категория
    """
    data = await state.get_data()
    object_id = data.get("object_id")
    selected_ids = get_selected(data, ctx)
    work_type_name = get_work_type(data, ctx)

    if cat_id == 0:
        materials = get_materials_for_object(object_id, work_type=work_type_name)
        title = "📂 Все материалы"
    elif cat_id in (None, -1):
        materials = get_materials_for_object(object_id, work_type=work_type_name)
        materials = [m for m in materials if not m.get("category_id")]
        title = "📁 Без категории"
    else:
        materials = get_materials_for_object(
            object_id, work_type=work_type_name, category_id=cat_id
        )
        cat = get_material_category(cat_id)
        title = f"📁 {cat['name'] if cat else '?'}"

    matched = split_materials_by_work_type(materials, work_type_name)

    await state.update_data(_mat_current_cat=cat_id)
    await state.set_state(state_for(ctx))

    if not materials:
        text = f"{title}\n\nМатериалов нет."
        await message.answer(
            text,
            reply_markup=materials_in_category_kb([], selected_ids, set()),
        )
        return

    text = (
        f"{title}\n"
        f"Материалов: {len(materials)}, "
        f"выбрано в этой категории: "
        f"{sum(1 for m in materials if m['id'] in selected_ids)} "
        f"(всего выбрано: {len(selected_ids)})"
    )
    await message.answer(
        text,
        reply_markup=materials_in_category_kb(materials, selected_ids, matched),
    )
