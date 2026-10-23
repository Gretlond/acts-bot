# handlers_certs.py
"""
Сертификаты на материалы — общий flow для NewAct / CycleRun / EditAct.
Перед вводом номера спрашиваем тип документа.
"""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from db import (
    get_materials_for_object,
    get_certificates_for_material, add_certificate,
)
from states import NewAct, CycleRun, EditAct
from keyboards import (
    cert_choice_kb, cert_save_ask_kb, cancel_kb,
    step_with_back_and_delete_kb,
    cert_type_choice_kb,
)
from utils import parse_date, cert_label, cert_type_label


router = Router()


CERT_CHOOSING_STATES = (
    NewAct.choosing_cert.state,
    CycleRun.item_cert_choosing.state,
    EditAct.choosing_cert.state,
)
CERT_DOC_TYPE_STATES = (
    NewAct.entering_cert_doc_type.state,
    CycleRun.item_cert_doc_type.state,
    EditAct.entering_cert_doc_type.state,
)
CERT_DOC_TYPE_CUSTOM_STATES = (
    NewAct.entering_cert_doc_type_custom.state,
    CycleRun.item_cert_doc_type_custom.state,
    EditAct.entering_cert_doc_type_custom.state,
)
CERT_NUMBER_STATES = (
    NewAct.entering_cert_number.state,
    CycleRun.item_cert_number.state,
    EditAct.entering_cert_number.state,
)
CERT_DATE_STATES = (
    NewAct.entering_cert_date.state,
    CycleRun.item_cert_date.state,
    EditAct.entering_cert_date.state,
)
CERT_SAVE_STATES = (
    NewAct.asking_save_cert.state,
    CycleRun.item_cert_asking_save.state,
    EditAct.asking_save_cert.state,
)


def _cert_flow_kind(current_state):
    if not current_state:
        return None
    if current_state.startswith("NewAct:"):
        return "newact"
    if current_state.startswith("CycleRun:"):
        return "cycle"
    if current_state.startswith("EditAct:"):
        return "edit"
    return None


def _doc_type_state(kind):
    if kind == "newact":
        return NewAct.entering_cert_doc_type
    if kind == "cycle":
        return CycleRun.item_cert_doc_type
    return EditAct.entering_cert_doc_type


def _doc_type_custom_state(kind):
    if kind == "newact":
        return NewAct.entering_cert_doc_type_custom
    if kind == "cycle":
        return CycleRun.item_cert_doc_type_custom
    return EditAct.entering_cert_doc_type_custom


def _number_state(kind):
    if kind == "newact":
        return NewAct.entering_cert_number
    if kind == "cycle":
        return CycleRun.item_cert_number
    return EditAct.entering_cert_number


def _date_state(kind):
    if kind == "newact":
        return NewAct.entering_cert_date
    if kind == "cycle":
        return CycleRun.item_cert_date
    return EditAct.entering_cert_date


def _save_state(kind):
    if kind == "newact":
        return NewAct.asking_save_cert
    if kind == "cycle":
        return CycleRun.item_cert_asking_save
    return EditAct.asking_save_cert


def _choosing_state(kind):
    if kind == "newact":
        return NewAct.choosing_cert
    if kind == "cycle":
        return CycleRun.item_cert_choosing
    return EditAct.choosing_cert


async def _start_cert_flow(message_or_call, state: FSMContext,
                           selected_ids, kind: str):
    if not selected_ids:
        await _cert_finish(message_or_call, state, kind)
        return
    await state.update_data(cert_queue=list(selected_ids),
                            cert_index=0, certs_result={})
    await _cert_next(message_or_call, state, kind)


async def _cert_next(message_or_call, state: FSMContext, kind: str):
    data = await state.get_data()
    queue = data.get("cert_queue", [])
    idx = data.get("cert_index", 0)
    if idx >= len(queue):
        await _cert_finish(message_or_call, state, kind)
        return
    material_id = queue[idx]
    materials = get_materials_for_object(data.get("object_id"))
    material = next((m for m in materials if m["id"] == material_id), None)
    if not material:
        await state.update_data(cert_index=idx + 1)
        await _cert_next(message_or_call, state, kind)
        return
    saved = get_certificates_for_material(material_id, limit=5)
    text = (f"📜 Сертификат для материала:\n«{material['name']}»\n"
            f"({idx + 1}/{len(queue)})")
    if saved:
        text += "\n\nВыберите сохранённый или введите новый:"
    await state.set_state(_choosing_state(kind))
    target = message_or_call.message if isinstance(message_or_call, CallbackQuery) \
        else message_or_call
    await target.answer(text, reply_markup=cert_choice_kb(saved))


async def _cert_finish(message_or_call, state: FSMContext, kind: str):
    target = message_or_call.message if isinstance(message_or_call, CallbackQuery) \
        else message_or_call
    data = await state.get_data()

    if data.get("_cert_return_to_materials"):
        from handlers_materials import return_to_materials_list
        await state.update_data(_cert_return_to_materials=False)
        await return_to_materials_list(target, state)
        return

    if kind == "newact":
        if not data.get("start_date") or not data.get("end_date"):
            await state.set_state(NewAct.entering_start_date)
            await target.answer("📅 Дата начала работ (ДД.ММ.ГГГГ):",
                                reply_markup=step_with_back_and_delete_kb())
            return
        from handlers import _show_final_preview
        await _show_final_preview(target, state)
    elif kind == "cycle":
        from handlers_cycles import _show_item_preview_msg
        await _show_item_preview_msg(target, state)
    else:
        from handlers_my_acts import _cert_finish_edit
        await _cert_finish_edit(target, state)


@router.callback_query(F.data.startswith("cert_pick:"))
async def cb_cert_pick(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current not in CERT_CHOOSING_STATES:
        await call.answer()
        return
    kind = _cert_flow_kind(current)
    cert_id = int(call.data.split(":")[1])
    data = await state.get_data()
    queue = data.get("cert_queue", [])
    idx = data.get("cert_index", 0)
    if idx >= len(queue):
        await call.answer()
        return
    material_id = queue[idx]
    saved = get_certificates_for_material(material_id, limit=50)
    cert = next((c for c in saved if c["id"] == cert_id), None)
    if not cert:
        await call.answer("Сертификат не найден", show_alert=True)
        return
    certs_result = data.get("certs_result", {})
    certs_result[str(material_id)] = cert_label(cert)
    await state.update_data(certs_result=certs_result, cert_index=idx + 1)
    await call.answer("✅ Взяли сохранённый")
    await _cert_next(call, state, kind)


@router.callback_query(F.data == "cert_new")
async def cb_cert_new(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current not in CERT_CHOOSING_STATES:
        await call.answer()
        return
    kind = _cert_flow_kind(current)
    await call.answer()
    data = await state.get_data()
    queue = data.get("cert_queue", [])
    idx = data.get("cert_index", 0)
    material_id = queue[idx]
    materials = get_materials_for_object(data.get("object_id"))
    material = next((m for m in materials if m["id"] == material_id), None)
    await state.update_data(
        _cert_current_mat=material_id,
        _cert_current_doc_type=None,
    )
    await state.set_state(_doc_type_state(kind))
    await call.message.answer(
        f"📜 Материал: «{material['name'] if material else '—'}»\n\n"
        f"Какой документ добавить?",
        reply_markup=cert_type_choice_kb(),
    )


@router.callback_query(F.data == "cert_skip")
async def cb_cert_skip(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current not in CERT_CHOOSING_STATES:
        await call.answer()
        return
    kind = _cert_flow_kind(current)
    await call.answer("Пропущено")
    data = await state.get_data()
    idx = data.get("cert_index", 0)
    await state.update_data(cert_index=idx + 1)
    await _cert_next(call, state, kind)


@router.callback_query(F.data.startswith("cert_type:"))
async def cb_cert_type(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current not in CERT_DOC_TYPE_STATES:
        await call.answer()
        return
    kind = _cert_flow_kind(current)
    choice = call.data.split(":", 1)[1]

    if choice == "custom":
        await call.answer()
        await state.set_state(_doc_type_custom_state(kind))
        await call.message.answer(
            "✏️ Введите название документа "
            "(например: «удостоверение качества»):",
            reply_markup=cancel_kb(),
        )
        return

    doc_type = None if choice == "skip" else choice
    await state.update_data(_cert_current_doc_type=doc_type)
    await call.answer()

    data = await state.get_data()
    material_id = data.get("_cert_current_mat")
    materials = get_materials_for_object(data.get("object_id"))
    material = next((m for m in materials if m["id"] == material_id), None)

    await state.set_state(_number_state(kind))
    await call.message.answer(
        f"📜 Материал: «{material['name'] if material else '—'}»\n\n"
        f"Введите номер документа (например: 1234):",
        reply_markup=cancel_kb(),
    )


@router.message(NewAct.entering_cert_doc_type_custom)
@router.message(CycleRun.item_cert_doc_type_custom)
@router.message(EditAct.entering_cert_doc_type_custom)
async def msg_cert_doc_type_custom(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 100:
        await message.answer("⚠️ 1-100 символов.", reply_markup=cancel_kb())
        return
    current = await state.get_state()
    kind = _cert_flow_kind(current)
    await state.update_data(_cert_current_doc_type=text)
    data = await state.get_data()
    material_id = data.get("_cert_current_mat")
    materials = get_materials_for_object(data.get("object_id"))
    material = next((m for m in materials if m["id"] == material_id), None)
    await state.set_state(_number_state(kind))
    await message.answer(
        f"📜 Материал: «{material['name'] if material else '—'}»\n\n"
        f"Введите номер документа (например: 1234):",
        reply_markup=cancel_kb(),
    )


@router.message(NewAct.entering_cert_number)
@router.message(CycleRun.item_cert_number)
@router.message(EditAct.entering_cert_number)
async def msg_cert_number(message: Message, state: FSMContext):
    current = await state.get_state()
    kind = _cert_flow_kind(current)
    text = (message.text or "").strip()
    if not text or len(text) > 100:
        await message.answer("⚠️ 1-100 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(_cert_current_number=text)
    await state.set_state(_date_state(kind))
    await message.answer("📅 Дата документа (ДД.ММ.ГГГГ)\nИли «—»:",
                         reply_markup=cancel_kb())


@router.message(NewAct.entering_cert_date)
@router.message(CycleRun.item_cert_date)
@router.message(EditAct.entering_cert_date)
async def msg_cert_date(message: Message, state: FSMContext):
    current = await state.get_state()
    kind = _cert_flow_kind(current)
    text = (message.text or "").strip()
    if text in ("—", "-", ""):
        date_str = ""
    else:
        try:
            d = parse_date(text)
            date_str = f"{d['day']}.{d['month_num']}.{d['year']}"
        except ValueError as e:
            await message.answer(f"⚠️ {e}.", reply_markup=cancel_kb())
            return
    await state.update_data(_cert_current_date=date_str)
    await state.set_state(_save_state(kind))
    await message.answer("💾 Сохранить документ для будущих актов?",
                         reply_markup=cert_save_ask_kb())


@router.callback_query(F.data == "cert_save_yes")
async def cb_cert_save_yes(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current not in CERT_SAVE_STATES:
        await call.answer()
        return
    kind = _cert_flow_kind(current)
    await call.answer()
    await _save_and_next_cert(call, state, save=True, kind=kind)


@router.callback_query(F.data == "cert_save_no")
async def cb_cert_save_no(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current not in CERT_SAVE_STATES:
        await call.answer()
        return
    kind = _cert_flow_kind(current)
    await call.answer()
    await _save_and_next_cert(call, state, save=False, kind=kind)


async def _save_and_next_cert(call: CallbackQuery, state: FSMContext,
                              save: bool, kind: str):
    data = await state.get_data()
    queue = data.get("cert_queue", [])
    idx = data.get("cert_index", 0)
    if idx >= len(queue):
        await _cert_finish(call, state, kind)
        return
    material_id = queue[idx]
    number = data.get("_cert_current_number", "")
    date_str = data.get("_cert_current_date", "")
    doc_type = data.get("_cert_current_doc_type")

    if save:
        try:
            add_certificate(material_id, number, date_from=date_str,
                            doc_type=doc_type)
        except Exception as e:
            print(f"⚠️ Не сохранилось: {e}")

    if doc_type:
        type_label = cert_type_label(doc_type)
    else:
        type_label = "сертификат"
    cert_str = f"{type_label} №{number}"
    if date_str:
        cert_str += f" от {date_str}"

    certs_result = data.get("certs_result", {})
    certs_result[str(material_id)] = cert_str
    await state.update_data(
        certs_result=certs_result,
        cert_index=idx + 1,
        _cert_current_doc_type=None,
    )
    await _cert_next(call, state, kind)