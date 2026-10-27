# handlers.py
"""
Новый акт (NewAct), back, ловушка.
"""

import os
import json
import traceback

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile

from db import (
    get_object,
    get_positions_for_object,
    get_position,
    get_all_work_types,
    add_work_type,
    get_materials_for_object,
    get_next_act_number,
    act_number_exists,
    get_sections_for_position,
    get_drawings_for_position,
    get_drawings_by_section,
    save_draft_act,
    update_draft_act,
    delete_act,
    get_acts_by_status,
    is_author_supervision,
    find_duplicate_act,
    DuplicateActNumberError,
)
from config import ACTS_DIR, PROJECT_DIR
from docs import check_size, make_input_file
from act_service import (
    create_act_with_file,
    validate_act_payload,
    validation_text,
)
from states import NewAct
from keyboards import (
    main_menu_kb,
    work_types_kb,
    position_group_action_kb,
    positions_in_group_kb,
    positions_grouped_kb,
    sections_kb,
    step_with_back_and_delete_kb,
    step_only_delete_kb,
    delete_confirm_kb,
    drawing_view_kb,
    drawings_list_kb,
    act_preview_kb,
    act_edit_menu_kb,
)
from utils import (
    parse_date,
    date_range_is_valid,
    format_materials_with_certs,
    act_filename,
    build_template_data,
    materials_to_json,
    compose_full_work,
    _range_str_from_numbers,
    _first_position_number,
    _show_positions_menu,
)
from materials_view import show_material_categories

router = Router()


# =====================================================================
#  НОВЫЙ АКТ
# =====================================================================


@router.message(NewAct.entering_act_number)
async def msg_new_act_number(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()
    edit_mode = data.get("_edit_mode", False)
    if not text:
        text = get_next_act_number(data["object_id"])
    if len(text) > 10:
        await message.answer("⚠️ Слишком длинный номер.", reply_markup=step_only_delete_kb())
        return
    if act_number_exists(data["object_id"], text, exclude_act_id=data.get("_draft_act_id")):
        await message.answer(
            f"⚠️ Акт №{text} уже существует у этого объекта. "
            "Введите другой номер или удалите старый акт.",
            reply_markup=step_only_delete_kb(),
        )
        return
    await state.update_data(act_number=text)
    if edit_mode:
        await state.update_data(_edit_mode=False)
        await _show_final_preview(message, state)
        return
    positions = get_positions_for_object(data["object_id"])
    if not positions:
        await message.answer("⚠️ У объекта нет позиций.")
        await state.clear()
        return
    await state.set_state(NewAct.choosing_position)
    await _show_positions_menu(message, state, prefix=f"📋 Акт №{text}\n\n📍 Выберите позицию:")


@router.callback_query(NewAct.choosing_position, F.data.startswith("pos_grp:"))
async def cb_new_position_group(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":", 1)[1])
    data = await state.get_data()
    groups = data.get("position_groups", [])
    if idx >= len(groups):
        await call.answer("Не найдено", show_alert=True)
        return
    g = groups[idx]
    if len(g["positions"]) == 1:
        await _apply_new_position(call, state, g["positions"][0])
        return
    await call.message.edit_text(
        f"📍 {g['name']} — выберите вариант:",
        reply_markup=position_group_action_kb(g, idx),
    )
    await call.answer()


@router.callback_query(NewAct.choosing_position, F.data == "pos_grp_back")
async def cb_new_positions_back(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    groups = data.get("position_groups", [])
    await call.message.edit_text(
        "📍 Выберите позицию:",
        reply_markup=positions_grouped_kb(groups),
    )
    await call.answer()


@router.callback_query(NewAct.choosing_position, F.data.startswith("pos_back_group:"))
async def cb_new_position_back_to_group(call: CallbackQuery, state: FSMContext):
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


@router.callback_query(NewAct.choosing_position, F.data.startswith("pos_single:"))
async def cb_new_position_single(call: CallbackQuery, state: FSMContext):
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


@router.callback_query(NewAct.choosing_position, F.data.startswith("pos_all:"))
async def cb_new_position_all(call: CallbackQuery, state: FSMContext):
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

    wt = data.get("work_type_name") or ""
    wn = data.get("work_name") or ""
    if wt or wn:
        full_work = compose_full_work(wt, wn, range_str)
    else:
        full_work = None

    await state.update_data(
        position_id=None,
        position_number=range_str,
        search_position_number=first_pos,
        position_name=g["name"],
        full_work=full_work,
    )

    if data.get("_edit_mode"):
        await state.update_data(_edit_mode=False)
        await call.answer("Обновлено")
        await _show_final_preview(call.message, state)
        return

    work_types = get_all_work_types()
    if not work_types:
        await call.message.edit_text("⚠️ Нет типов работ в БД.")
        await state.clear()
        await call.answer()
        return
    await state.set_state(NewAct.choosing_work_type)
    await call.message.edit_text(
        f"📋 Акт №{data['act_number']}  ·  №{range_str}\n"
        f"📍 {g['name'][:60]}\n\n🔨 Выберите тип работы:",
        reply_markup=work_types_kb(work_types),
    )
    await call.answer()


@router.callback_query(NewAct.choosing_position, F.data.startswith("pos_id:"))
async def cb_new_choose_position(call: CallbackQuery, state: FSMContext):
    position_id = int(call.data.split(":", 1)[1])
    pos = get_position(position_id)
    if not pos:
        await call.answer("Позиция не найдена", show_alert=True)
        return
    await _apply_new_position(call, state, pos)


async def _apply_new_position(call: CallbackQuery, state: FSMContext, pos):
    data = await state.get_data()
    pos_num = (pos.get("position_number") or "").strip()
    await state.update_data(
        position_id=pos["id"],
        position_number=pos_num,
        search_position_number=pos_num,
        position_name=pos.get("name") or "",
    )
    wt = data.get("work_type_name") or ""
    wn = data.get("work_name") or ""
    if wt or wn:
        await state.update_data(full_work=compose_full_work(wt, wn, pos_num))

    if data.get("_edit_mode"):
        await state.update_data(_edit_mode=False)
        await call.answer("Обновлено")
        await _show_final_preview(call.message, state)
        return

    work_types = get_all_work_types()
    if not work_types:
        await call.message.edit_text("⚠️ Нет типов работ в БД.")
        await state.clear()
        await call.answer()
        return
    await state.set_state(NewAct.choosing_work_type)
    num_line = f"№{pos_num}" if pos_num else "без номера"
    await call.message.edit_text(
        f"📋 Акт №{data['act_number']}  ·  {num_line}\n"
        f"📍 {(pos.get('name') or '')[:60]}\n\n🔨 Выберите тип работы:",
        reply_markup=work_types_kb(work_types),
    )
    await call.answer()


@router.callback_query(NewAct.choosing_work_type, F.data == "wt_new")
async def cb_new_work_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(NewAct.entering_work_type_new)
    await call.message.edit_text(
        "📝 Введите новый тип работы:", reply_markup=step_with_back_and_delete_kb()
    )


@router.message(NewAct.entering_work_type_new)
async def msg_new_work_type(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 200:
        await message.answer("⚠️ 1-200 символов.", reply_markup=step_with_back_and_delete_kb())
        return
    _, created = add_work_type(name)
    if created:
        await message.answer(f"✅ «{name}» добавлен в справочник.")
    else:
        await message.answer(f"ℹ️ «{name}» уже есть.")
    await state.update_data(work_type_name=name)
    data = await state.get_data()
    await state.set_state(NewAct.entering_work_name)
    pos_num = data.get("position_number") or ""
    suffix = f" «позиция №{pos_num}»" if pos_num else " (без номера)"
    await message.answer(
        f"🔨 Тип: «{name}»\n\n"
        f"📝 Введи наименование работы над объектом.\n\n"
        f"В конец добавится:{suffix}",
        reply_markup=step_with_back_and_delete_kb(),
    )


@router.callback_query(NewAct.choosing_work_type, F.data.startswith("wt:"))
async def cb_new_choose_work_type(call: CallbackQuery, state: FSMContext):
    wt_id = int(call.data.split(":")[1])
    work_types = get_all_work_types()
    wt = next((w for w in work_types if w["id"] == wt_id), None)
    if not wt:
        await call.answer("Не найден", show_alert=True)
        return
    data = await state.get_data()
    await state.update_data(work_type_name=wt["name"])
    wn = data.get("work_name") or ""
    pos_num = data.get("position_number") or ""
    if wn or pos_num:
        await state.update_data(full_work=compose_full_work(wt["name"], wn, pos_num))
    edit_mode = data.get("_edit_mode", False)
    if edit_mode:
        await state.update_data(_edit_mode=False)
        await call.answer("Обновлено")
        await _show_final_preview(call.message, state)
        return
    await state.set_state(NewAct.entering_work_name)
    pos_num = data.get("position_number") or ""
    suffix = f" «позиция №{pos_num}»" if pos_num else " (без номера)"
    await call.message.edit_text(
        f"🔨 Тип: «{wt['name']}»\n\n"
        f"📝 Введи наименование работы над объектом.\n\n"
        f"В конец добавится:{suffix}",
        reply_markup=step_with_back_and_delete_kb(),
    )
    await call.answer()


@router.message(NewAct.entering_work_name)
async def msg_new_work_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 400:
        await message.answer("⚠️ 1-400 символов.", reply_markup=step_with_back_and_delete_kb())
        return
    data = await state.get_data()
    wt = data["work_type_name"]
    pos_num = data.get("position_number") or ""
    full_work = compose_full_work(wt, name, pos_num)
    await state.update_data(work_name=name, full_work=full_work)
    edit_mode = data.get("_edit_mode", False)
    if edit_mode:
        await state.update_data(_edit_mode=False)
        await _show_final_preview(message, state)
        return
    search_num = data.get("search_position_number") or pos_num
    sections = get_sections_for_position(data["object_id"], search_num)
    if not sections:
        await state.update_data(section=None, cipher=None, pdf_path=None)
        await state.set_state(NewAct.entering_sheets)
        await message.answer(
            f"✅ Работа: «{full_work}»\n\n"
            f"⚠️ Чертежей по позиции в БД нет.\n"
            f"Введи номера листов (или «—»):",
            reply_markup=step_with_back_and_delete_kb(),
        )
        return
    await state.set_state(NewAct.choosing_section)
    await message.answer(
        f"✅ Работа: «{full_work}»\n\n📂 Выберите раздел проекта:",
        reply_markup=sections_kb(sections),
    )


@router.callback_query(NewAct.choosing_section, F.data.startswith("sec:"))
async def cb_new_choose_section(call: CallbackQuery, state: FSMContext):
    section = call.data.split(":", 1)[1]
    data = await state.get_data()
    search_num = data.get("search_position_number") or data.get("position_number") or ""
    drawings = get_drawings_by_section(data["object_id"], search_num, section)
    if not drawings:
        await state.update_data(section=section, cipher=None, pdf_path=None)
        if data.get("_edit_mode"):
            await state.update_data(_edit_mode=False)
            await call.answer("Обновлено")
            await _show_final_preview(call.message, state)
            return
        await state.set_state(NewAct.entering_sheets)
        await call.message.edit_text(
            f"📂 Раздел: {section}\n\n⚠️ PDF не найден.\nВведи листы:",
            reply_markup=step_with_back_and_delete_kb(),
        )
        await call.answer()
        return
    d = drawings[0]
    full_path = PROJECT_DIR / d["file_path"]
    await state.update_data(
        section=section,
        cipher=d["cipher"],
        pdf_path=full_path,
        drawing_id=d["id"],
    )
    if data.get("_edit_mode"):
        await state.update_data(_edit_mode=False)
        await call.answer("Обновлено")
        await _show_final_preview(call.message, state)
        return
    await state.set_state(NewAct.viewing_drawing)
    await call.answer()
    file_name = os.path.basename(d["file_path"])
    await call.message.edit_text(
        f"📂 Раздел: {section}\n"
        f"📐 Шифр: {d['cipher']}\n"
        f"📄 Файл: {file_name}\n\n"
        f"Чертежи по данной работе лежат в этом PDF.",
        reply_markup=drawing_view_kb(),
    )


@router.callback_query(NewAct.viewing_drawing, F.data == "drw:open")
async def cb_drawing_open(call: CallbackQuery, state: FSMContext):
    await call.answer("Отправляю…")
    data = await state.get_data()
    section = data.get("section") or "—"
    cipher = data.get("cipher") or "—"
    full_path = data.get("pdf_path")
    if full_path and os.path.exists(full_path):
        ok, size_mb, err = check_size(full_path)
        if ok:
            try:
                file = make_input_file(full_path)
                await call.message.answer_document(file, caption=f"📂 {section} · {cipher}")
            except Exception as e:
                await call.message.answer(f"⚠️ Ошибка отправки PDF: {e}")
        else:
            await call.message.answer(f"⚠️ {err}")
    else:
        await call.message.answer("⚠️ Файл не найден.")
    if data.get("_edit_mode"):
        await state.update_data(_edit_mode=False)
        await _show_final_preview(call.message, state)
        return
    await state.set_state(NewAct.entering_sheets)
    await call.message.answer(
        "✏️ Введите номера листов для акта (например: 3-10):",
        reply_markup=step_with_back_and_delete_kb(),
    )


@router.callback_query(NewAct.viewing_drawing, F.data == "drw:all")
@router.callback_query(NewAct.entering_sheets, F.data == "drw:all")
@router.callback_query(NewAct.viewing_all_drawings, F.data == "drw:all")
async def cb_drawing_all(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    search_num = data.get("search_position_number") or data.get("position_number") or ""
    drawings = get_drawings_for_position(data["object_id"], search_num)
    if not drawings:
        await call.message.answer("⚠️ Чертежей нет.")
        return
    await state.set_state(NewAct.viewing_all_drawings)
    await call.message.answer(
        f"📂 Все чертежи по позиции ({len(drawings)}):\n\nВыбери нужный:",
        reply_markup=drawings_list_kb(drawings),
    )


@router.callback_query(NewAct.viewing_drawing, F.data == "drw:manual")
@router.callback_query(NewAct.entering_sheets, F.data == "drw:manual")
@router.callback_query(NewAct.viewing_all_drawings, F.data == "drw:manual")
async def cb_drawing_manual(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    await state.update_data(section=None, cipher=None, pdf_path=None)
    if data.get("_edit_mode"):
        await state.update_data(_edit_mode=False)
        await _show_final_preview(call.message, state)
        return
    await state.set_state(NewAct.entering_sheets)
    await call.message.answer(
        "✏️ Введи номера листов (например: 3-10):",
        reply_markup=step_with_back_and_delete_kb(),
    )


@router.callback_query(NewAct.viewing_all_drawings, F.data.startswith("drwpick:"))
async def cb_drawing_pick(call: CallbackQuery, state: FSMContext):
    d_id = int(call.data.split(":")[1])
    data = await state.get_data()
    search_num = data.get("search_position_number") or data.get("position_number") or ""
    drawings = get_drawings_for_position(data["object_id"], search_num)
    d = next((x for x in drawings if x["id"] == d_id), None)
    if not d:
        await call.answer("Не найдено", show_alert=True)
        return
    full_path = PROJECT_DIR / d["file_path"]
    await state.update_data(
        section=d["section"], cipher=d["cipher"], pdf_path=full_path, drawing_id=d["id"]
    )
    await call.answer("✅ Выбран")
    try:
        await call.message.delete()
    except Exception:
        pass
    await state.set_state(NewAct.viewing_drawing)
    file_name = os.path.basename(d["file_path"])
    await call.message.answer(
        f"📂 Раздел: {d['section']}\n"
        f"📐 Шифр: {d['cipher']}\n"
        f"📄 Файл: {file_name}\n\n"
        f"Чертежи по данной работе лежат в этом PDF.",
        reply_markup=drawing_view_kb(),
    )


@router.message(NewAct.entering_sheets)
async def msg_new_sheets(message: Message, state: FSMContext):
    sheets = (message.text or "").strip()
    if not sheets or len(sheets) > 60:
        await message.answer("⚠️ 1-60 символов.", reply_markup=step_with_back_and_delete_kb())
        return
    await state.update_data(sheets=sheets)
    data = await state.get_data()
    if data.get("_edit_mode"):
        await state.update_data(_edit_mode=False)
        await _show_final_preview(message, state)
        return
    # показываем категории материалов
    await show_material_categories(message, state, "newact")


# =====================================================================
#  ВОЗВРАТ НАЗАД
# =====================================================================

NEWACT_BACK_MAP = {
    NewAct.choosing_position.state: "number",
    NewAct.choosing_work_type.state: "position",
    NewAct.entering_work_name.state: "work_type",
    NewAct.choosing_section.state: "work_name",
    NewAct.viewing_drawing.state: "section",
    NewAct.viewing_all_drawings.state: "drawing",
    NewAct.entering_sheets.state: "drawing_or_section",
    NewAct.choosing_materials.state: "sheets",
    NewAct.choosing_cert.state: "materials",
    NewAct.entering_cert_doc_type.state: "materials",
    NewAct.entering_cert_doc_type_custom.state: "materials",
    NewAct.entering_cert_number.state: "materials",
    NewAct.entering_cert_date.state: "materials",
    NewAct.asking_save_cert.state: "materials",
    NewAct.entering_start_date.state: "materials",
    NewAct.entering_end_date.state: "start_date",
    NewAct.final_preview.state: "dates",
    NewAct.entering_act_number.state: None,
    NewAct.entering_work_type_new.state: "work_type",
}


@router.callback_query(StateFilter(NewAct), F.data == "na:back")
async def cb_na_back(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    data = await state.get_data()

    if data.get("_edit_mode"):
        await state.update_data(_edit_mode=False)
        await call.answer("↩ Возврат в итог")
        await _show_final_preview(call.message, state)
        return

    # если мы внутри категории материалов — вернёмся к категориям
    if current == NewAct.choosing_materials.state and data.get("_mat_current_cat") is not None:
        await call.answer()
        try:
            await call.message.delete()
        except Exception:
            pass
        await show_material_categories(call.message, state, "newact")
        return

    target = NEWACT_BACK_MAP.get(current)
    if not target:
        await call.answer("Назад недоступно на этом шаге.", show_alert=True)
        return
    await call.answer()
    await _render_newact_step(call.message, state, target)


async def _render_newact_step(message, state: FSMContext, name: str):
    data = await state.get_data()
    object_id = data.get("object_id")

    if name == "number":
        await state.update_data(act_number=None)
        await state.set_state(NewAct.entering_act_number)
        next_num = get_next_act_number(object_id)
        drafts = get_acts_by_status(object_id, "draft", limit=50)
        draft_nums = [a["act_number"] for a in drafts if a.get("act_number")]
        text = f"🔢 Введите номер акта (предлагаю {next_num}):"
        if draft_nums:
            text += "\n\n⚠️ Есть недоделанные акты: " + ", ".join(f"№{n}" for n in draft_nums[:10])
        await message.answer(text, reply_markup=step_only_delete_kb())

    elif name == "position":
        await state.update_data(
            position_id=None,
            position_number=None,
            search_position_number=None,
            position_name=None,
            work_type_name=None,
            work_name=None,
            full_work=None,
            section=None,
            cipher=None,
            pdf_path=None,
            drawing_id=None,
            sheets=None,
            selected_materials=[],
            certs_result={},
        )
        await state.set_state(NewAct.choosing_position)
        await _show_positions_menu(
            message,
            state,
            prefix=f"📋 Акт №{data.get('act_number')}\n\n📍 Выберите позицию:",
        )

    elif name == "work_type":
        await state.update_data(
            work_type_name=None,
            work_name=None,
            full_work=None,
            section=None,
            cipher=None,
            pdf_path=None,
            drawing_id=None,
        )
        await state.set_state(NewAct.choosing_work_type)
        work_types = get_all_work_types()
        pos_num = data.get("position_number") or ""
        num_line = f"№{pos_num}" if pos_num else "без номера"
        await message.answer(
            f"📋 Акт №{data.get('act_number')}  ·  {num_line}\n"
            f"📍 {(data.get('position_name') or '')[:60]}\n\n"
            f"🔨 Выберите тип работы:",
            reply_markup=work_types_kb(work_types),
        )

    elif name == "work_name":
        await state.update_data(
            work_name=None, full_work=None, section=None, cipher=None, pdf_path=None
        )
        await state.set_state(NewAct.entering_work_name)
        pos_num = data.get("position_number") or ""
        suffix = f" «позиция №{pos_num}»" if pos_num else " (без номера)"
        await message.answer(
            f"🔨 Тип: «{data.get('work_type_name')}»\n\n"
            f"📝 Введи наименование работы над объектом.\n\n"
            f"В конец добавится:{suffix}",
            reply_markup=step_with_back_and_delete_kb(),
        )

    elif name == "section":
        await state.update_data(section=None, cipher=None, pdf_path=None, drawing_id=None)
        await state.set_state(NewAct.choosing_section)
        search_num = data.get("search_position_number") or data.get("position_number") or ""
        sections = get_sections_for_position(object_id, search_num)
        if not sections:
            await state.set_state(NewAct.entering_sheets)
            await message.answer(
                "⚠️ Чертежей по позиции нет.\nВведи номера листов:",
                reply_markup=step_with_back_and_delete_kb(),
            )
            return
        await message.answer("📂 Выберите раздел проекта:", reply_markup=sections_kb(sections))

    elif name == "drawing":
        pdf_path = data.get("pdf_path")
        if not pdf_path:
            await _render_newact_step(message, state, "section")
            return
        await state.set_state(NewAct.viewing_drawing)
        section = data.get("section") or "—"
        cipher = data.get("cipher") or "—"
        file_name = os.path.basename(pdf_path)
        await message.answer(
            f"📂 Раздел: {section}\n"
            f"📐 Шифр: {cipher}\n"
            f"📄 Файл: {file_name}\n\n"
            f"Чертежи по данной работе лежат в этом PDF.",
            reply_markup=drawing_view_kb(),
        )

    elif name == "drawing_or_section":
        if data.get("pdf_path"):
            await _render_newact_step(message, state, "drawing")
        else:
            await _render_newact_step(message, state, "section")

    elif name == "sheets":
        await state.update_data(sheets=None)
        await state.set_state(NewAct.entering_sheets)
        await message.answer(
            "✏️ Введи номера листов (например: 3-10):",
            reply_markup=step_with_back_and_delete_kb(),
        )

    elif name == "materials":
        await state.update_data(
            selected_materials=[], certs_result={}, start_date=None, end_date=None, act_date=None
        )
        await show_material_categories(message, state, "newact")

    elif name == "start_date":
        await state.update_data(end_date=None, act_date=None)
        await state.set_state(NewAct.entering_end_date)
        await message.answer(
            "📅 Дата окончания (ДД.ММ.ГГГГ) — она же дата акта:",
            reply_markup=step_with_back_and_delete_kb(),
        )

    elif name == "dates":
        await state.update_data(start_date=None, end_date=None, act_date=None)
        await state.set_state(NewAct.entering_start_date)
        await message.answer(
            "📅 Дата начала работ (ДД.ММ.ГГГГ):",
            reply_markup=step_with_back_and_delete_kb(),
        )


@router.callback_query(StateFilter(NewAct), F.data == "na:del")
async def cb_na_del(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    num = data.get("act_number") or "—"
    await call.message.answer(
        f"⚠️ Удалить акт №{num} и вернуться в главное меню?\n"
        f"Все введённые данные будут потеряны.",
        reply_markup=delete_confirm_kb(),
    )


@router.callback_query(F.data == "na:del_yes")
async def cb_na_del_yes(call: CallbackQuery, state: FSMContext):
    await call.answer("Удалено")
    await state.clear()
    try:
        await call.message.edit_text("🗑 Акт удалён.")
    except Exception:
        pass
    await call.message.answer("Выбери действие:", reply_markup=main_menu_kb())


@router.callback_query(F.data == "na:del_no")
async def cb_na_del_no(call: CallbackQuery, state: FSMContext):
    await call.answer("↩ Продолжаем")
    try:
        await call.message.edit_text("↩ Продолжаем работу над актом.")
    except Exception:
        pass


# ---------- Финальный предпросмотр ----------


async def _show_final_preview(message, state: FSMContext):
    data = await state.get_data()
    act_number = data.get("act_number", "—")
    position_number = data.get("position_number") or ""
    position_name = data.get("position_name", "—")
    full_work = data.get("full_work") or compose_full_work(
        data.get("work_type_name"), data.get("work_name"), position_number
    )
    cipher = data.get("cipher") or "—"
    section = data.get("section") or "—"
    sheets = data.get("sheets") or "—"
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    dates_str = "—"
    if start_date and end_date:
        dates_str = f"{start_date['full']} — {end_date['full']}"
    materials = get_materials_for_object(data["object_id"])
    selected_ids = data.get("selected_materials", [])
    selected = [m for m in materials if m["id"] in selected_ids]
    certs_result = data.get("certs_result", {})
    mat_str = format_materials_with_certs(selected, certs_result) or "—"
    pos_line = f"позиция №{position_number}" if position_number else "без номера"

    duplicate = None
    if start_date and end_date:
        duplicate = find_duplicate_act(
            data["object_id"],
            data.get("work_type_name") or "",
            data.get("work_name") or "",
            position_number,
            start_date.get("full") or "",
            end_date.get("full") or "",
            exclude_act_id=data.get("_draft_act_id"),
            work_full=full_work,
            materials_json=materials_to_json(selected, certs_result),
        )
    errors, warnings = validate_act_payload(
        act_number=act_number,
        work_type_name=data.get("work_type_name"),
        work_name=data.get("work_name"),
        full_work=full_work,
        start_date=start_date,
        end_date=end_date,
        position_number=position_number,
        selected_materials=selected,
        certs_result=certs_result,
        duplicate=duplicate,
    )
    text = (
        f"📋 АКТ №{act_number}\n\n"
        f"📍 {position_name[:60]} ({pos_line})\n"
        f"🔨 Работа: {full_work[:120]}\n\n"
        f"📂 Раздел: {section} · {cipher}\n"
        f"📄 Листы: {sheets}\n"
        f"📦 Материалы: {mat_str[:250]}\n"
        f"📅 {dates_str}"
    )
    check_text = validation_text(errors, warnings)
    if check_text:
        text += "\n\n" + check_text
    await state.set_state(NewAct.final_preview)
    await message.answer(
        text,
        reply_markup=act_preview_kb(
            confirm_enabled=not errors,
            duplicate=bool(duplicate),
        ),
    )


@router.callback_query(NewAct.final_preview, F.data == "na:confirm")
async def cb_na_confirm(call: CallbackQuery, state: FSMContext):
    await call.answer("Генерирую…")
    try:
        await _generate_and_save_final(call.message, state, save_as="ready")
    except Exception as e:
        traceback.print_exc()
        await call.message.answer(f"❌ Ошибка: {e}")


@router.callback_query(NewAct.final_preview, F.data == "na:draft")
async def cb_na_draft(call: CallbackQuery, state: FSMContext):
    await call.answer("Откладываю…")
    await _save_draft(call.message, state)


async def _save_draft(message, state: FSMContext):
    data = await state.get_data()
    object_id = data.get("object_id")
    act_number = data.get("act_number", "—")
    if not object_id:
        await message.answer("⚠️ Не удалось сохранить.")
        return
    draft_json = json.dumps(
        {
            "position_id": data.get("position_id"),
            "position_number": data.get("position_number"),
            "search_position_number": data.get("search_position_number"),
            "position_name": data.get("position_name"),
            "work_type_name": data.get("work_type_name"),
            "work_name": data.get("work_name"),
            "full_work": data.get("full_work"),
            "section": data.get("section"),
            "cipher": data.get("cipher"),
            "pdf_path": data.get("pdf_path"),
            "drawing_id": data.get("drawing_id"),
            "sheets": data.get("sheets"),
            "selected_materials": data.get("selected_materials", []),
            "certs_result": data.get("certs_result", {}),
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date"),
            "act_date": data.get("act_date"),
        },
        ensure_ascii=False,
    )
    draft_step = data.get("_current_step", "preview")
    if data.get("_draft_act_id"):
        update_draft_act(data["_draft_act_id"], draft_step, draft_json)
    else:
        save_draft_act(object_id, act_number, draft_step, draft_json)
    await state.clear()
    await message.answer(
        f"⏸ Акт №{act_number} отложен.\n"
        f"Вернуться можно через «📄 Мои акты» → «✏️ Недоделанные».",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(NewAct.final_preview, F.data == "na:edit")
async def cb_na_edit(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("✏️ Что изменить?", reply_markup=act_edit_menu_kb())


@router.callback_query(NewAct.final_preview, F.data.startswith("nae:"))
async def cb_nae(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":")[1]
    data = await state.get_data()
    await state.update_data(_edit_mode=True)
    if field == "number":
        await state.set_state(NewAct.entering_act_number)
        await call.message.answer(
            "🔢 Введи новый номер:", reply_markup=step_with_back_and_delete_kb()
        )
    elif field == "position":
        await state.set_state(NewAct.choosing_position)
        await _show_positions_menu(call.message, state, prefix="📍 Выбери позицию:")
    elif field == "work_type":
        work_types = get_all_work_types()
        await state.set_state(NewAct.choosing_work_type)
        await call.message.answer("🔨 Выбери тип работы:", reply_markup=work_types_kb(work_types))
    elif field == "work_name":
        await state.set_state(NewAct.entering_work_name)
        await call.message.answer(
            "📝 Введи наименование:", reply_markup=step_with_back_and_delete_kb()
        )
    elif field == "drawing":
        search_num = data.get("search_position_number") or data.get("position_number") or ""
        sections = get_sections_for_position(data["object_id"], search_num)
        if not sections:
            await call.answer("Разделов нет", show_alert=True)
            return
        await state.set_state(NewAct.choosing_section)
        await call.message.answer("📂 Выбери раздел:", reply_markup=sections_kb(sections))
    elif field == "sheets":
        await state.set_state(NewAct.entering_sheets)
        await call.message.answer("📄 Введи листы:", reply_markup=step_with_back_and_delete_kb())
    elif field == "materials":
        await call.message.answer("📦 Открываю материалы…")
        await show_material_categories(call.message, state, "newact")
    elif field == "dates":
        await state.set_state(NewAct.entering_start_date)
        await call.message.answer("📅 Дата начала:", reply_markup=step_with_back_and_delete_kb())
    await call.answer()


@router.message(NewAct.entering_start_date)
async def msg_new_start_date(message: Message, state: FSMContext):
    try:
        d = parse_date(message.text or "")
    except ValueError as e:
        await message.answer(f"⚠️ {e}", reply_markup=step_with_back_and_delete_kb())
        return
    await state.update_data(start_date=d)
    await state.set_state(NewAct.entering_end_date)
    await message.answer(
        "📅 Дата окончания (ДД.ММ.ГГГГ) — она же дата акта:",
        reply_markup=step_with_back_and_delete_kb(),
    )


@router.message(NewAct.entering_end_date)
async def msg_new_end_date(message: Message, state: FSMContext):
    try:
        d = parse_date(message.text or "")
    except ValueError as e:
        await message.answer(f"⚠️ {e}", reply_markup=step_with_back_and_delete_kb())
        return
    data = await state.get_data()
    if not date_range_is_valid(data.get("start_date"), d):
        await message.answer(
            "⚠️ Дата окончания не может быть раньше даты начала.",
            reply_markup=step_with_back_and_delete_kb(),
        )
        return
    await state.update_data(end_date=d, act_date=d)
    await _show_final_preview(message, state)


async def _generate_and_save_final(message, state: FSMContext, save_as="ready"):
    data = await state.get_data()
    object_id = data["object_id"]
    position_id = data.get("position_id")
    position_number = data.get("position_number") or ""
    work_type_name = data.get("work_type_name", "")
    work_name = data.get("work_name", "")
    full_work = data.get("full_work") or compose_full_work(
        work_type_name, work_name, position_number
    )
    sheets = data.get("sheets", "")
    section = data.get("section") or ""
    cipher = data.get("cipher") or ""
    act_number = data.get("act_number")
    act_date = data.get("act_date") or data.get("end_date")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    obj = get_object(object_id)
    materials = get_materials_for_object(object_id)
    selected_ids = data.get("selected_materials", [])
    selected = [m for m in materials if m["id"] in selected_ids]
    certs_result = data.get("certs_result", {})
    errors, _warnings = validate_act_payload(
        act_number=act_number,
        work_type_name=work_type_name,
        work_name=work_name,
        full_work=full_work,
        start_date=start_date,
        end_date=end_date,
        position_number=position_number,
        selected_materials=selected,
        certs_result=certs_result,
    )
    if errors or not act_date:
        await message.answer(
            "❌ Акт не сохранён:\n• " + "\n• ".join(errors or ["не указана дата акта"])
        )
        return
    materials_str = format_materials_with_certs(selected, certs_result)
    materials_json = materials_to_json(selected, certs_result)
    author_sup = is_author_supervision(object_id, work_type_name)
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
    target = ACTS_DIR / act_filename(act_number, work_type_name, work_name, position_number)
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
            work_type_name=work_type_name,
            work_name=work_name,
            position_number=position_number,
            materials_data=materials_json,
            status=save_as,
        )
    except DuplicateActNumberError:
        await message.answer(
            f"⚠️ Акт №{act_number} уже существует. " "Измените номер или удалите существующий акт."
        )
        return
    except Exception as e:
        traceback.print_exc()
        await message.answer(f"❌ Ошибка генерации: {e}")
        return
    await message.answer(
        f"✅ Акт №{act_number} готов!\n"
        f"Работа: {full_work[:80]}…\n"
        f"Раздел: {cipher or '—'}\nЛисты: {sheets or '—'}\n"
        f"Материалов: {len(selected)}"
        + (f"\n🎨 Авторский надзор: {obj.get('author_short')}" if author_sup else "")
    )
    try:
        file = FSInputFile(out_path)
        await message.answer_document(file, caption=f"Акт №{act_number}")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка отправки: {e}")
    if data.get("_draft_act_id"):
        try:
            delete_act(data["_draft_act_id"])
        except Exception:
            pass
    await state.clear()


# =====================================================================
#  BACK
# =====================================================================


@router.callback_query(F.data == "back")
async def cb_back(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if not current:
        await call.answer("Нечего отменять.", show_alert=True)
        return
    if current.startswith("CycleRun:"):
        from db import get_cycles_for_user
        from keyboards import cycles_kb
        from states import CycleRun

        tg_id = call.from_user.id
        cycles = get_cycles_for_user(tg_id)
        await state.set_state(CycleRun.choosing_cycle)
        await call.message.edit_text("📋 Выберите цикл:", reply_markup=cycles_kb(cycles, tg_id))
        await call.answer()
        return
    await call.answer("Используйте ❌.", show_alert=True)


# =====================================================================
#  ЛОВУШКА
# =====================================================================


@router.message()
async def catch_all(message: Message):
    print(f"⚠️ Необработано: {message.text!r}")
    await message.answer(
        f"Не понимаю: «{message.text}»\n\nИспользуй кнопки снизу или /start.",
        reply_markup=main_menu_kb(),
    )
