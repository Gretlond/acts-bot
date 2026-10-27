# handlers_cycles.py
"""
Всё, что связано с циклами работ: конструктор, просмотр, запуск.
"""

import os
import traceback

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile

from config import ACTS_DIR
from db import (
    get_all_objects,
    get_object,
    get_positions_for_object,
    get_position,
    get_all_work_types,
    get_materials_for_object,
    get_sections_for_position,
    get_next_act_number,
    get_cycles_for_user,
    get_cycle,
    get_cycle_items,
    get_cycle_item,
    add_cycle,
    update_cycle,
    add_cycle_item,
    update_cycle_item,
    delete_cycle,
    delete_cycle_item,
    move_cycle_item,
    copy_cycle_for_user,
    render_cycle_name,
    find_materials_by_hint,
    is_author_supervision,
    find_duplicate_act,
    DuplicateActNumberError,
)
from docs import get_pdf_path, check_size, make_input_file
from act_service import (
    create_act_with_file,
    validate_act_payload,
    validation_text,
)
from states import CycleRun
from keyboards import (
    main_menu_kb,
    objects_kb,
    work_types_kb,
    position_group_action_kb,
    positions_in_group_kb,
    positions_grouped_kb,
    back_kb,
    cancel_kb,
    cycles_kb,
    cycle_view_kb,
    cycle_edit_menu_kb,
    cycle_manage_items_kb,
    cycle_item_manage_kb,
    step_template_kb,
    cycle_confirm_delete_kb,
    cycle_section_kb,
    cycle_dates_kb,
    cycle_pdf_choice_kb,
    cycle_sheets_kb,
    cycle_sheets_apply_kb,
    cycle_item_preview_kb,
)
from utils import (
    parse_dates_range,
    date_range_is_valid,
    format_materials_with_certs,
    build_template_data,
    resolve_section_hint,
    materials_to_json,
    act_filename,
    compose_full_work,
    _range_str_from_numbers,
    _first_position_number,
    _show_positions_menu,
)
from materials_view import show_material_categories

router = Router()


# =====================================================================
#  КОНСТРУКТОР ЦИКЛОВ — просмотр и редактирование
# =====================================================================


@router.callback_query(CycleRun.choosing_cycle, F.data.startswith("cyc:"))
async def cb_choose_cycle(call: CallbackQuery, state: FSMContext):
    cycle_id = int(call.data.split(":")[1])
    await _show_cycle_view(call, state, cycle_id)


async def _show_cycle_view(call: CallbackQuery, state: FSMContext, cycle_id: int):
    cycle = get_cycle(cycle_id)
    if not cycle:
        await call.answer("Цикл не найден", show_alert=True)
        return
    tg_id = call.from_user.id
    is_owner = cycle.get("owner_tg_id") == tg_id
    is_default = bool(cycle.get("is_default"))
    items = get_cycle_items(cycle_id)
    lines = [f"📋 {cycle['name']}"]
    if cycle["description"]:
        lines.append(f"{cycle['description']}\n")
    lines.append(f"Состав ({len(items)}):")
    for it in items:
        tmpl = it.get("name_template") or "{common}"
        lines.append(f"  {it['order_num']}. {it['work_type']} [{tmpl}]")
    await state.update_data(cycle_id=cycle_id)
    await state.set_state(CycleRun.viewing_cycle)
    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=cycle_view_kb(cycle_id, len(items), is_owner, is_default),
    )
    await call.answer()


@router.callback_query(F.data == "cyc_back_list")
async def cb_cyc_back_list(call: CallbackQuery, state: FSMContext):
    tg_id = call.from_user.id
    cycles = get_cycles_for_user(tg_id)
    await state.set_state(CycleRun.choosing_cycle)
    await call.message.edit_text(
        "📋 Выберите цикл работ:",
        reply_markup=cycles_kb(cycles, tg_id),
    )
    await call.answer()


@router.callback_query(CycleRun.choosing_cycle, F.data == "cyce:new")
async def cb_cycle_new(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(CycleRun.entering_cycle_name)
    await call.message.answer("📝 Введите название нового цикла:", reply_markup=cancel_kb())


@router.message(CycleRun.entering_cycle_name)
async def msg_cycle_new_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 200:
        await message.answer("⚠️ 1-200 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(new_cycle_name=name)
    await state.set_state(CycleRun.entering_cycle_description)
    await message.answer("📋 Описание цикла (или «—» чтобы пропустить):", reply_markup=cancel_kb())


@router.message(CycleRun.entering_cycle_description)
async def msg_cycle_new_desc(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    desc = "" if text in ("—", "-", "") else text[:300]
    data = await state.get_data()
    tg_id = message.from_user.id
    cycle_id = add_cycle(data["new_cycle_name"], desc, is_default=0, owner_tg_id=tg_id)
    await state.update_data(edit_cycle_id=cycle_id)
    await message.answer(
        f"✅ Цикл «{data['new_cycle_name']}» создан.\n\n" f"Теперь добавьте работы:"
    )
    await _show_cycle_edit_menu(message, state, cycle_id)


@router.callback_query(CycleRun.viewing_cycle, F.data.startswith("cyce:menu:"))
async def cb_cycle_edit_menu(call: CallbackQuery, state: FSMContext):
    cycle_id = int(call.data.split(":")[2])
    cycle = get_cycle(cycle_id)
    if not cycle:
        await call.answer("Не найдено", show_alert=True)
        return
    tg_id = call.from_user.id
    is_owner = cycle.get("owner_tg_id") == tg_id
    if not is_owner and cycle.get("is_default"):
        await call.answer(
            "Дефолтный цикл редактировать нельзя. " "Скопируйте его себе.", show_alert=True
        )
        return
    await call.answer()
    await _show_cycle_edit_menu(call.message, state, cycle_id)


async def _show_cycle_edit_menu(message, state: FSMContext, cycle_id: int):
    cycle = get_cycle(cycle_id)
    if not cycle:
        await message.answer("Цикл не найден")
        return
    items = get_cycle_items(cycle_id)
    text = f"✏️ Редактирование цикла\n\n📋 {cycle['name']}\n"
    if cycle.get("description"):
        text += f"📋 {cycle['description']}\n"
    text += f"\nСостав ({len(items)}):"
    if not items:
        text += "\n  (пусто — добавьте работы)"
    else:
        for it in items:
            text += f"\n  {it['order_num']}. {it['work_type']}"
    await state.update_data(edit_cycle_id=cycle_id)
    await state.set_state(CycleRun.viewing_cycle_edit_menu)
    await message.answer(text, reply_markup=cycle_edit_menu_kb(cycle_id, True))


@router.callback_query(F.data == "cyce:back_menu")
async def cb_ce_back_menu(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cycle_id = data.get("edit_cycle_id")
    if not cycle_id:
        await call.answer("Ошибка", show_alert=True)
        return
    await call.answer()
    await _show_cycle_edit_menu(call.message, state, cycle_id)


@router.callback_query(F.data == "cyce:back_manage")
async def cb_ce_back_manage(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cycle_id = data.get("edit_cycle_id")
    if not cycle_id:
        await call.answer("Ошибка", show_alert=True)
        return
    items = get_cycle_items(cycle_id)
    if not items:
        await call.answer("Работ нет")
        await _show_cycle_edit_menu(call.message, state, cycle_id)
        return
    await state.set_state(CycleRun.choosing_item_to_manage)
    await call.message.edit_text(
        "🔀 Управление работами. Выберите:", reply_markup=cycle_manage_items_kb(items)
    )
    await call.answer()


@router.callback_query(F.data.startswith("cyce:add_item:"))
async def cb_cycle_add_item(call: CallbackQuery, state: FSMContext):
    cycle_id = int(call.data.split(":")[2])
    await call.answer()
    await state.update_data(edit_cycle_id=cycle_id, _edit_step_mode=False)
    work_types = get_all_work_types()
    if not work_types:
        await call.message.answer("⚠️ Нет типов работ в справочнике.")
        return
    await state.set_state(CycleRun.adding_step_work_type)
    await call.message.answer(
        "🔨 Выберите тип работы для нового шага:",
        reply_markup=work_types_kb(
            work_types,
            add_new=False,
            back_cb="cyce:back_manage",
            del_cb=None,
        ),
    )


@router.callback_query(CycleRun.adding_step_work_type, F.data.startswith("wt:"))
async def cb_cycle_add_item_wt(call: CallbackQuery, state: FSMContext):
    wt_id = int(call.data.split(":")[1])
    work_types = get_all_work_types()
    wt = next((w for w in work_types if w["id"] == wt_id), None)
    if not wt:
        await call.answer("Не найден", show_alert=True)
        return
    data = await state.get_data()
    if data.get("_edit_step_mode"):
        item_id = data.get("manage_item_id")
        update_cycle_item(item_id, work_type=wt["name"])
        await state.update_data(_edit_step_mode=False)
        await state.set_state(CycleRun.choosing_item_to_manage)
        await call.answer("✅ Тип обновлён")
        await _refresh_manage_item(call, state, item_id)
        return
    await state.update_data(new_step_work_type=wt["name"])
    await call.answer()
    await state.set_state(CycleRun.adding_step_template)
    await call.message.edit_text(
        f"🔨 Тип: «{wt['name']}»\n\n📝 Шаблон наименования:",
        reply_markup=step_template_kb(),
    )


@router.callback_query(CycleRun.adding_step_template, F.data.startswith("tmpl:"))
async def cb_cycle_add_item_tmpl(call: CallbackQuery, state: FSMContext):
    tmpl_value = call.data.split(":", 1)[1]
    if tmpl_value == "custom":
        await call.answer()
        await state.set_state(CycleRun.adding_step_custom_template)
        await call.message.answer(
            "📝 Введите шаблон. Используйте {common} как заглушку.\n"
            "Например: «под устройство {common}»",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(new_step_template=tmpl_value)
    await call.answer("Шаблон выбран")
    await _save_new_step(call.message, state)


@router.message(CycleRun.adding_step_custom_template)
async def msg_cycle_custom_template(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or "{common}" not in text:
        await message.answer("⚠️ Нужен текст со словом {common}.", reply_markup=cancel_kb())
        return
    await state.update_data(new_step_template=text)
    await _save_new_step(message, state)


async def _save_new_step(message, state: FSMContext):
    data = await state.get_data()
    cycle_id = data["edit_cycle_id"]
    wt = data["new_step_work_type"]
    tmpl = data.get("new_step_template", "{common}")
    items = get_cycle_items(cycle_id)
    order = len(items) + 1
    add_cycle_item(cycle_id, order, wt, tmpl)
    await message.answer(f"✅ Шаг добавлен: «{wt}» [{tmpl}]")
    await _show_cycle_edit_menu(message, state, cycle_id)


@router.callback_query(F.data.startswith("cyce:manage:"))
async def cb_cycle_manage(call: CallbackQuery, state: FSMContext):
    cycle_id = int(call.data.split(":")[2])
    await call.answer()
    items = get_cycle_items(cycle_id)
    if not items:
        await call.answer("В цикле нет работ", show_alert=True)
        return
    await state.update_data(edit_cycle_id=cycle_id)
    await state.set_state(CycleRun.choosing_item_to_manage)
    await call.message.edit_text(
        "🔀 Управление работами. Выберите:", reply_markup=cycle_manage_items_kb(items)
    )


@router.callback_query(CycleRun.choosing_item_to_manage, F.data.startswith("cyci:edit:"))
async def cb_cycle_manage_item(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split(":")[2])
    item = get_cycle_item(item_id)
    if not item:
        await call.answer("Не найдено", show_alert=True)
        return
    items = get_cycle_items(item["cycle_id"])
    total = len(items)
    await state.update_data(manage_item_id=item_id)
    text = (
        f"🔨 {item['work_type']}\n"
        f"📝 Шаблон: {item['name_template'] or '{common}'}\n"
        f"№{item['order_num']} из {total}"
    )
    await call.message.edit_text(
        text,
        reply_markup=cycle_item_manage_kb(item_id, total, item["order_num"]),
    )
    await call.answer()


async def _refresh_manage_item(call: CallbackQuery, state: FSMContext, item_id: int):
    item = get_cycle_item(item_id)
    if not item:
        await call.message.edit_text("Шаг не найден")
        return
    items = get_cycle_items(item["cycle_id"])
    total = len(items)
    text = (
        f"🔨 {item['work_type']}\n"
        f"📝 Шаблон: {item['name_template'] or '{common}'}\n"
        f"№{item['order_num']} из {total}"
    )
    try:
        await call.message.edit_text(
            text,
            reply_markup=cycle_item_manage_kb(item_id, total, item["order_num"]),
        )
    except Exception:
        await call.message.answer(
            text,
            reply_markup=cycle_item_manage_kb(item_id, total, item["order_num"]),
        )


@router.callback_query(F.data.startswith("cyci:up:"))
async def cb_item_up(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split(":")[2])
    ok = move_cycle_item(item_id, "up")
    await call.answer("⬆️" if ok else "Уже сверху", show_alert=not ok)
    if ok:
        await _refresh_manage_item(call, state, item_id)


@router.callback_query(F.data.startswith("cyci:down:"))
async def cb_item_down(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split(":")[2])
    ok = move_cycle_item(item_id, "down")
    await call.answer("⬇️" if ok else "Уже снизу", show_alert=not ok)
    if ok:
        await _refresh_manage_item(call, state, item_id)


@router.callback_query(F.data.startswith("cyci:del:"))
async def cb_item_del(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split(":")[2])
    item = get_cycle_item(item_id)
    if not item:
        await call.answer("Не найдено", show_alert=True)
        return
    cycle_id = item["cycle_id"]
    items = get_cycle_items(cycle_id)
    if len(items) == 1:
        await call.answer("Нельзя удалить последнюю работу.", show_alert=True)
        return
    delete_cycle_item(item_id)
    await call.answer(f"🗑 {item['work_type']}")
    items = get_cycle_items(cycle_id)
    await state.update_data(edit_cycle_id=cycle_id)
    await state.set_state(CycleRun.choosing_item_to_manage)
    await call.message.edit_text(
        "🔀 Управление работами. Выберите:", reply_markup=cycle_manage_items_kb(items)
    )


@router.callback_query(F.data.startswith("cyci:tmpl:"))
async def cb_item_tmpl(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split(":")[2])
    await state.update_data(manage_item_id=item_id)
    await state.set_state(CycleRun.editing_item_template)
    await call.answer()
    await call.message.answer("📝 Выберите новый шаблон:", reply_markup=step_template_kb())


@router.callback_query(CycleRun.editing_item_template, F.data.startswith("tmpl:"))
async def cb_item_tmpl_set(call: CallbackQuery, state: FSMContext):
    tmpl_value = call.data.split(":", 1)[1]
    if tmpl_value == "custom":
        await call.answer()
        await state.set_state(CycleRun.editing_item_custom_template)
        await call.message.answer("📝 Введите шаблон со словом {common}:", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    item_id = data["manage_item_id"]
    update_cycle_item(item_id, name_template=tmpl_value)
    await state.set_state(CycleRun.choosing_item_to_manage)
    await call.answer("✅ Шаблон обновлён")
    await _refresh_manage_item(call, state, item_id)


@router.message(CycleRun.editing_item_custom_template)
async def msg_edit_custom_template(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or "{common}" not in text:
        await message.answer("⚠️ Нужен текст со словом {common}.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    item_id = data["manage_item_id"]
    update_cycle_item(item_id, name_template=text)
    await message.answer(f"✅ Шаблон обновлён: «{text}»")
    item = get_cycle_item(item_id)
    if item:
        items = get_cycle_items(item["cycle_id"])
        total = len(items)
        await state.set_state(CycleRun.choosing_item_to_manage)
        await message.answer(
            f"🔨 {item['work_type']}\n📝 {text}\n№{item['order_num']} из {total}",
            reply_markup=cycle_item_manage_kb(item_id, total, item["order_num"]),
        )


@router.callback_query(F.data.startswith("cyci:wt:"))
async def cb_item_wt(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split(":")[2])
    item = get_cycle_item(item_id)
    if not item:
        await call.answer("Не найдено", show_alert=True)
        return
    await state.update_data(
        manage_item_id=item_id,
        edit_cycle_id=item["cycle_id"],
        _edit_step_mode=True,
    )
    await state.set_state(CycleRun.adding_step_work_type)
    work_types = get_all_work_types()
    await call.answer()
    await call.message.answer(
        "🔨 Выберите новый тип работы:",
        reply_markup=work_types_kb(
            work_types,
            add_new=False,
            back_cb="cyce:back_manage",
            del_cb=None,
        ),
    )


@router.callback_query(F.data.startswith("cyce:rename:"))
async def cb_cycle_rename(call: CallbackQuery, state: FSMContext):
    cycle_id = int(call.data.split(":")[2])
    cycle = get_cycle(cycle_id)
    if not cycle:
        await call.answer("Не найдено", show_alert=True)
        return
    await state.update_data(edit_cycle_id=cycle_id)
    await state.set_state(CycleRun.editing_cycle_name)
    await call.answer()
    await call.message.answer(
        f"📝 Текущее: «{cycle['name']}»\n\nВведите новое:",
        reply_markup=cancel_kb(),
    )


@router.message(CycleRun.editing_cycle_name)
async def msg_cycle_rename(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 200:
        await message.answer("⚠️ 1-200 символов.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    cycle_id = data["edit_cycle_id"]
    if not update_cycle(cycle_id, name=text):
        await message.answer("⚠️ Имя занято. Введите другое.", reply_markup=cancel_kb())
        return
    await message.answer("✅ Переименовано.")
    await _show_cycle_edit_menu(message, state, cycle_id)


@router.callback_query(F.data.startswith("cyce:desc:"))
async def cb_cycle_desc(call: CallbackQuery, state: FSMContext):
    cycle_id = int(call.data.split(":")[2])
    cycle = get_cycle(cycle_id)
    if not cycle:
        await call.answer("Не найдено", show_alert=True)
        return
    await state.update_data(edit_cycle_id=cycle_id)
    await state.set_state(CycleRun.editing_cycle_description)
    await call.answer()
    await call.message.answer(
        f"📋 Текущее: {cycle.get('description') or '—'}\n\n"
        f"Введите новое (или «—» чтобы очистить):",
        reply_markup=cancel_kb(),
    )


@router.message(CycleRun.editing_cycle_description)
async def msg_cycle_desc(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    desc = "" if text in ("—", "-", "") else text[:300]
    data = await state.get_data()
    cycle_id = data["edit_cycle_id"]
    update_cycle(cycle_id, description=desc)
    await message.answer("✅ Описание обновлено.")
    await _show_cycle_edit_menu(message, state, cycle_id)


@router.callback_query(F.data.startswith("cyc_copy:"))
async def cb_cycle_copy(call: CallbackQuery, state: FSMContext):
    cycle_id = int(call.data.split(":")[1])
    tg_id = call.from_user.id
    new_id = copy_cycle_for_user(cycle_id, tg_id)
    if not new_id:
        await call.answer("Не удалось скопировать", show_alert=True)
        return
    await call.answer("✅ Скопировано")
    new_cycle = get_cycle(new_id)
    await call.message.answer(f"✅ Создана ваша версия: «{new_cycle['name']}».")
    await _show_cycle_edit_menu(call.message, state, new_id)


@router.callback_query(F.data.startswith("cyce:del_confirm:"))
async def cb_cycle_del_confirm(call: CallbackQuery, state: FSMContext):
    cycle_id = int(call.data.split(":")[2])
    tg_id = call.from_user.id
    cycle = get_cycle(cycle_id)
    if not cycle or cycle.get("owner_tg_id") != tg_id:
        await call.answer("Это не ваш цикл", show_alert=True)
        return
    delete_cycle(cycle_id, owner_tg_id=tg_id)
    await call.answer("🗑 Удалено")
    cycles = get_cycles_for_user(tg_id)
    await state.set_state(CycleRun.choosing_cycle)
    await call.message.edit_text(
        f"🗑 Цикл «{cycle['name']}» удалён.\n\n📋 Выберите цикл:",
        reply_markup=cycles_kb(cycles, tg_id),
    )


@router.callback_query(F.data.startswith("cyce:del:"))
async def cb_cycle_del(call: CallbackQuery, state: FSMContext):
    cycle_id = int(call.data.split(":")[2])
    cycle = get_cycle(cycle_id)
    if not cycle:
        await call.answer("Не найдено", show_alert=True)
        return
    tg_id = call.from_user.id
    if cycle.get("owner_tg_id") != tg_id:
        await call.answer("Это не ваш цикл", show_alert=True)
        return
    await call.answer()
    await call.message.edit_text(
        f"⚠️ Удалить цикл «{cycle['name']}»? Это действие нельзя отменить.",
        reply_markup=cycle_confirm_delete_kb(cycle_id),
    )


# =====================================================================
#  ЗАПУСК ЦИКЛА
# =====================================================================


@router.callback_query(CycleRun.viewing_cycle, F.data.startswith("cyc_run:"))
async def cb_run_cycle(call: CallbackQuery, state: FSMContext):
    cycle_id = int(call.data.split(":")[1])
    cycle = get_cycle(cycle_id)
    items = get_cycle_items(cycle_id)
    if not cycle or not items:
        await call.answer("Пусто", show_alert=True)
        return
    objects = get_all_objects()
    if not objects:
        await call.answer("Нет объектов", show_alert=True)
        return
    await state.update_data(
        cycle_id=cycle_id,
        cycle_name=cycle["name"],
        items=items,
        idx=0,
        previous_sheets=None,
        sheets_for_all=None,
        apply_sheets_decided=False,
        results=[],
        certs_result={},
    )
    await state.set_state(CycleRun.choosing_object)
    await call.message.edit_text(
        f"📋 Цикл: {cycle['name']} ({len(items)} работ)\n\n🏗 Объект:",
        reply_markup=objects_kb(objects),
    )
    await call.answer()


@router.callback_query(CycleRun.choosing_object, F.data.startswith("obj:"))
async def cb_cycle_choose_object(call: CallbackQuery, state: FSMContext):
    obj_id = int(call.data.split(":")[1])
    obj = get_object(obj_id)
    if not obj:
        await call.answer("Не найден", show_alert=True)
        return
    positions = get_positions_for_object(obj_id)
    if not positions:
        await call.answer("Нет позиций", show_alert=True)
        return
    await state.update_data(object_id=obj_id)
    await state.set_state(CycleRun.choosing_position)
    await _show_positions_menu(call.message, state, prefix=f"🏗 {obj['name'][:60]}…\n\n📍 Позиция:")
    await call.answer()


@router.callback_query(CycleRun.choosing_position, F.data.startswith("pos_grp:"))
async def cb_cycle_position_group(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    groups = data.get("position_groups", [])
    if idx >= len(groups):
        await call.answer("Не найдено", show_alert=True)
        return
    g = groups[idx]
    if len(g["positions"]) == 1:
        await _apply_cycle_position(call, state, g["positions"][0])
        return
    await call.message.edit_text(
        f"📍 {g['name']} — выберите вариант:",
        reply_markup=position_group_action_kb(g, idx),
    )
    await call.answer()


@router.callback_query(CycleRun.choosing_position, F.data == "pos_grp_back")
async def cb_cycle_positions_back(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    groups = data.get("position_groups", [])
    await call.message.edit_text(
        "📍 Выберите позицию:",
        reply_markup=positions_grouped_kb(groups),
    )
    await call.answer()


@router.callback_query(CycleRun.choosing_position, F.data.startswith("pos_back_group:"))
async def cb_cycle_position_back_to_group(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    groups = data.get("position_groups", [])
    if idx >= len(groups):
        await call.answer()
        return
    g = groups[idx]
    await call.message.edit_text(
        f"📍 {g['name']} — выберите вариант:",
        reply_markup=position_group_action_kb(g, idx),
    )
    await call.answer()


@router.callback_query(CycleRun.choosing_position, F.data.startswith("pos_single:"))
async def cb_cycle_position_single(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    groups = data.get("position_groups", [])
    if idx >= len(groups):
        await call.answer()
        return
    g = groups[idx]
    await call.message.edit_text(
        f"📍 {g['name']} — выберите позицию:",
        reply_markup=positions_in_group_kb(g["positions"], idx),
    )
    await call.answer()


@router.callback_query(CycleRun.choosing_position, F.data.startswith("pos_all:"))
async def cb_cycle_position_all(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    groups = data.get("position_groups", [])
    if idx >= len(groups):
        await call.answer()
        return
    g = groups[idx]
    numbers = [n for n in g["numbers"] if n]
    range_str = _range_str_from_numbers(numbers)
    first_pos = _first_position_number(numbers)
    if not range_str or not first_pos:
        await call.answer("Не удалось определить диапазон", show_alert=True)
        return
    await state.update_data(
        position_id=None,
        position_number=range_str,
        search_position_number=first_pos,
        position_name=g["name"],
    )
    items = data.get("items", [])
    example_line = ""
    if items:
        example_name = render_cycle_name(items[0].get("name_template"), "{общая часть}")
        example_line = (
            f"\n\nПример для 1-й работы:\n"
            f"«{items[0]['work_type']} {example_name} "
            f"позиция №{range_str}»"
        )
    await state.set_state(CycleRun.entering_common_part)
    await call.message.edit_text(
        f"📍 {g['name']} (№{range_str})\n\n"
        f"📝 Введите общую часть для всех работ цикла.\n\n"
        f"Например: «фундаментов Фм1, Фм2 низ на отм. -1.800 "
        f"в осях 1-2/А-Д»{example_line}",
        reply_markup=back_kb(),
    )
    await call.answer()


@router.callback_query(CycleRun.choosing_position, F.data.startswith("pos_id:"))
async def cb_cycle_choose_position(call: CallbackQuery, state: FSMContext):
    position_id = int(call.data.split(":", 1)[1])
    pos = get_position(position_id)
    if not pos:
        await call.answer("Не найдена", show_alert=True)
        return
    await _apply_cycle_position(call, state, pos)


async def _apply_cycle_position(call: CallbackQuery, state: FSMContext, pos):
    data = await state.get_data()
    pos_num = (pos.get("position_number") or "").strip()
    await state.update_data(
        position_id=pos["id"],
        position_number=pos_num,
        search_position_number=pos_num,
        position_name=pos.get("name") or "",
    )
    items = data.get("items", [])
    example_line = ""
    if items:
        example_name = render_cycle_name(items[0].get("name_template"), "{общая часть}")
        if pos_num:
            example_line = (
                f"\n\nПример для 1-й работы:\n"
                f"«{items[0]['work_type']} {example_name} "
                f"позиция №{pos_num}»"
            )
        else:
            example_line = (
                f"\n\nПример для 1-й работы:\n" f"«{items[0]['work_type']} {example_name}»"
            )
    await state.set_state(CycleRun.entering_common_part)
    num_line = f"№{pos_num}" if pos_num else "без номера"
    await call.message.edit_text(
        f"📍 {pos.get('name') or ''} ({num_line})\n\n"
        f"📝 Введите общую часть для всех работ цикла.\n\n"
        f"Например: «фундаментов Фм1, Фм2 низ на отм. -1.800 "
        f"в осях 1-2/А-Д»{example_line}",
        reply_markup=back_kb(),
    )
    await call.answer()


@router.message(CycleRun.entering_common_part)
async def msg_cycle_common(message: Message, state: FSMContext):
    common = (message.text or "").strip()
    if not common or len(common) > 300:
        await message.answer("⚠️ 1-300 символов.", reply_markup=back_kb())
        return
    data = await state.get_data()
    object_id = data["object_id"]
    try:
        base_act_number = int(get_next_act_number(object_id))
    except (ValueError, TypeError):
        base_act_number = 1
    await state.update_data(
        common_part=common,
        idx=0,
        base_act_number=base_act_number,
        results=[],
        certs_result={},
        sheets_for_all=None,
        apply_sheets_decided=False,
    )
    items = data["items"]
    preview_lines = [
        f"✅ Общая часть: «{common}»",
        f"🔢 Первый акт — №{base_act_number}\n",
        "Итоговые наименования:",
    ]
    for i, it in enumerate(items, start=1):
        name = render_cycle_name(it.get("name_template"), common)
        preview_lines.append(f"  {i}. {it['work_type']} {name}")
    await message.answer("\n".join(preview_lines) + "\n\n▶️ Запускаю…")
    await _show_cycle_item(message, state)


async def _show_cycle_item(event, state: FSMContext):
    data = await state.get_data()
    items = data["items"]
    idx = data["idx"]
    if idx >= len(items):
        await _finish_cycle(event, state)
        return
    item = items[idx]
    common = data["common_part"]
    work_name = render_cycle_name(item.get("name_template"), common)
    pos_num = data.get("position_number") or ""
    if pos_num:
        full_line = f"→ «{item['work_type']} {work_name} " f"позиция №{pos_num}»"
    else:
        full_line = f"→ «{item['work_type']} {work_name}»"
    text = (
        f"📋 Работа {idx + 1}/{len(items)}\n\n"
        f"🔨 {item['work_type']}\n📝 {work_name}\n"
        f"{full_line}\n\n"
        f"📅 Даты работ:\n"
        f"• одна дата (ДД.ММ.ГГГГ) — начало = окончание\n"
        f"• или диапазон: ДД.ММ.ГГГГ - ДД.ММ.ГГГГ"
    )
    await state.set_state(CycleRun.item_dates)
    kb = cycle_dates_kb()
    if isinstance(event, CallbackQuery):
        await event.message.answer(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.message(CycleRun.item_dates)
async def msg_item_dates(message: Message, state: FSMContext):
    try:
        start_date, end_date = parse_dates_range(message.text or "")
    except ValueError as e:
        await message.answer(f"⚠️ {e}", reply_markup=cycle_dates_kb())
        return
    if not date_range_is_valid(start_date, end_date):
        await message.answer(
            "⚠️ Дата окончания не может быть раньше даты начала.",
            reply_markup=cycle_dates_kb(),
        )
        return
    data = await state.get_data()
    items = data["items"]
    idx = data["idx"]
    item = items[idx]
    await state.update_data(
        item_start_date=start_date,
        item_end_date=end_date,
        item_act_date=end_date,
    )
    object_id = data["object_id"]
    pos_num = data.get("position_number") or ""
    search_num = data.get("search_position_number") or pos_num
    available_sections = get_sections_for_position(object_id, search_num)
    if not available_sections:
        await state.update_data(item_section=None, item_cipher=None, item_pdf_path=None)
        await _ask_item_pdf_choice(message, state)
        return
    auto_section = resolve_section_hint(item, available_sections)
    if auto_section:
        full_path, record, err = get_pdf_path(object_id, search_num, auto_section)
        await state.update_data(
            item_section=auto_section,
            item_cipher=record["cipher"] if record else None,
            item_pdf_path=full_path,
        )
        await _ask_item_pdf_choice(message, state, section=auto_section)
        return
    await state.set_state(CycleRun.item_section)
    await message.answer(
        f"📅 {start_date['full']} — {end_date['full']}\n\n📂 Раздел:",
        reply_markup=cycle_section_kb(available_sections),
    )


@router.callback_query(CycleRun.item_section, F.data == "item_back_dates")
async def cb_item_back_dates_from_section(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _show_cycle_item(call, state)


@router.callback_query(CycleRun.item_section, F.data.startswith("csec:"))
async def cb_choose_item_section(call: CallbackQuery, state: FSMContext):
    section = call.data.split(":", 1)[1]
    data = await state.get_data()
    object_id = data["object_id"]
    pos_num = data.get("position_number") or ""
    search_num = data.get("search_position_number") or pos_num
    if section == "none":
        await state.update_data(item_section=None, item_cipher=None, item_pdf_path=None)
        await call.message.edit_text("⏭ Раздел пропущен.")
        await _ask_item_pdf_choice(call.message, state)
        await call.answer()
        return
    full_path, record, err = get_pdf_path(object_id, search_num, section)
    await state.update_data(
        item_section=section,
        item_cipher=record["cipher"] if record else None,
        item_pdf_path=full_path,
    )
    await call.message.edit_text(f"📂 Раздел: {section}")
    await _ask_item_pdf_choice(call.message, state, section=section)
    await call.answer()


async def _ask_item_pdf_choice(message, state: FSMContext, section=None):
    data = await state.get_data()
    pdf_path = data.get("item_pdf_path")
    if pdf_path and os.path.exists(pdf_path):
        await state.set_state(CycleRun.item_pdf_choice)
        await message.answer(
            f"📎 Прислать PDF чертежа ({section or '—'})?", reply_markup=cycle_pdf_choice_kb()
        )
    else:
        await _go_to_sheets_or_materials(message, state)


@router.callback_query(CycleRun.item_pdf_choice, F.data == "item_back_dates")
async def cb_item_back_dates_from_pdf(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _show_cycle_item(call, state)


@router.callback_query(CycleRun.item_pdf_choice, F.data == "cpdf:send")
async def cb_item_pdf_send(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    full_path = data.get("item_pdf_path")
    cipher = data.get("item_cipher") or "—"
    section = data.get("item_section") or "—"
    if not full_path or not os.path.exists(full_path):
        await call.message.answer("⚠️ PDF не найден.")
    else:
        ok, size_mb, err = check_size(full_path)
        if not ok:
            await call.message.answer(f"⚠️ {err}")
        else:
            try:
                file = make_input_file(full_path)
                await call.message.answer_document(file, caption=f"{section} · {cipher}")
                await call.message.answer(f"📎 PDF ({size_mb:.1f} МБ)")
            except Exception as e:
                await call.message.answer(f"⚠️ {e}")
    await _go_to_sheets_or_materials(call.message, state)


@router.callback_query(CycleRun.item_pdf_choice, F.data == "cpdf:skip")
async def cb_item_pdf_skip(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("⏭ PDF пропущен.")
    await _go_to_sheets_or_materials(call.message, state)


async def _go_to_sheets_or_materials(message, state: FSMContext):
    data = await state.get_data()
    sheets_for_all = data.get("sheets_for_all")
    if sheets_for_all:
        await state.update_data(item_sheets=sheets_for_all)
        await _ask_item_materials(message, state)
    else:
        await state.set_state(CycleRun.item_sheets)
        await _ask_item_sheets(message, state)


async def _ask_item_sheets(message, state: FSMContext):
    data = await state.get_data()
    prev_sheets = data.get("previous_sheets")
    text = "✏️ Введите номера листов (например: 3-4)."
    if prev_sheets:
        text += f"\n\nИли возьмите из прошлой работы ({prev_sheets})."
    await message.answer(text, reply_markup=cycle_sheets_kb(prev_sheets))


@router.message(CycleRun.item_sheets)
async def msg_item_sheets(message: Message, state: FSMContext):
    sheets = (message.text or "").strip()
    if not sheets or len(sheets) > 60:
        data = await state.get_data()
        await message.answer(
            "⚠️ 1-60 символов.", reply_markup=cycle_sheets_kb(data.get("previous_sheets"))
        )
        return
    await state.update_data(item_sheets=sheets)
    await _handle_sheets_received(message, state)


@router.callback_query(CycleRun.item_sheets, F.data == "use_prev_sheets")
async def cb_use_prev_sheets(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prev = data.get("previous_sheets")
    if not prev:
        await call.answer("Нет прошлых листов", show_alert=True)
        return
    await call.answer()
    await state.update_data(item_sheets=prev)
    await call.message.answer(f"📋 Листы: {prev}")
    await _handle_sheets_received(call.message, state)


@router.callback_query(CycleRun.item_sheets, F.data == "item_back_pdf")
async def cb_item_back_pdf(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    pdf_path = data.get("item_pdf_path")
    if pdf_path and os.path.exists(pdf_path):
        await state.set_state(CycleRun.item_pdf_choice)
        await call.message.answer("📎 Прислать PDF?", reply_markup=cycle_pdf_choice_kb())
    else:
        await _show_cycle_item(call, state)


async def _handle_sheets_received(message, state: FSMContext):
    data = await state.get_data()
    items = data["items"]
    idx = data["idx"]
    if idx == 0 and len(items) > 1 and not data.get("apply_sheets_decided"):
        await state.set_state(CycleRun.item_sheets_apply)
        await message.answer(
            f"📄 Листы: {data['item_sheets']}\n\n" f"Применить ко всем {len(items)} работам?",
            reply_markup=cycle_sheets_apply_kb(),
        )
        return
    await _ask_item_materials(message, state)


@router.callback_query(CycleRun.item_sheets_apply, F.data == "sheets_apply_all")
async def cb_sheets_apply_all(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    sheets = data["item_sheets"]
    await state.update_data(
        sheets_for_all=sheets,
        apply_sheets_decided=True,
        previous_sheets=sheets,
    )
    await call.message.edit_text(f"✅ Листы {sheets} для всех работ.")
    await _ask_item_materials(call.message, state)


@router.callback_query(CycleRun.item_sheets_apply, F.data == "sheets_per_item")
async def cb_sheets_per_item(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.update_data(sheets_for_all=None, apply_sheets_decided=True)
    await call.message.edit_text("📝 Листы спрашиваю по каждой.")
    await _ask_item_materials(call.message, state)


@router.callback_query(CycleRun.item_dates, F.data == "item_back_common")
async def cb_item_back_common(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(CycleRun.entering_common_part)
    await call.message.answer(
        "📝 Введите новую общую часть. Прогресс сбросится.", reply_markup=cancel_kb()
    )


async def _ask_item_materials(message, state: FSMContext):
    """Переход к выбору материалов по категориям."""
    data = await state.get_data()
    items = data["items"]
    idx = data["idx"]
    item = items[idx]
    work_type_name = item.get("work_type", "")

    # предзаполняем auto_selected по materials_hint
    auto_selected = find_materials_by_hint(data["object_id"], item.get("materials_hint"))
    await state.update_data(
        cycle_selected_materials=auto_selected,
        work_type_name=work_type_name,
    )
    # показываем категории
    await show_material_categories(message, state, "cycle")


async def _show_item_preview_msg(message, state: FSMContext):
    data = await state.get_data()
    items = data["items"]
    idx = data["idx"]
    item = items[idx]
    common = data["common_part"]
    pos_num = data.get("position_number") or ""
    work_name = render_cycle_name(item.get("name_template"), common)
    sheets = data.get("item_sheets", "—")
    start_date = data["item_start_date"]
    end_date = data["item_end_date"]
    cipher = data.get("item_cipher") or "—"
    section = data.get("item_section") or "—"
    act_number = str(data["base_act_number"] + idx)
    object_id = data["object_id"]
    materials = get_materials_for_object(object_id)
    selected_ids = data.get("cycle_selected_materials", [])
    selected = [m for m in materials if m["id"] in selected_ids]
    certs_result = data.get("certs_result", {})
    materials_str = format_materials_with_certs(selected, certs_result) or "—"
    full_line = compose_full_work(item["work_type"], work_name, pos_num)
    duplicate = find_duplicate_act(
        object_id,
        item["work_type"],
        work_name,
        pos_num,
        start_date.get("full") or "",
        end_date.get("full") or "",
        work_full=full_line,
        materials_json=materials_to_json(selected, certs_result),
    )
    errors, warnings = validate_act_payload(
        act_number=act_number,
        work_type_name=item["work_type"],
        work_name=work_name,
        full_work=full_line,
        start_date=start_date,
        end_date=end_date,
        position_number=pos_num,
        selected_materials=selected,
        certs_result=certs_result,
        duplicate=duplicate,
    )
    text = (
        f"📋 Работа {idx + 1}/{len(items)}\n"
        f"🔨 {item['work_type']}\n📝 {work_name}\n\n"
        f"🔢 Акт №{act_number}\n"
        f"📅 {start_date['full']} — {end_date['full']}\n"
        f"📂 Раздел: {section} · {cipher}\n"
        f"📄 Листы: {sheets}\n"
        f"📦 {materials_str[:250]}"
    )
    check_text = validation_text(errors, warnings)
    if check_text:
        text += "\n\n" + check_text
    await state.set_state(CycleRun.item_preview)
    await message.answer(text, reply_markup=cycle_item_preview_kb())


@router.callback_query(CycleRun.item_preview, F.data == "preview_edit")
async def cb_preview_edit(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _show_cycle_item(call, state)


@router.callback_query(CycleRun.item_preview, F.data == "preview_pause")
async def cb_preview_pause(call: CallbackQuery, state: FSMContext):
    await call.answer("Остановлено.")
    await state.clear()
    await call.message.answer("⏸ Цикл остановлен. Начните заново.", reply_markup=main_menu_kb())


@router.callback_query(CycleRun.item_preview, F.data == "preview_create")
async def cb_preview_create(call: CallbackQuery, state: FSMContext):
    await call.answer("Генерирую…")
    try:
        data = await state.get_data()
        items = data["items"]
        idx = data["idx"]
        item = items[idx]
        common = data["common_part"]
        pos_num = data.get("position_number") or ""
        work_name = render_cycle_name(item.get("name_template"), common)
        full_work = compose_full_work(item["work_type"], work_name, pos_num)
        sheets = data["item_sheets"]
        object_id = data["object_id"]
        position_id = data.get("position_id")
        start_date = data["item_start_date"]
        end_date = data["item_end_date"]
        act_date = data["item_act_date"]
        cipher = data.get("item_cipher") or ""
        section = data.get("item_section") or ""
        act_number = str(data["base_act_number"] + idx)
        obj = get_object(object_id)
        materials = get_materials_for_object(object_id)
        selected_ids = data.get("cycle_selected_materials", [])
        selected = [m for m in materials if m["id"] in selected_ids]
        certs_result = data.get("certs_result", {})
        errors, _warnings = validate_act_payload(
            act_number=act_number,
            work_type_name=item["work_type"],
            work_name=work_name,
            full_work=full_work,
            start_date=start_date,
            end_date=end_date,
            position_number=pos_num,
            selected_materials=selected,
            certs_result=certs_result,
        )
        if errors:
            await call.message.answer(
                f"❌ Акт №{act_number} не сохранён:\n• " + "\n• ".join(errors)
            )
            return
        materials_str = format_materials_with_certs(selected, certs_result)
        materials_json = materials_to_json(selected, certs_result)
        author_sup = is_author_supervision(object_id, item["work_type"])
        template_data = build_template_data(
            obj,
            full_work,
            sheets,
            cipher or "—",
            start_date,
            end_date,
            act_date,
            materials_str,
            act_number,
            author_supervision=author_sup,
        )
        target = ACTS_DIR / act_filename(act_number, item["work_type"], work_name, pos_num)
        try:
            out_path, _act_id = create_act_with_file(
                template_data,
                target,
                object_id=object_id,
                position_id=position_id,
                act_number=act_number,
                act_date=act_date["full"],
                start_date=start_date["full"],
                end_date=end_date["full"],
                work_full=full_work,
                sheets=sheets,
                section=section,
                cipher=cipher,
                work_type_name=item["work_type"],
                work_name=work_name,
                position_number=pos_num,
                materials_data=materials_json,
                status="ready",
            )
        except DuplicateActNumberError:
            await call.message.answer(
                f"⚠️ Акт №{act_number} уже существует. " "Цикл остановлен, измените базовый номер."
            )
            return
        except Exception as e:
            traceback.print_exc()
            await call.message.answer(f"❌ Ошибка №{act_number}: {e}")
            return
        try:
            file = FSInputFile(out_path)
            await call.message.answer_document(
                file, caption=f"Акт №{act_number} — {item['work_type']}"
            )
        except Exception as e:
            await call.message.answer(f"⚠️ {e}")
        results = data.get("results", [])
        results.append(
            {"num": act_number, "work": full_work, "sheets": sheets, "materials": materials_str}
        )
        new_idx = idx + 1
        await state.update_data(
            results=results,
            idx=new_idx,
            previous_sheets=sheets,
            cycle_selected_materials=[],
            certs_result={},
        )
        if new_idx >= len(items):
            await _finish_cycle(call, state)
            return
        next_item = items[new_idx]
        next_name = render_cycle_name(next_item.get("name_template"), common)
        await call.message.answer(
            f"✅ Акт №{act_number} готов ({new_idx}/{len(items)})\n\n"
            f"➡️ Далее: {next_item['work_type']} — {next_name}"
        )
        await _show_cycle_item(call, state)
    except Exception as e:
        traceback.print_exc()
        try:
            await call.message.answer(f"❌ {e}")
        except Exception:
            pass


async def _finish_cycle(event, state: FSMContext):
    try:
        data = await state.get_data()
        results = data.get("results", [])
        items = data.get("items", [])
        cycle_name = data.get("cycle_name", "")
        common = data.get("common_part", "")
        if not results:
            text = "⚠️ Цикл завершён без актов."
        else:
            lines = [
                f"🏁 Цикл «{cycle_name}» завершён!",
                f"Создано: {len(results)} из {len(items)}\n",
                f"Общая часть: «{common}»\n",
                "Акты:",
            ]
            for r in results:
                lines.append(f"  • №{r['num']} — {r['work'][:55]}… (листы: {r['sheets']})")
            text = "\n".join(lines)
    except Exception as e:
        text = f"⚠️ Цикл завершён (ошибка: {e})"
    await state.clear()
    try:
        if isinstance(event, CallbackQuery):
            await event.message.answer(text, reply_markup=main_menu_kb())
        else:
            await event.answer(text, reply_markup=main_menu_kb())
    except Exception:
        pass
