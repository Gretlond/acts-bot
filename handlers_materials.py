# handlers_materials.py
"""
Общие хендлеры для работы с материалами из акта (NewAct / CycleRun / EditAct):
  • matcat_pick:{id} — открыть категорию
  • matcat_back      — вернуться к категориям
  • mat:{id}         — toggle материала
  • mat_done         — завершить выбор → сертификаты или превью
  • mat_add_new      — создать материал «на лету»
  • добавление документа к новому материалу

Используется всеми тремя контекстами.
"""

import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from db import (
    get_materials_for_object,
    get_material,
    add_material,
    get_all_material_categories,
)
from states import MaterialFromAct, NewAct, CycleRun, EditAct
from keyboards import (
    cancel_kb,
    material_add_category_kb,
    material_add_doc_ask_kb,
)
from materials_view import (
    show_material_categories,
    show_materials_in_category,
    selected_key,
    work_type_key,
    get_selected,
    get_work_type,
)
from utils import split_materials_by_work_type

router = Router()
logger = logging.getLogger(__name__)


def _ctx_from_state(current):
    if not current:
        return None
    if current.startswith("NewAct:"):
        return "newact"
    if current.startswith("CycleRun:"):
        return "cycle"
    if current.startswith("EditAct:"):
        return "edit"
    return None


# =====================================================================
#  КАТЕГОРИИ → МАТЕРИАЛЫ
# =====================================================================


@router.callback_query(F.data.startswith("matcat_pick:"))
async def cb_matcat_pick(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    ctx = _ctx_from_state(current)
    if not ctx:
        await call.answer("Сейчас недоступно", show_alert=True)
        return
    raw = call.data.split(":", 1)[1]
    cat_id = int(raw) if raw else 0
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    await show_materials_in_category(call.message, state, ctx, cat_id)


@router.callback_query(F.data == "matcat_back")
async def cb_matcat_back(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    ctx = _ctx_from_state(current)
    if not ctx:
        await call.answer()
        return
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    await show_material_categories(call.message, state, ctx)


# =====================================================================
#  TOGGLE МАТЕРИАЛА
# =====================================================================


@router.callback_query(F.data.startswith("mat:"))
async def cb_toggle_material(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    ctx = _ctx_from_state(current)
    if not ctx:
        await call.answer()
        return
    try:
        mat_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer()
        return

    data = await state.get_data()
    skey = selected_key(ctx)
    selected = list(data.get(skey, []) or [])
    if mat_id in selected:
        selected.remove(mat_id)
    else:
        selected.append(mat_id)
    await state.update_data(**{skey: selected})

    # перерисовка текущей категории
    cat_id = data.get("_mat_current_cat")
    object_id = data.get("object_id")
    work_type_name = get_work_type(data, ctx)

    if cat_id == 0:
        materials = get_materials_for_object(object_id, work_type=work_type_name)
    elif cat_id in (None, -1):
        materials = [
            m
            for m in get_materials_for_object(object_id, work_type=work_type_name)
            if not m.get("category_id")
        ]
    else:
        materials = get_materials_for_object(
            object_id, work_type=work_type_name, category_id=cat_id
        )

    matched = split_materials_by_work_type(materials, work_type_name)

    from keyboards import materials_in_category_kb

    try:
        await call.message.edit_reply_markup(
            reply_markup=materials_in_category_kb(materials, selected, matched)
        )
    except Exception as e:
        logger.warning("Не удалось обновить клавиатуру материалов: %s", e)
    await call.answer()


# =====================================================================
#  ЗАВЕРШЕНИЕ ВЫБОРА
# =====================================================================


@router.callback_query(F.data == "mat_done")
async def cb_materials_done(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    ctx = _ctx_from_state(current)
    if not ctx:
        await call.answer()
        return
    await call.answer()

    data = await state.get_data()
    selected_ids = list(data.get(selected_key(ctx), []) or [])

    if ctx == "newact":
        if not selected_ids:
            # без материалов — либо к датам, либо в превью
            if data.get("_edit_mode"):
                await state.update_data(_edit_mode=False)
                from handlers import _show_final_preview

                await _show_final_preview(call.message, state)
                return
            if not data.get("start_date") or not data.get("end_date"):
                await state.set_state(NewAct.entering_start_date)
                from keyboards import step_with_back_and_delete_kb

                await call.message.answer(
                    "📅 Дата начала работ (ДД.ММ.ГГГГ):",
                    reply_markup=step_with_back_and_delete_kb(),
                )
                return
            from handlers import _show_final_preview

            await _show_final_preview(call.message, state)
            return
        await state.update_data(certs_result={})
        from handlers_certs import _start_cert_flow

        await _start_cert_flow(call.message, state, selected_ids, kind="newact")

    elif ctx == "cycle":
        if not selected_ids:
            from handlers_cycles import _show_item_preview_msg

            await _show_item_preview_msg(call.message, state)
            return
        await state.update_data(certs_result={})
        from handlers_certs import _start_cert_flow

        await _start_cert_flow(call.message, state, selected_ids, kind="cycle")

    elif ctx == "edit":
        await state.update_data(edit_certs_result={})
        if not selected_ids:
            from handlers_my_acts import _edit_send_menu

            await _edit_send_menu(call.message, state)
            return
        # подменяем object_id для cert-flow
        await state.update_data(
            object_id=data.get("edit_object_id"),
            cert_queue=list(selected_ids),
            cert_index=0,
            certs_result={},
        )
        from handlers_certs import _cert_next

        await state.set_state(EditAct.choosing_cert)
        await _cert_next(call, state, kind="edit")


# =====================================================================
#  ДОБАВЛЕНИЕ НОВОГО МАТЕРИАЛА «НА ЛЕТУ»
# =====================================================================


@router.callback_query(F.data == "mat_add_new")
async def cb_mat_add_new(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    ctx = _ctx_from_state(current)
    if not ctx:
        await call.answer("Сейчас недоступно", show_alert=True)
        return
    await call.answer()
    await state.update_data(
        _mat_add_ctx=ctx,
        _mat_add_name=None,
        _mat_add_qdoc=None,
        _mat_add_work_types=None,
        _mat_add_category_id=None,
        _mat_add_new_id=None,
    )
    await state.set_state(MaterialFromAct.entering_name)
    await call.message.answer(
        "➕ Новый материал\n\n📝 Название материала:",
        reply_markup=cancel_kb(),
    )


@router.message(MaterialFromAct.entering_name)
async def msg_mat_new_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 200:
        await message.answer("⚠️ 1-200 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(_mat_add_name=name)
    await state.set_state(MaterialFromAct.entering_qdoc)
    await message.answer(
        "📄 Нормативный документ (ГОСТ/ТУ/СТБ). Или «—»:",
        reply_markup=cancel_kb(),
    )


@router.message(MaterialFromAct.entering_qdoc)
async def msg_mat_new_qdoc(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    qdoc = "" if text in ("—", "-", "") else text[:200]
    await state.update_data(_mat_add_qdoc=qdoc)
    await state.set_state(MaterialFromAct.entering_work_types)
    await message.answer(
        "🔨 Типы работ (через `|`, например «Бетонирование|Армирование»).\n" "Или «—»:",
        reply_markup=cancel_kb(),
    )


@router.message(MaterialFromAct.entering_work_types)
async def msg_mat_new_work_types(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    wt = "" if text in ("—", "-", "") else text[:200]
    await state.update_data(_mat_add_work_types=wt)
    categories = get_all_material_categories()
    await state.set_state(MaterialFromAct.choosing_category)
    if not categories:
        await _finish_material_create(message, state)
        return
    await message.answer(
        "📁 Выбери категорию:",
        reply_markup=material_add_category_kb(
            categories,
            back_cb="mat_add_back_to_list",
            cb_prefix="mat_add_cat",
        ),
    )


@router.callback_query(MaterialFromAct.choosing_category, F.data.startswith("mat_add_cat:"))
async def cb_mat_add_cat(call: CallbackQuery, state: FSMContext):
    raw = call.data.split(":", 1)[1]
    cat_id = int(raw) if raw else 0
    await call.answer()
    await state.update_data(_mat_add_category_id=cat_id or None)
    await _finish_material_create(call.message, state)


@router.callback_query(F.data == "mat_add_back_to_list")
async def cb_mat_add_back_to_list(call: CallbackQuery, state: FSMContext):
    await call.answer("Отменено")
    data = await state.get_data()
    ctx = data.get("_mat_add_ctx")
    if not ctx:
        await state.clear()
        return
    await show_material_categories(call.message, state, ctx)


async def _finish_material_create(message, state: FSMContext):
    data = await state.get_data()
    object_id = data.get("object_id")
    name = data.get("_mat_add_name")
    qdoc = data.get("_mat_add_qdoc") or ""
    work_types = data.get("_mat_add_work_types") or ""
    category_id = data.get("_mat_add_category_id")
    ctx = data.get("_mat_add_ctx")

    new_id = add_material(
        name=name,
        quality_doc=qdoc,
        object_id=object_id,
        work_types=work_types,
        category_id=category_id,
    )
    await state.update_data(_mat_add_new_id=new_id)

    # автовыбор в текущем акте
    if ctx:
        skey = selected_key(ctx)
        selected = list(data.get(skey, []) or [])
        if new_id not in selected:
            selected.append(new_id)
        await state.update_data(**{skey: selected})

    await state.set_state(MaterialFromAct.asking_add_doc)
    await message.answer(
        f"✅ Материал «{name}» добавлен и выбран.\n\n"
        f"📜 Добавить документ на этот материал сейчас?",
        reply_markup=material_add_doc_ask_kb(),
    )


@router.callback_query(MaterialFromAct.asking_add_doc, F.data == "mat_add_doc_no")
async def cb_mat_add_doc_no(call: CallbackQuery, state: FSMContext):
    await call.answer("Ок, потом")
    data = await state.get_data()
    ctx = data.get("_mat_add_ctx")
    if not ctx:
        await state.clear()
        return
    await show_material_categories(call.message, state, ctx)


@router.callback_query(MaterialFromAct.asking_add_doc, F.data == "mat_add_doc_yes")
async def cb_mat_add_doc_yes(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ctx = data.get("_mat_add_ctx")
    new_id = data.get("_mat_add_new_id")
    if not new_id or not ctx:
        await show_material_categories(call.message, state, ctx or "newact")
        return

    # готовим cert-flow на один материал
    # сохраняем флаг «вернуться к материалам»
    # от него зависит ветка в _cert_finish
    prev_certs = data.get("certs_result") or {}
    await state.update_data(
        cert_queue=[new_id],
        cert_index=0,
        certs_result=prev_certs,
        _cert_return_to_materials=True,
    )
    from handlers_certs import _cert_next

    kind = ctx  # newact / cycle / edit
    await _cert_next(call, state, kind=kind)
