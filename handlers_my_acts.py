# handlers_my_acts.py
"""
Мои акты (готовые / история / недоделанные) и редактирование актов.
"""
import json
import traceback

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile

from config import ACTS_DIR, resolve_path, to_stored_path
from db import (
    get_all_objects, get_object,
    get_materials_for_object,
    get_sections_for_position,
    get_drawing,
    get_act, update_act, delete_act, set_act_status, act_number_exists,
    get_acts_by_status, get_act_status_counts,
    is_author_supervision,
)
from generate_act import build_act
from states import EditAct
from keyboards import (
    sections_kb,
    my_acts_categories_kb, acts_list_kb, act_card_kb, act_label,
    act_delete_confirm_kb,
    edit_act_menu_kb,
    edit_act_menu_back_kb,
)
from utils import (
    parse_date,
    format_materials_with_certs, act_filename, build_template_data,
    materials_to_json, materials_from_json, _parse_date_or_none,
)
from materials_view import show_material_categories
from handlers_certs import _cert_next
from storage import archive_act_file


router = Router()


# =====================================================================
#  МОИ АКТЫ
# =====================================================================

@router.callback_query(F.data == "myacts:menu")
async def cb_myacts_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    obj_id = data.get("object_id")
    if not obj_id:
        objs = get_all_objects()
        if not objs:
            return
        obj_id = objs[0]["id"]
        await state.update_data(object_id=obj_id)
    obj = get_object(obj_id)
    counts = get_act_status_counts(obj_id)
    try:
        await call.message.edit_text(
            f"📄 Мои акты\nОбъект: {obj['name'][:80]}\n\nВыберите категорию:",
            reply_markup=my_acts_categories_kb(counts, obj["name"]),
        )
    except Exception:
        await call.message.answer(
            f"📄 Мои акты\nОбъект: {obj['name'][:80]}",
            reply_markup=my_acts_categories_kb(counts, obj["name"]),
        )


@router.callback_query(F.data.startswith("myacts:"))
async def cb_myacts_category(call: CallbackQuery, state: FSMContext):
    cat = call.data.split(":")[1]
    await call.answer()
    if cat == "menu":
        return
    data = await state.get_data()
    obj_id = data.get("object_id")
    if not obj_id:
        objs = get_all_objects()
        if not objs:
            return
        obj_id = objs[0]["id"]
        await state.update_data(object_id=obj_id)
    status_map = {"ready": "ready", "printed": "printed", "draft": "draft"}
    if cat not in status_map:
        return
    acts = get_acts_by_status(obj_id, status_map[cat], limit=100)
    titles = {
        "ready": "🆕 Готовые акты",
        "printed": "🖨 История (распечатанные)",
        "draft": "✏️ Недоделанные",
    }
    if not acts:
        await call.message.answer(f"{titles[cat]}\n\nСписок пуст.")
        return
    prefix_map = {"ready": "act_ready", "printed": "act_printed",
                  "draft": "act_draft"}
    await call.message.answer(
        f"{titles[cat]} ({len(acts)}):",
        reply_markup=acts_list_kb(acts, prefix_map[cat]),
    )


@router.callback_query(F.data.startswith("act_ready:"))
@router.callback_query(F.data.startswith("act_printed:"))
@router.callback_query(F.data.startswith("act_draft:"))
async def cb_act_view(call: CallbackQuery, state: FSMContext):
    act_id = int(call.data.split(":")[1])
    await call.answer()
    act = get_act(act_id)
    if not act:
        await call.message.answer("Не найден")
        return
    selected_ids, certs_result = materials_from_json(act.get("materials_data"))
    materials = get_materials_for_object(act["object_id"])
    selected = [m for m in materials if m["id"] in selected_ids]
    mat_str = format_materials_with_certs(selected, certs_result) or "—"
    status_label = {
        "draft": "✏️ Черновик",
        "ready": "🆕 Готовый",
        "printed": "🖨 Распечатан",
    }.get(act.get("status") or "ready", "—")
    text = (
        f"📋 {act_label(act)}\n"
        f"Статус: {status_label}\n\n"
        f"🔨 Работа: {(act.get('work_full') or '')[:120]}\n"
        f"📂 Раздел: {act.get('section') or '—'} · {act.get('cipher') or '—'}\n"
        f"📄 Листы: {act.get('sheets') or '—'}\n"
        f"📦 Материалы: {mat_str[:200]}\n"
        f"📅 {act.get('start_date') or '—'} — {act.get('end_date') or '—'}"
    )
    await state.update_data(card_act_id=act_id)
    await call.message.answer(text, reply_markup=act_card_kb(act))


@router.callback_query(F.data.startswith("act_back:"))
async def cb_act_back(call: CallbackQuery, state: FSMContext):
    await call.answer()
    status = call.data.split(":")[1]
    data = await state.get_data()
    obj_id = data.get("object_id")
    if not obj_id:
        objs = get_all_objects()
        if objs:
            obj_id = objs[0]["id"]
    if status not in ("ready", "printed", "draft"):
        return
    acts = get_acts_by_status(obj_id, status, limit=100)
    prefix_map = {"ready": "act_ready", "printed": "act_printed",
                  "draft": "act_draft"}
    titles = {"ready": "🆕 Готовые акты",
              "printed": "🖨 История", "draft": "✏️ Недоделанные"}
    if not acts:
        await call.message.answer(f"{titles[status]}: пусто.")
        return
    await call.message.answer(
        f"{titles[status]} ({len(acts)}):",
        reply_markup=acts_list_kb(acts, prefix_map[status]),
    )


@router.callback_query(F.data.startswith("act_print:"))
async def cb_act_print(call: CallbackQuery, state: FSMContext):
    act_id = int(call.data.split(":")[1])
    set_act_status(act_id, "printed")
    await call.answer("🖨 Перенесено в историю")
    act = get_act(act_id)
    if act:
        await call.message.answer(
            f"✅ {act_label(act)} отмечен как распечатанный.")


@router.callback_query(F.data.startswith("act_unprint:"))
async def cb_act_unprint(call: CallbackQuery, state: FSMContext):
    act_id = int(call.data.split(":")[1])
    set_act_status(act_id, "ready")
    await call.answer("↩ Возвращено в готовые")
    act = get_act(act_id)
    if act:
        await call.message.answer(
            f"✅ {act_label(act)} возвращён в работу.")


@router.callback_query(F.data.startswith("act_del:"))
async def cb_act_del(call: CallbackQuery, state: FSMContext):
    act_id = int(call.data.split(":")[1])
    act = get_act(act_id)
    await call.answer()
    if not act:
        await call.message.answer("Акт не найден.")
        return
    await call.message.answer(
        f"🗑 Удалить акт?\n\n{act_label(act)}\n\n"
        "Файл будет перемещён в архив acts/_deleted, запись удалена.",
        reply_markup=act_delete_confirm_kb(act_id),
    )


@router.callback_query(F.data.startswith("act_del_yes:"))
async def cb_act_del_yes(call: CallbackQuery, state: FSMContext):
    act_id = int(call.data.split(":")[1])
    act = get_act(act_id)
    await call.answer("Удаляю…")
    if not act:
        await call.message.edit_text("Акт уже удалён.")
        return
    archived = archive_act_file(act.get("file_path"))
    delete_act(act_id)
    text = f"🗑 {act_label(act)} удалён."
    if archived:
        text += f"\nФайл в архиве: {archived.name}"
    try:
        await call.message.edit_text(text)
    except Exception:
        await call.message.answer(text)


@router.callback_query(F.data.startswith("act_del_no:"))
async def cb_act_del_no(call: CallbackQuery, state: FSMContext):
    await call.answer("Отменено")
    try:
        await call.message.edit_text("Удаление отменено.")
    except Exception:
        await call.message.answer("Удаление отменено.")


@router.callback_query(F.data.startswith("act_dl:"))
async def cb_act_dl(call: CallbackQuery, state: FSMContext):
    act_id = int(call.data.split(":")[1])
    await call.answer()
    act = get_act(act_id)
    if not act or not act.get("file_path"):
        await call.message.answer("Файл не найден.")
        return
    path = resolve_path(act["file_path"])
    if not path.exists():
        await call.message.answer("⚠️ Файл отсутствует на диске.")
        return
    try:
        file = FSInputFile(path)
        await call.message.answer_document(file, caption=act_label(act))
    except Exception as e:
        await call.message.answer(f"⚠️ Ошибка: {e}")


@router.callback_query(F.data.startswith("act_cont:"))
async def cb_act_cont(call: CallbackQuery, state: FSMContext):
    act_id = int(call.data.split(":")[1])
    await call.answer()
    act = get_act(act_id)
    if not act:
        await call.message.answer("Черновик не найден.")
        return
    try:
        draft = json.loads(act.get("draft_data") or "{}")
    except Exception:
        draft = {}
    await state.clear()
    await state.update_data(
        object_id=act["object_id"],
        act_number=act.get("act_number"),
        _draft_act_id=act_id,
        position_id=draft.get("position_id"),
        position_number=draft.get("position_number"),
        search_position_number=draft.get("search_position_number"),
        position_name=draft.get("position_name"),
        work_type_name=draft.get("work_type_name"),
        work_name=draft.get("work_name"),
        full_work=draft.get("full_work"),
        section=draft.get("section"),
        cipher=draft.get("cipher"),
        pdf_path=draft.get("pdf_path"),
        drawing_id=draft.get("drawing_id"),
        sheets=draft.get("sheets"),
        selected_materials=draft.get("selected_materials", []),
        certs_result=draft.get("certs_result", {}),
        start_date=draft.get("start_date"),
        end_date=draft.get("end_date"),
        act_date=draft.get("act_date"),
    )
    await call.message.answer(f"▶️ Продолжаем акт №{act['act_number']}.")
    from handlers import _show_final_preview
    await _show_final_preview(call.message, state)


# =====================================================================
#  РЕДАКТИРОВАНИЕ АКТА
# =====================================================================

@router.callback_query(F.data.startswith("edit_act:"))
async def cb_edit_act(call: CallbackQuery, state: FSMContext):
    await call.answer()
    act_id = int(call.data.split(":")[1])
    act = get_act(act_id)
    if not act:
        await call.message.answer("⚠️ Акт не найден")
        return
    selected_ids, certs_result = materials_from_json(act.get("materials_data"))
    await state.update_data(
        edit_act_id=act_id,
        edit_object_id=act["object_id"],
        edit_position_id=act.get("position_id"),
        edit_position_number=act.get("position_number") or "",
        edit_work_type_name=act.get("work_type_name") or "",
        edit_work_name=act.get("work_name") or "",
        edit_act_number=act.get("act_number") or "",
        edit_act_date_raw=act.get("act_date") or "",
        edit_start_date_raw=act.get("start_date") or "",
        edit_end_date_raw=act.get("end_date") or "",
        edit_sheets=act.get("sheets") or "",
        edit_section=act.get("section") or "",
        edit_cipher=act.get("cipher") or "",
        edit_selected_materials=selected_ids,
        edit_certs_result=certs_result,
        edit_file_path=act.get("file_path") or "",
        object_id=act["object_id"],
    )
    await state.set_state(EditAct.menu)
    await _edit_send_menu(call.message, state)


async def _edit_send_menu(message, state: FSMContext):
    data = await state.get_data()
    act_id = data["edit_act_id"]
    await state.set_state(EditAct.menu)
    materials = get_materials_for_object(data["edit_object_id"])
    selected_ids = data.get("edit_selected_materials", [])
    selected = [m for m in materials if m["id"] in selected_ids]
    certs_result = data.get("edit_certs_result", {})
    mat_str = format_materials_with_certs(selected, certs_result) or "—"
    text = (
        f"✏️ Редактирование акта\n\n"
        f"📝 Наименование: {data.get('edit_work_name') or '—'}\n"
        f"🔨 Тип: {data.get('edit_work_type_name') or '—'}\n"
        f"📍 Позиция: {data.get('edit_position_number') or '—'}\n"
        f"🔢 Номер акта: {data.get('edit_act_number') or '—'}\n"
        f"📅 Дата акта: {data.get('edit_act_date_raw') or '—'}\n"
        f"📅 Начало: {data.get('edit_start_date_raw') or '—'}\n"
        f"📅 Окончание: {data.get('edit_end_date_raw') or '—'}\n"
        f"📄 Листы: {data.get('edit_sheets') or '—'}\n"
        f"📂 Раздел: {data.get('edit_section') or '—'}\n"
        f"📐 Шифр: {data.get('edit_cipher') or '—'}\n"
        f"📦 Материалы: {mat_str[:200]}"
    )
    await message.answer(text, reply_markup=edit_act_menu_kb(act_id))


@router.callback_query(F.data.startswith("ea_back:"))
async def cb_ea_back(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _edit_send_menu(call.message, state)


@router.callback_query(EditAct.menu, F.data.startswith("ea_name:"))
async def cb_ea_name(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    await state.set_state(EditAct.entering_work_name)
    await call.message.answer(
        f"📝 Текущее: «{data.get('edit_work_name') or '—'}»\n\nНовое:",
        reply_markup=edit_act_menu_back_kb(data["edit_act_id"]),
    )


@router.message(EditAct.entering_work_name)
async def msg_ea_work_name(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 400:
        data = await state.get_data()
        await message.answer("⚠️ 1-400 символов.",
                             reply_markup=edit_act_menu_back_kb(data["edit_act_id"]))
        return
    await state.update_data(edit_work_name=text)
    await _edit_send_menu(message, state)


@router.callback_query(EditAct.menu, F.data.startswith("ea_num:"))
async def cb_ea_num(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    await state.set_state(EditAct.entering_act_number)
    await call.message.answer(
        f"🔢 Текущий: {data.get('edit_act_number')}\n\nНовый:",
        reply_markup=edit_act_menu_back_kb(data["edit_act_id"]),
    )


@router.message(EditAct.entering_act_number)
async def msg_ea_act_number(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()
    if not text or len(text) > 10:
        await message.answer("⚠️ до 10 символов.",
                             reply_markup=edit_act_menu_back_kb(data["edit_act_id"]))
        return
    if act_number_exists(
        data["edit_object_id"], text, exclude_act_id=data["edit_act_id"]
    ):
        await message.answer(
            f"⚠️ Акт №{text} уже существует у этого объекта. "
            "Введите другой номер.",
            reply_markup=edit_act_menu_back_kb(data["edit_act_id"]),
        )
        return
    await state.update_data(edit_act_number=text)
    await _edit_send_menu(message, state)


@router.callback_query(EditAct.menu, F.data.startswith("ea_dates:"))
async def cb_ea_dates(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    await state.set_state(EditAct.entering_start_date)
    await call.message.answer(
        f"📅 Текущие:\nНачало: {data.get('edit_start_date_raw')}\n"
        f"Окончание: {data.get('edit_end_date_raw')}\n\n"
        f"Новая дата начала (ДД.ММ.ГГГГ):",
        reply_markup=edit_act_menu_back_kb(data["edit_act_id"]),
    )


@router.message(EditAct.entering_start_date)
async def msg_ea_start_date(message: Message, state: FSMContext):
    try:
        d = parse_date(message.text or "")
    except ValueError as e:
        data = await state.get_data()
        await message.answer(f"⚠️ {e}",
                             reply_markup=edit_act_menu_back_kb(data["edit_act_id"]))
        return
    await state.update_data(edit_start_date=d)
    data = await state.get_data()
    await state.set_state(EditAct.entering_end_date)
    await message.answer("📅 Дата окончания:",
                         reply_markup=edit_act_menu_back_kb(data["edit_act_id"]))


@router.message(EditAct.entering_end_date)
async def msg_ea_end_date(message: Message, state: FSMContext):
    try:
        d = parse_date(message.text or "")
    except ValueError as e:
        data = await state.get_data()
        await message.answer(f"⚠️ {e}",
                             reply_markup=edit_act_menu_back_kb(data["edit_act_id"]))
        return
    await state.update_data(edit_end_date=d)
    data = await state.get_data()
    await state.set_state(EditAct.entering_act_date)
    await message.answer(
        f"📅 Дата акта. Если совпадает ({d['full']}) — «—»:",
        reply_markup=edit_act_menu_back_kb(data["edit_act_id"]),
    )


@router.message(EditAct.entering_act_date)
async def msg_ea_act_date(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()
    if text in ("—", "-", ""):
        act_date = data.get("edit_end_date")
    else:
        try:
            act_date = parse_date(text)
        except ValueError as e:
            await message.answer(f"⚠️ {e}",
                                 reply_markup=edit_act_menu_back_kb(data["edit_act_id"]))
            return
    await state.update_data(
        edit_act_date=act_date,
        edit_act_date_raw=act_date["full"],
        edit_start_date_raw=data["edit_start_date"]["full"],
        edit_end_date_raw=data["edit_end_date"]["full"],
    )
    await _edit_send_menu(message, state)


@router.callback_query(EditAct.menu, F.data.startswith("ea_sheets:"))
async def cb_ea_sheets(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    await state.set_state(EditAct.entering_sheets)
    await call.message.answer(
        f"📄 Текущие листы: {data.get('edit_sheets') or '—'}\n\nНовые:",
        reply_markup=edit_act_menu_back_kb(data["edit_act_id"]),
    )


@router.message(EditAct.entering_sheets)
async def msg_ea_sheets(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()
    if not text or len(text) > 60:
        await message.answer("⚠️ 1-60 символов.",
                             reply_markup=edit_act_menu_back_kb(data["edit_act_id"]))
        return
    await state.update_data(edit_sheets=text)
    await _edit_send_menu(message, state)


@router.callback_query(EditAct.menu, F.data.startswith("ea_section:"))
async def cb_ea_section(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    sections = get_sections_for_position(
        data["edit_object_id"], data.get("edit_position_number") or "")
    if not sections:
        await call.message.answer("⚠️ У позиции нет разделов.")
        return
    await state.set_state(EditAct.choosing_section)
    await call.message.answer(
        f"📂 Текущий: {data.get('edit_section') or '—'}\n\nНовый:",
        reply_markup=sections_kb(sections, back_cb="ea_back:", del_cb=None),
    )


@router.callback_query(EditAct.choosing_section, F.data.startswith("sec:"))
async def cb_ea_choose_section(call: CallbackQuery, state: FSMContext):
    section = call.data.split(":", 1)[1]
    await call.answer()
    data = await state.get_data()
    rec = get_drawing(data["edit_object_id"],
                      data.get("edit_position_number") or "", section)
    await state.update_data(
        edit_section=section,
        edit_cipher=rec["cipher"] if rec else "",
    )
    await _edit_send_menu(call.message, state)


@router.callback_query(EditAct.menu, F.data.startswith("ea_materials:"))
async def cb_ea_materials(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    await state.update_data(object_id=data["edit_object_id"])
    await show_material_categories(call.message, state, "edit")


@router.callback_query(EditAct.choosing_materials, F.data == "eaback_menu")
async def cb_ea_back_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    await state.update_data(object_id=data["edit_object_id"])
    await _edit_send_menu(call.message, state)


async def _cert_finish_edit(message, state: FSMContext):
    data = await state.get_data()
    certs_result = data.get("certs_result", {})
    await state.update_data(edit_certs_result=certs_result, certs_result={})
    await _edit_send_menu(message, state)


@router.callback_query(EditAct.menu, F.data.startswith("ea_save:"))
async def cb_ea_save(call: CallbackQuery, state: FSMContext):
    await call.answer("Пересобираю акт…")
    data = await state.get_data()
    act_id = data["edit_act_id"]
    original_act = get_act(act_id) or {}
    object_id = data["edit_object_id"]
    position_id = data.get("edit_position_id")
    position_number = data.get("edit_position_number") or ""
    work_type_name = data.get("edit_work_type_name", "")
    work_name = data.get("edit_work_name", "")
    act_number = data.get("edit_act_number", "")
    sheets = data.get("edit_sheets", "")
    section = data.get("edit_section", "")
    cipher = data.get("edit_cipher", "")
    act_date = data.get("edit_act_date") or _parse_date_or_none(data.get("edit_act_date_raw"))
    start_date = data.get("edit_start_date") or _parse_date_or_none(data.get("edit_start_date_raw"))
    end_date = data.get("edit_end_date") or _parse_date_or_none(data.get("edit_end_date_raw"))
    if not (act_date and start_date and end_date):
        await call.message.answer("⚠️ Некорректные даты. Отредактируйте вручную.")
        return
    if work_type_name and work_name:
        if position_number:
            full_work = f"{work_type_name} {work_name} позиция №{position_number}"
        else:
            full_work = f"{work_type_name} {work_name}"
    else:
        full_work = original_act.get("work_full") or ""
    materials = get_materials_for_object(object_id)
    selected_ids = data.get("edit_selected_materials", [])
    selected = [m for m in materials if m["id"] in selected_ids]
    certs_result = data.get("edit_certs_result", {})
    materials_str = format_materials_with_certs(selected, certs_result)
    materials_json = materials_to_json(selected, certs_result)
    obj = get_object(object_id)
    author_sup = is_author_supervision(object_id, work_type_name)
    template_data = build_template_data(
        obj, full_work, sheets, cipher or "—",
        start_date, end_date, act_date,
        materials_str, act_number,
        author_supervision=author_sup,
    )
    old_path = resolve_path(data["edit_file_path"]) if data.get("edit_file_path") else None
    new_path = ACTS_DIR / act_filename(
        act_number,
        work_type_name or original_act.get("work_type_name") or "",
        work_name or original_act.get("work_name") or "",
        position_number or original_act.get("position_number") or "",
    )
    if old_path and old_path.exists() and old_path != new_path:
        try:
            old_path.replace(old_path.with_name(old_path.name + ".bak"))
        except OSError as e:
            print(f"⚠️ Не удалось сделать .bak: {e}")
    try:
        new_path = build_act(template_data, out_path=new_path)
    except Exception as e:
        traceback.print_exc()
        await call.message.answer(f"❌ Ошибка генерации: {e}")
        return
    update_act(
        act_id, act_number=act_number, act_date=act_date["full"],
        start_date=start_date["full"], end_date=end_date["full"],
        work_full=full_work, work_name=work_name,
        file_path=to_stored_path(new_path),
        sheets=sheets, section=section, cipher=cipher,
        materials_data=materials_json,
    )
    await call.message.answer(f"✅ Акт №{act_number} пересобран!")
    try:
        file = FSInputFile(new_path)
        await call.message.answer_document(
            file, caption=f"Обновлённый акт №{act_number}")
    except Exception as e:
        await call.message.answer(f"⚠️ Ошибка отправки: {e}")
    await state.clear()