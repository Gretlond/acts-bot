# project_handlers.py
"""
Setup-визард, меню «🏗 Проект», категории материалов, CRUD материалов
и сертификатов с типами документов.
Подключается ПЕРВЫМ роутером (см. bot.py).
"""
import traceback

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import (
    get_all_objects, get_object, add_object, update_object,
    get_all_work_types,
    get_object_author_supervision, add_object_author_supervision,
    remove_object_author_supervision,
    get_materials_for_object, get_all_materials_with_categories,
    get_material, add_material, update_material, delete_material,
    move_material_to_category,
    get_all_material_categories, get_material_category,
    add_material_category, update_material_category,
    delete_material_category, get_categories_with_counts,
    count_materials_in_category,
    get_certificates_for_material, add_certificate, delete_certificate,
    get_conn,
)
from keyboards import (
    main_menu_kb, cancel_kb,
    setup_confirm_scan_kb, setup_skip_kb, setup_works_kb,
    project_menu_kb, project_person_kb,
    project_author_works_kb,
    material_categories_kb,
    project_materials_kb, material_card_ext_kb,
    move_material_category_kb, material_add_category_kb,
    project_certs_kb, cert_type_choice_kb,
)
from states import ProjectSetup, ProjectEdit
from sync import scan_only, apply_scan


router = Router()


# =====================================================================
#  УТИЛИТЫ
# =====================================================================

def _make_short_name(full_name: str) -> str:
    """'Иванова Ивана Ивановича' → 'Иванов И.И.'"""
    if not full_name:
        return ""
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} {parts[1][0]}."
    return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."


def _current_object():
    objs = get_all_objects()
    return objs[0] if objs else None


async def _show_project_menu(message, state: FSMContext):
    obj = _current_object()
    if not obj:
        await message.answer("⚠️ Объект не настроен.", reply_markup=main_menu_kb())
        return
    await state.set_state(ProjectEdit.menu)
    text = (
        f"🏗 Проект:\n"
        f"  • Объект: {obj['name'][:80]}\n"
        f"  • Генподрядчик: {obj.get('gen_contractor') or '—'}\n"
        f"  • Субподрядчик: {obj.get('subgen_firm') or '—'}\n"
        f"  • Госстройнадзор: {obj.get('tech_short') or '—'}\n"
        f"  • Авторский надзор: {obj.get('author_short') or '—'}\n"
        f"  • Проектировщик: {obj.get('project_firm') or '—'} "
        f"({obj.get('project_date') or '—'})"
    )
    await message.answer(text, reply_markup=project_menu_kb())


def _category_view_kb(category_id, materials):
    """Список материалов в категории + управление категорией."""
    builder = InlineKeyboardBuilder()
    for m in materials:
        text = m["name"][:55]
        if len(m["name"]) > 55:
            text += "…"
        builder.button(text=text, callback_data=f"pmat:view:{m['id']}")
    if category_id is not None and category_id != -1:
        builder.button(text="➕ Добавить в эту категорию",
                       callback_data=f"pmat:add_in_cat:{category_id}")
        builder.button(text="📝 Переименовать категорию",
                       callback_data=f"pmat:cat_rename:{category_id}")
        builder.button(text="🗑 Удалить категорию",
                       callback_data=f"pmat:cat_del:{category_id}")
    else:
        builder.button(text="➕ Добавить в «Без категории»",
                       callback_data="pmat:add_in_cat:0")
    builder.button(text="🔙 К категориям", callback_data="pmat:list")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  /start
# =====================================================================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    obj = _current_object()
    if not obj:
        await state.set_state(ProjectSetup.waiting_zip)
        await message.answer(
            "👋 Привет! Объект ещё не настроен.\n\n"
            "📦 Залей папку `project/` на сервер (SFTP или вручную), "
            "затем отправь /scan_server — я найду позиции и чертежи.",
            reply_markup=cancel_kb(),
        )
        return
    await message.answer(
        f"👋 Привет!\n\nОбъект:\n{obj['name'][:100]}\n\nВыбери действие:",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("scan_server"))
async def cmd_scan_server(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔍 Сканирую папку project/…")
    try:
        result = scan_only()
    except Exception as e:
        traceback.print_exc()
        await message.answer(f"❌ Ошибка сканирования: {e}")
        return

    n_pos = len(result["positions"])
    n_drw = len(result["drawings"])
    n_folders = result["folders_count"]

    if n_pos == 0 and n_drw == 0:
        await message.answer(
            "⚠️ Ничего не найдено.\n"
            "Проверь, что папка project/ лежит рядом с ботом "
            "и содержит PDF."
        )
        return

    await state.update_data(
        scan_positions=result["positions"],
        scan_drawings=result["drawings"],
    )
    await state.set_state(ProjectSetup.showing_scan)

    text = (
        f"📂 Найдено:\n"
        f"  • папок: {n_folders}\n"
        f"  • позиций: {n_pos}\n"
        f"  • чертежей: {n_drw}\n\n"
    )
    if result["skipped"]:
        text += "Пропущены папки:\n"
        for s in result["skipped"][:5]:
            text += f"  • {s}\n"
        text += "\n"
    text += "Проверь, что все файлы на месте."
    await message.answer(text, reply_markup=setup_confirm_scan_kb())


@router.callback_query(ProjectSetup.showing_scan, F.data == "setup:scan_again")
async def cb_scan_again(call: CallbackQuery, state: FSMContext):
    await call.answer()
    try:
        result = scan_only()
    except Exception as e:
        await call.message.edit_text(f"❌ Ошибка: {e}")
        return
    await state.update_data(
        scan_positions=result["positions"],
        scan_drawings=result["drawings"],
    )
    await call.message.edit_text(
        f"📂 Пересканировано: позиций {len(result['positions'])}, "
        f"чертежей {len(result['drawings'])}.",
        reply_markup=setup_confirm_scan_kb(),
    )


@router.callback_query(ProjectSetup.showing_scan, F.data == "setup:scan_ok")
async def cb_scan_ok(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(ProjectSetup.entering_object_name)
    await call.message.edit_text(
        "✅ Отлично.\n\n📝 Введи полное название объекта (как в акте):",
        reply_markup=cancel_kb(),
    )


@router.message(ProjectSetup.entering_object_name)
async def msg_setup_object_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 500:
        await message.answer("⚠️ 1-500 символов.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    new_id = add_object({"name": name})
    added_pos, added_drw = apply_scan(new_id, {
        "positions": data.get("scan_positions", {}),
        "drawings": data.get("scan_drawings", []),
    })
    await state.update_data(object_id=new_id)
    await message.answer(
        f"✅ Объект создан.\nПозиций: {added_pos}, чертежей: {added_drw}.\n\n"
        f"Заполним данные. Любой блок можно пропустить."
    )
    await _ask_tech_post(message, state)


# ---------- Госстройнадзор ----------

async def _ask_tech_post(message, state: FSMContext):
    await state.set_state(ProjectSetup.entering_tech_post)
    await message.answer(
        "🔍 Госстройнадзор.\n\n📝 Введи должность "
        "(например: «ведущего инженера»).\nИли нажми «Пропустить»:",
        reply_markup=setup_skip_kb("tech"),
    )


@router.message(ProjectSetup.entering_tech_post)
async def msg_setup_tech_post(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 200:
        await message.answer("⚠️ 1-200 символов.",
                             reply_markup=setup_skip_kb("tech"))
        return
    await state.update_data(tech_post=text)
    await state.set_state(ProjectSetup.entering_tech_place)
    await message.answer("🏢 Организация технадзора:", reply_markup=cancel_kb())


@router.message(ProjectSetup.entering_tech_place)
async def msg_setup_tech_place(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 300:
        await message.answer("⚠️ 1-300 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(tech_place=text)
    await state.set_state(ProjectSetup.entering_tech_name)
    await message.answer("👤 ФИО представителя технадзора:",
                         reply_markup=cancel_kb())


@router.message(ProjectSetup.entering_tech_name)
async def msg_setup_tech_name(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 200:
        await message.answer("⚠️ 1-200 символов.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    short = _make_short_name(text)
    update_object(
        data["object_id"],
        tech_post=data["tech_post"],
        tech_place=data["tech_place"],
        tech_name=text,
        tech_short=short,
    )
    await message.answer(f"✅ {short}")
    await _ask_author_post(message, state)


@router.callback_query(ProjectSetup.entering_tech_post,
                       F.data == "setup:skip:tech")
async def cb_skip_tech(call: CallbackQuery, state: FSMContext):
    await call.answer("Пропущено")
    await call.message.edit_text("⏭ Госстройнадзор пропущен.")
    await _ask_author_post(call.message, state)


# ---------- Авторский надзор ----------

async def _ask_author_post(message, state: FSMContext):
    await state.set_state(ProjectSetup.entering_author_post)
    await message.answer(
        "🎨 Авторский надзор.\n\n📝 Должность (например: «ГИП»)\n"
        "Или нажми «Пропустить»:",
        reply_markup=setup_skip_kb("author"),
    )


@router.message(ProjectSetup.entering_author_post)
async def msg_setup_author_post(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 200:
        await message.answer("⚠️ 1-200 символов.",
                             reply_markup=setup_skip_kb("author"))
        return
    await state.update_data(author_post=text)
    await state.set_state(ProjectSetup.entering_author_place)
    await message.answer("🏢 Организация автнадзора:", reply_markup=cancel_kb())


@router.message(ProjectSetup.entering_author_place)
async def msg_setup_author_place(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 300:
        await message.answer("⚠️ 1-300 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(author_place=text)
    await state.set_state(ProjectSetup.entering_author_name)
    await message.answer("👤 ФИО автнадзора:", reply_markup=cancel_kb())


@router.message(ProjectSetup.entering_author_name)
async def msg_setup_author_name(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 200:
        await message.answer("⚠️ 1-200 символов.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    short = _make_short_name(text)
    update_object(
        data["object_id"],
        author_post=data["author_post"],
        author_place=data["author_place"],
        author_name=text,
        author_short=short,
    )
    await message.answer(f"✅ {short}")
    await _ask_designer_firm(message, state)


@router.callback_query(ProjectSetup.entering_author_post,
                       F.data == "setup:skip:author")
async def cb_skip_author(call: CallbackQuery, state: FSMContext):
    await call.answer("Пропущено")
    await call.message.edit_text("⏭ Авторский надзор пропущен.")
    await _ask_designer_firm(call.message, state)


# ---------- Проектировщик ----------

async def _ask_designer_firm(message, state: FSMContext):
    await state.set_state(ProjectSetup.entering_designer_firm)
    await message.answer(
        "🏢 Организация-проектировщик "
        "(например: ООО «Проектировщик»):",
        reply_markup=setup_skip_kb("designer"),
    )


@router.message(ProjectSetup.entering_designer_firm)
async def msg_setup_designer_firm(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 300:
        await message.answer("⚠️ 1-300 символов.",
                             reply_markup=setup_skip_kb("designer"))
        return
    await state.update_data(designer_firm=text)
    await state.set_state(ProjectSetup.entering_designer_date)
    await message.answer("📅 Дата проекта (например: 01.2026):",
                         reply_markup=cancel_kb())


@router.message(ProjectSetup.entering_designer_date)
async def msg_setup_designer_date(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 20:
        await message.answer("⚠️ 1-20 символов.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    update_object(data["object_id"],
                  project_firm=data["designer_firm"],
                  project_date=text)
    await message.answer("✅ Сохранено.")
    await _ask_author_works(message, state)


@router.callback_query(ProjectSetup.entering_designer_firm,
                       F.data == "setup:skip:designer")
async def cb_skip_designer(call: CallbackQuery, state: FSMContext):
    await call.answer("Пропущено")
    await call.message.edit_text("⏭ Проектировщик пропущен.")
    await _ask_author_works(call.message, state)


# ---------- Работы с автнадзором ----------

async def _ask_author_works(message, state: FSMContext):
    work_types = get_all_work_types()
    if not work_types:
        await _finish_setup(message, state)
        return
    default = [w["name"] for w in work_types
               if w["name"].lower() in ("армирование", "гидроизоляция")]
    await state.update_data(author_works_selected=default)
    await state.set_state(ProjectSetup.choosing_author_works)
    await message.answer(
        "🛡 Работы, для которых нужен авторский надзор.\n"
        "По умолчанию — «Армирование» и «Гидроизоляция». Изменить можно здесь "
        "или позже в меню «🏗 Проект».",
        reply_markup=setup_works_kb(work_types, default),
    )


@router.callback_query(ProjectSetup.choosing_author_works,
                       F.data.startswith("setup:aw:"))
async def cb_setup_aw_toggle(call: CallbackQuery, state: FSMContext):
    wt_id = int(call.data.split(":")[2])
    work_types = get_all_work_types()
    wt = next((w for w in work_types if w["id"] == wt_id), None)
    if not wt:
        await call.answer()
        return
    data = await state.get_data()
    selected = data.get("author_works_selected", [])
    if wt["name"] in selected:
        selected.remove(wt["name"])
    else:
        selected.append(wt["name"])
    await state.update_data(author_works_selected=selected)
    await call.message.edit_reply_markup(
        reply_markup=setup_works_kb(work_types, selected)
    )
    await call.answer()


@router.callback_query(ProjectSetup.choosing_author_works,
                       F.data == "setup:aw_done")
async def cb_setup_aw_done(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    selected = data.get("author_works_selected", [])
    obj_id = data["object_id"]
    existing = set(get_object_author_supervision(obj_id))
    for w in set(selected) - existing:
        add_object_author_supervision(obj_id, w)
    await call.message.edit_text(
        f"✅ Работ с автнадзором: {len(selected)}\n"
        + (", ".join(selected) if selected else "—")
    )
    await _finish_setup(call.message, state)


async def _finish_setup(message, state: FSMContext):
    await state.clear()
    obj = _current_object()
    await message.answer(
        f"🎉 Настройка завершена!\n\nОбъект:\n{obj['name'][:100]}",
        reply_markup=main_menu_kb(),
    )


# =====================================================================
#  МЕНЮ «🏗 ПРОЕКТ»
# =====================================================================

@router.message(Command("project"))
@router.message(F.text.contains("🏗 Проект"))
async def cmd_project(message: Message, state: FSMContext):
    await state.clear()
    if not _current_object():
        await message.answer("⚠️ Объект не настроен. /start",
                             reply_markup=main_menu_kb())
        return
    await _show_project_menu(message, state)


@router.callback_query(F.data == "pj:menu")
async def cb_pj_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    obj = _current_object()
    if not obj:
        await call.message.answer("⚠️ Объект не настроен.")
        return
    await state.set_state(ProjectEdit.menu)
    text = (
        f"🏗 Проект:\n"
        f"  • Объект: {obj['name'][:80]}\n"
        f"  • Генподрядчик: {obj.get('gen_contractor') or '—'}\n"
        f"  • Субподрядчик: {obj.get('subgen_firm') or '—'}\n"
        f"  • Госстройнадзор: {obj.get('tech_short') or '—'}\n"
        f"  • Авторский надзор: {obj.get('author_short') or '—'}\n"
        f"  • Проектировщик: {obj.get('project_firm') or '—'} "
        f"({obj.get('project_date') or '—'})"
    )
    try:
        await call.message.edit_text(text, reply_markup=project_menu_kb())
    except Exception:
        await call.message.answer(text, reply_markup=project_menu_kb())


# ---------- Название объекта ----------

@router.callback_query(F.data == "pj:name")
async def cb_pj_name(call: CallbackQuery, state: FSMContext):
    await call.answer()
    obj = _current_object()
    await state.set_state(ProjectEdit.entering_object_name)
    await call.message.answer(
        f"📝 Текущее название:\n{obj['name']}\n\nВведи новое:",
        reply_markup=cancel_kb(),
    )


@router.message(ProjectEdit.entering_object_name)
async def msg_pj_object_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 500:
        await message.answer("⚠️ 1-500 символов.", reply_markup=cancel_kb())
        return
    obj = _current_object()
    try:
        update_object(obj["id"], name=name)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {e}")
        return
    await message.answer("✅ Обновлено.")
    await _show_project_menu(message, state)


# ---------- Персоналии ----------

PERSON_PREFIXES = {
    "gen": {
        "post": "gen_person_post", "place_field": "gen_contractor",
        "name": "gen_person", "short": "gen_short",
        "label": "Генподрядчик",
        "post_state": ProjectEdit.entering_gen_post,
        "firm_state": ProjectEdit.entering_gen_firm,
        "name_state": ProjectEdit.entering_gen_name,
        "kb_prefix": "pg",
    },
    "subgen": {
        "post": "subgen_person_post", "place_field": "subgen_firm",
        "name": "subgen_person", "short": "subgen_short",
        "label": "Субподрядчик",
        "post_state": ProjectEdit.entering_subgen_post,
        "firm_state": ProjectEdit.entering_subgen_firm,
        "name_state": ProjectEdit.entering_subgen_name,
        "kb_prefix": "ps",
    },
    "tech": {
        "post": "tech_post", "place_field": "tech_place",
        "name": "tech_name", "short": "tech_short",
        "label": "Госстройнадзор",
        "post_state": ProjectEdit.entering_tech_post,
        "firm_state": ProjectEdit.entering_tech_place,
        "name_state": ProjectEdit.entering_tech_name,
        "kb_prefix": "pt",
    },
    "author": {
        "post": "author_post", "place_field": "author_place",
        "name": "author_name", "short": "author_short",
        "label": "Авторский надзор",
        "post_state": ProjectEdit.entering_author_post,
        "firm_state": ProjectEdit.entering_author_place,
        "name_state": ProjectEdit.entering_author_name,
        "kb_prefix": "pa",
    },
}


@router.callback_query(F.data.in_({"pj:gen", "pj:subgen", "pj:tech", "pj:author"}))
async def cb_pj_person(call: CallbackQuery, state: FSMContext):
    await call.answer()
    prefix = call.data.split(":")[1]
    cfg = PERSON_PREFIXES[prefix]
    obj = _current_object()
    text = (
        f"👤 {cfg['label']}\n\n"
        f"  • Должность: {obj.get(cfg['post']) or '—'}\n"
        f"  • Организация: {obj.get(cfg['place_field']) or '—'}\n"
        f"  • ФИО: {obj.get(cfg['name']) or '—'}\n\n"
        f"Что изменить?"
    )
    await call.message.edit_text(text,
                                  reply_markup=project_person_kb(cfg["kb_prefix"]))


def _find_person_by_state(current_state, kind):
    for key, cfg in PERSON_PREFIXES.items():
        st = cfg[f"{kind}_state"].state
        if current_state == st:
            return key, cfg
    return None, None


@router.callback_query(F.data.startswith("pg:"))
@router.callback_query(F.data.startswith("ps:"))
@router.callback_query(F.data.startswith("pt:"))
@router.callback_query(F.data.startswith("pa:"))
async def cb_pj_person_field(call: CallbackQuery, state: FSMContext):
    kb_pref = call.data.split(":")[0]
    field = call.data.split(":")[1]
    prefix = {"pg": "gen", "ps": "subgen",
              "pt": "tech", "pa": "author"}[kb_pref]
    cfg = PERSON_PREFIXES[prefix]
    obj = _current_object()
    if field == "post":
        await state.set_state(cfg["post_state"])
        await call.message.answer(
            f"📝 Должность сейчас: {obj.get(cfg['post']) or '—'}\n\nНовая:",
            reply_markup=cancel_kb(),
        )
    elif field == "place":
        await state.set_state(cfg["firm_state"])
        await call.message.answer(
            f"🏢 Организация сейчас: {obj.get(cfg['place_field']) or '—'}\n\nНовая:",
            reply_markup=cancel_kb(),
        )
    elif field == "name":
        await state.set_state(cfg["name_state"])
        await call.message.answer(
            f"👤 ФИО сейчас: {obj.get(cfg['name']) or '—'}\n\nНовое:",
            reply_markup=cancel_kb(),
        )
    await call.answer()


@router.message(ProjectEdit.entering_gen_post)
@router.message(ProjectEdit.entering_subgen_post)
@router.message(ProjectEdit.entering_tech_post)
@router.message(ProjectEdit.entering_author_post)
async def msg_pj_post(message: Message, state: FSMContext):
    current = await state.get_state()
    key, cfg = _find_person_by_state(current, "post")
    if not cfg:
        return
    text = (message.text or "").strip()
    if not text or len(text) > 200:
        await message.answer("⚠️ 1-200 символов.", reply_markup=cancel_kb())
        return
    obj = _current_object()
    update_object(obj["id"], **{cfg["post"]: text})
    await message.answer("✅ Обновлено.")
    await _show_project_menu(message, state)


@router.message(ProjectEdit.entering_gen_firm)
@router.message(ProjectEdit.entering_subgen_firm)
@router.message(ProjectEdit.entering_tech_place)
@router.message(ProjectEdit.entering_author_place)
async def msg_pj_place(message: Message, state: FSMContext):
    current = await state.get_state()
    key, cfg = _find_person_by_state(current, "firm")
    if not cfg:
        return
    text = (message.text or "").strip()
    if not text or len(text) > 300:
        await message.answer("⚠️ 1-300 символов.", reply_markup=cancel_kb())
        return
    obj = _current_object()
    update_object(obj["id"], **{cfg["place_field"]: text})
    await message.answer("✅ Обновлено.")
    await _show_project_menu(message, state)


@router.message(ProjectEdit.entering_gen_name)
@router.message(ProjectEdit.entering_subgen_name)
@router.message(ProjectEdit.entering_tech_name)
@router.message(ProjectEdit.entering_author_name)
async def msg_pj_person_name(message: Message, state: FSMContext):
    current = await state.get_state()
    key, cfg = _find_person_by_state(current, "name")
    if not cfg:
        return
    text = (message.text or "").strip()
    if not text or len(text) > 200:
        await message.answer("⚠️ 1-200 символов.", reply_markup=cancel_kb())
        return
    obj = _current_object()
    short = _make_short_name(text)
    update_object(obj["id"], **{cfg["name"]: text, cfg["short"]: short})
    await message.answer(f"✅ {short}")
    await _show_project_menu(message, state)


# ---------- Проектировщик ----------

@router.callback_query(F.data == "pj:designer")
async def cb_pj_designer(call: CallbackQuery, state: FSMContext):
    await call.answer()
    obj = _current_object()
    await state.set_state(ProjectEdit.entering_designer_firm)
    await call.message.answer(
        f"🏢 Проектировщик: {obj.get('project_firm') or '—'}\n"
        f"📅 Дата проекта: {obj.get('project_date') or '—'}\n\n"
        f"Введи новую организацию:",
        reply_markup=cancel_kb(),
    )


@router.message(ProjectEdit.entering_designer_firm)
async def msg_pj_designer_firm(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 300:
        await message.answer("⚠️ 1-300 символов.", reply_markup=cancel_kb())
        return
    obj = _current_object()
    update_object(obj["id"], project_firm=text)
    await state.set_state(ProjectEdit.entering_designer_date)
    await message.answer("📅 Дата проекта (например: 01.2026):",
                         reply_markup=cancel_kb())


@router.message(ProjectEdit.entering_designer_date)
async def msg_pj_designer_date(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 20:
        await message.answer("⚠️ 1-20 символов.", reply_markup=cancel_kb())
        return
    obj = _current_object()
    update_object(obj["id"], project_date=text)
    await message.answer("✅ Обновлено.")
    await _show_project_menu(message, state)


# ---------- Работы с автнадзором ----------

@router.callback_query(F.data == "pj:author_works")
async def cb_pj_author_works(call: CallbackQuery, state: FSMContext):
    await call.answer()
    obj = _current_object()
    work_types = get_all_work_types()
    selected = get_object_author_supervision(obj["id"])
    await state.update_data(author_works_selected=selected)
    await state.set_state(ProjectEdit.choosing_author_works)
    await call.message.edit_text(
        f"🛡 Работы с автнадзором.\nВыбрано: {len(selected)}",
        reply_markup=project_author_works_kb(work_types, selected),
    )


@router.callback_query(ProjectEdit.choosing_author_works,
                       F.data.startswith("paw:toggle:"))
async def cb_paw_toggle(call: CallbackQuery, state: FSMContext):
    wt_id = int(call.data.split(":")[2])
    work_types = get_all_work_types()
    wt = next((w for w in work_types if w["id"] == wt_id), None)
    if not wt:
        await call.answer()
        return
    data = await state.get_data()
    selected = data.get("author_works_selected", [])
    if wt["name"] in selected:
        selected.remove(wt["name"])
    else:
        selected.append(wt["name"])
    await state.update_data(author_works_selected=selected)
    await call.message.edit_reply_markup(
        reply_markup=project_author_works_kb(work_types, selected)
    )
    await call.answer()


@router.callback_query(ProjectEdit.choosing_author_works, F.data == "paw:done")
async def cb_paw_done(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    selected = data.get("author_works_selected", [])
    obj = _current_object()
    existing = set(get_object_author_supervision(obj["id"]))
    new_set = set(selected)
    for w in existing - new_set:
        remove_object_author_supervision(obj["id"], w)
    for w in new_set - existing:
        add_object_author_supervision(obj["id"], w)
    await call.message.edit_text(
        f"✅ Сохранено. Работ с автнадзором: {len(selected)}"
    )
    await _show_project_menu(call.message, state)


# =====================================================================
#  МАТЕРИАЛЫ И КАТЕГОРИИ
# =====================================================================

async def _render_categories(message, state: FSMContext, edit=False):
    obj = _current_object()
    cats, total = get_categories_with_counts(obj["id"])
    await state.set_state(ProjectEdit.materials_menu)
    text = (
        f"📦 Материалы и паспорта\n\n"
        f"Категорий: {len(cats)}, материалов всего: {total}\n\n"
        f"Выбери категорию:"
    )
    kb = material_categories_kb(cats, total_count=total,
                                 back_cb="pj:menu", add_cb="pmat:add")
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "pj:materials")
@router.callback_query(F.data == "pmat:list")
async def cb_pj_materials(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _render_categories(call.message, state, edit=True)


# ---------- Просмотр категории: показываем материалы списком ----------

@router.callback_query(F.data.startswith("pmat:cat:"))
async def cb_pmat_cat_view(call: CallbackQuery, state: FSMContext):
    await call.answer()
    try:
        cat_id = int(call.data.split(":")[2])
    except (ValueError, IndexError):
        return

    if cat_id == -1:
        # «Без категории»
        obj = _current_object()
        all_m = get_materials_for_object(obj["id"])
        materials = [m for m in all_m if not m.get("category_id")]
        title = "📁 Без категории"
        category_id_for_kb = None
    else:
        cat = get_material_category(cat_id)
        if not cat:
            await call.message.answer("Категория не найдена.")
            return
        obj = _current_object()
        materials = get_materials_for_object(obj["id"], category_id=cat_id)
        title = f"📁 {cat['name']}"
        category_id_for_kb = cat_id

    await state.set_state(ProjectEdit.materials_menu)

    lines = [title, f"Материалов: {len(materials)}"]
    if materials:
        lines.append("")
        lines.append("Выбери материал для просмотра / редактирования:")
    else:
        lines.append("")
        lines.append("Материалов нет.")
    text = "\n".join(lines)

    kb = _category_view_kb(category_id_for_kb, materials)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("pmat:add_in_cat:"))
async def cb_pmat_add_in_cat(call: CallbackQuery, state: FSMContext):
    await call.answer()
    try:
        cat_id = int(call.data.split(":")[2])
    except (ValueError, IndexError):
        return
    if cat_id == -1:
        cat_id = 0
    cat_label = "Без категории"
    if cat_id:
        cat = get_material_category(cat_id)
        if not cat:
            await call.message.answer("Категория не найдена.")
            return
        cat_label = cat["name"]
    await state.update_data(
        new_material_category_id=cat_id or None,
        new_material_name=None,
        new_material_qdoc=None,
        new_material_work_types=None,
    )
    await state.set_state(ProjectEdit.entering_material_name)
    await call.message.answer(
        f"📁 Категория: {cat_label}\n\n"
        f"📝 Название материала:",
        reply_markup=cancel_kb(),
    )


@router.callback_query(F.data == "pmat:all")
async def cb_pmat_all(call: CallbackQuery, state: FSMContext):
    await call.answer()
    obj = _current_object()
    materials = get_materials_for_object(obj["id"])
    if not materials:
        await call.message.answer("Материалов пока нет.")
        return
    await state.set_state(ProjectEdit.materials_menu)
    text = f"📂 Все материалы ({len(materials)}):"
    try:
        await call.message.edit_text(text,
                                      reply_markup=project_materials_kb(materials))
    except Exception:
        await call.message.answer(text,
                                  reply_markup=project_materials_kb(materials))


# ---------- Карточка материала ----------

@router.callback_query(F.data.startswith("pmat:view:"))
async def cb_pmat_view(call: CallbackQuery, state: FSMContext):
    await call.answer()
    mat_id = int(call.data.split(":")[2])
    mat = get_material(mat_id)
    if not mat:
        await call.message.answer("Материал не найден.")
        return
    certs = get_certificates_for_material(mat_id, limit=20)
    cat_name = mat.get("category_name") or "без категории"
    text = (
        f"📦 {mat['name']}\n"
        f"📁 Категория: {cat_name}\n"
        f"📄 Норматив: {mat['quality_doc'] or '—'}\n"
        f"🔨 Работы: {mat.get('work_types') or '—'}\n"
        f"📜 Документов: {len(certs)}"
    )
    await state.set_state(ProjectEdit.materials_menu)
    kb = material_card_ext_kb(mat_id)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)


# ---------- Добавление нового материала ----------

@router.callback_query(F.data == "pmat:add")
async def cb_pmat_add(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.update_data(
        new_material_category_id=None,
        new_material_name=None,
        new_material_qdoc=None,
        new_material_work_types=None,
    )
    await state.set_state(ProjectEdit.entering_material_name)
    await call.message.answer("📝 Название материала:", reply_markup=cancel_kb())


@router.message(ProjectEdit.entering_material_name)
async def msg_pmat_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 200:
        await message.answer("⚠️ 1-200 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(new_material_name=name)
    await state.set_state(ProjectEdit.entering_material_qdoc)
    await message.answer("📄 Нормативный документ (ГОСТ/ТУ/СТБ). Или «—»:",
                         reply_markup=cancel_kb())


@router.message(ProjectEdit.entering_material_qdoc)
async def msg_pmat_qdoc(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    qdoc = "" if text in ("—", "-", "") else text[:200]
    await state.update_data(new_material_qdoc=qdoc)
    await state.set_state(ProjectEdit.entering_material_work_types)
    await message.answer(
        "🔨 Типы работ (через `|`, например «Бетонирование|Армирование»).\n"
        "Или «—»:",
        reply_markup=cancel_kb(),
    )


@router.message(ProjectEdit.entering_material_work_types)
async def msg_pmat_work_types(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    wt = "" if text in ("—", "-", "") else text[:200]
    await state.update_data(new_material_work_types=wt)
    data = await state.get_data()
    # если категория уже задана — сразу сохраняем
    if data.get("new_material_category_id") is not None:
        await _save_new_material(message, state)
        return
    cats = get_all_material_categories()
    if not cats:
        await _save_new_material(message, state)
        return
    await state.set_state(ProjectEdit.choosing_category_for_new_material)
    await message.answer(
        "📁 Выбери категорию:",
        reply_markup=material_add_category_kb(
            cats, back_cb="pmat:list", cb_prefix="pmat:new_in_cat",
        ),
    )


@router.callback_query(ProjectEdit.choosing_category_for_new_material,
                       F.data.startswith("pmat:new_in_cat:"))
async def cb_pmat_new_in_cat(call: CallbackQuery, state: FSMContext):
    raw = call.data.split(":", 2)[2]
    cat_id = int(raw) if raw else 0
    await call.answer()
    await state.update_data(new_material_category_id=cat_id or None)
    await _save_new_material(call.message, state)


async def _save_new_material(message, state: FSMContext):
    data = await state.get_data()
    name = data.get("new_material_name")
    qdoc = data.get("new_material_qdoc") or ""
    wt = data.get("new_material_work_types") or ""
    cat_id = data.get("new_material_category_id")
    obj = _current_object()
    try:
        new_id = add_material(
            name=name, quality_doc=qdoc, object_id=obj["id"],
            work_types=wt, category_id=cat_id,
        )
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {e}")
        return
    await state.update_data(
        new_material_name=None, new_material_qdoc=None,
        new_material_work_types=None, new_material_category_id=None,
    )
    await message.answer(f"✅ «{name}» добавлен.")
    await _render_categories(message, state)


# ---------- Переименование материала ----------

@router.callback_query(F.data.startswith("pmat:edit:"))
async def cb_pmat_edit(call: CallbackQuery, state: FSMContext):
    await call.answer()
    mat_id = int(call.data.split(":")[2])
    mat = get_material(mat_id)
    if not mat:
        return
    await state.update_data(edit_material_id=mat_id)
    await state.set_state(ProjectEdit.editing_material_name)
    await call.message.answer(
        f"📝 Текущее: {mat['name']}\n\nНовое название:",
        reply_markup=cancel_kb(),
    )


@router.message(ProjectEdit.editing_material_name)
async def msg_pmat_edit_name(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 200:
        await message.answer("⚠️ 1-200 символов.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    update_material(data["edit_material_id"], name=text)
    await message.answer("✅ Переименовано.")
    await _render_categories(message, state)


# ---------- Перенос между категориями ----------

@router.callback_query(F.data.startswith("pmat:move:"))
async def cb_pmat_move(call: CallbackQuery, state: FSMContext):
    await call.answer()
    mat_id = int(call.data.split(":")[2])
    mat = get_material(mat_id)
    if not mat:
        return
    cats = get_all_material_categories()
    if not cats:
        await call.message.answer("Категорий нет. Создай сначала.")
        return
    await state.set_state(ProjectEdit.choosing_category_for_move)
    await call.message.answer(
        f"📁 Текущая категория: {mat.get('category_name') or 'без категории'}\n\n"
        f"Куда перенести?",
        reply_markup=move_material_category_kb(
            mat_id, cats, current_category_id=mat.get("category_id")
        ),
    )


@router.callback_query(ProjectEdit.choosing_category_for_move,
                       F.data.startswith("pmat:move_to:"))
async def cb_pmat_move_to(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    mat_id = int(parts[2])
    cat_id = int(parts[3])
    await call.answer()
    move_material_to_category(mat_id, cat_id or None)
    mat = get_material(mat_id)
    await call.message.answer(
        f"✅ «{mat['name']}» → {mat.get('category_name') or 'без категории'}"
    )
    await _render_categories(call.message, state)


# ---------- Удаление материала ----------

@router.callback_query(F.data.startswith("pmat:del:"))
async def cb_pmat_del(call: CallbackQuery, state: FSMContext):
    mat_id = int(call.data.split(":")[2])
    mat = get_material(mat_id)
    if not mat:
        await call.answer()
        return
    delete_material(mat_id)
    await call.answer(f"🗑 Удалено: {mat['name']}")
    await _render_categories(call.message, state, edit=True)


# =====================================================================
#  КАТЕГОРИИ — CRUD
# =====================================================================

@router.callback_query(F.data == "pmat:new_cat")
async def cb_pmat_new_cat(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(ProjectEdit.entering_material_category_name)
    await call.message.answer("📝 Название новой категории:",
                              reply_markup=cancel_kb())


@router.message(ProjectEdit.entering_material_category_name)
async def msg_pmat_new_cat_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 100:
        await message.answer("⚠️ 1-100 символов.", reply_markup=cancel_kb())
        return
    new_id, created = add_material_category(name, sort_order=100)
    if not created:
        await message.answer("⚠️ Категория с таким именем уже есть.")
        return
    await message.answer(f"✅ Категория «{name}» создана.")
    await _render_categories(message, state)


@router.callback_query(F.data.startswith("pmat:cat_rename:"))
async def cb_pmat_cat_rename(call: CallbackQuery, state: FSMContext):
    await call.answer()
    cat_id = int(call.data.split(":")[2])
    cat = get_material_category(cat_id)
    if not cat:
        await call.message.answer("Категория не найдена.")
        return
    await state.update_data(edit_cat_id=cat_id)
    await state.set_state(ProjectEdit.editing_material_category_name)
    await call.message.answer(
        f"📝 Текущее: {cat['name']}\n\nНовое имя:",
        reply_markup=cancel_kb(),
    )


@router.message(ProjectEdit.editing_material_category_name)
async def msg_pmat_cat_rename(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 100:
        await message.answer("⚠️ 1-100 символов.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    ok = update_material_category(data["edit_cat_id"], name=text)
    if not ok:
        await message.answer("⚠️ Имя занято, попробуй другое.")
        return
    await message.answer("✅ Переименовано.")
    await _render_categories(message, state)


@router.callback_query(F.data.startswith("pmat:cat_del:"))
async def cb_pmat_cat_del(call: CallbackQuery, state: FSMContext):
    cat_id = int(call.data.split(":")[2])
    cat = get_material_category(cat_id)
    if not cat:
        await call.answer()
        return
    cnt = count_materials_in_category(cat_id)
    if cnt == 0:
        delete_material_category(cat_id, force=False)
        await call.answer(f"🗑 Категория «{cat['name']}» удалена")
        await _render_categories(call.message, state, edit=True)
        return
    await call.answer()
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить, материалы без категории",
                   callback_data=f"pmat:cat_del_force:{cat_id}")
    builder.button(text="↩ Отмена", callback_data=f"pmat:cat:{cat_id}")
    builder.adjust(1)
    await call.message.answer(
        f"⚠️ В категории «{cat['name']}» {cnt} материалов.\n"
        f"Удалить категорию? Материалы останутся без категории.",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("pmat:cat_del_force:"))
async def cb_pmat_cat_del_force(call: CallbackQuery, state: FSMContext):
    cat_id = int(call.data.split(":")[2])
    cat = get_material_category(cat_id)
    if not cat:
        await call.answer()
        return
    delete_material_category(cat_id, force=True)
    await call.answer("🗑 Удалено")
    await _render_categories(call.message, state, edit=True)


# =====================================================================
#  СЕРТИФИКАТЫ МАТЕРИАЛА
# =====================================================================

@router.callback_query(F.data.startswith("pmat:certs:"))
async def cb_pmat_certs(call: CallbackQuery, state: FSMContext):
    await call.answer()
    mat_id = int(call.data.split(":")[2])
    mat = get_material(mat_id)
    if not mat:
        return
    certs = get_certificates_for_material(mat_id, limit=50)
    await state.set_state(ProjectEdit.material_certs_menu)
    text = f"📜 Документы «{mat['name']}» ({len(certs)}):"
    try:
        await call.message.edit_text(text,
                                      reply_markup=project_certs_kb(mat_id, certs))
    except Exception:
        await call.message.answer(text,
                                  reply_markup=project_certs_kb(mat_id, certs))


@router.callback_query(F.data.startswith("pcert:add:"))
async def cb_pcert_add(call: CallbackQuery, state: FSMContext):
    await call.answer()
    mat_id = int(call.data.split(":")[2])
    await state.update_data(cert_material_id=mat_id)
    await state.set_state(ProjectEdit.entering_cert_doc_type)
    await call.message.answer(
        "📎 Какой документ добавить?",
        reply_markup=cert_type_choice_kb(),
    )


@router.callback_query(ProjectEdit.entering_cert_doc_type,
                       F.data.startswith("cert_type:"))
async def cb_pcert_type(call: CallbackQuery, state: FSMContext):
    choice = call.data.split(":", 1)[1]
    if choice == "custom":
        await call.answer()
        await state.set_state(ProjectEdit.entering_cert_doc_type_custom)
        await call.message.answer(
            "✏️ Введите название документа:",
            reply_markup=cancel_kb(),
        )
        return
    doc_type = None if choice == "skip" else choice
    await state.update_data(cert_doc_type=doc_type)
    await call.answer()
    await state.set_state(ProjectEdit.entering_cert_number)
    await call.message.answer("📝 Номер документа:", reply_markup=cancel_kb())


@router.message(ProjectEdit.entering_cert_doc_type_custom)
async def msg_pcert_type_custom(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 100:
        await message.answer("⚠️ 1-100 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(cert_doc_type=text)
    await state.set_state(ProjectEdit.entering_cert_number)
    await message.answer("📝 Номер документа:", reply_markup=cancel_kb())


@router.message(ProjectEdit.entering_cert_number)
async def msg_pcert_number(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text or len(text) > 100:
        await message.answer("⚠️ 1-100 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(cert_number=text)
    await state.set_state(ProjectEdit.entering_cert_date)
    await message.answer("📅 Дата выдачи (ДД.ММ.ГГГГ) или «—»:",
                         reply_markup=cancel_kb())


@router.message(ProjectEdit.entering_cert_date)
async def msg_pcert_date(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text in ("—", "-", ""):
        date_str = ""
    else:
        try:
            parts = text.replace("/", ".").replace("-", ".").split(".")
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            if not (1 <= d <= 31 and 1 <= m <= 12 and 2000 <= y <= 2100):
                raise ValueError
            date_str = f"{d:02d}.{m:02d}.{y}"
        except Exception:
            await message.answer("⚠️ Формат: ДД.ММ.ГГГГ или «—»",
                                 reply_markup=cancel_kb())
            return
    data = await state.get_data()
    mat_id = data["cert_material_id"]
    doc_type = data.get("cert_doc_type")
    add_certificate(mat_id, data["cert_number"],
                    date_from=date_str, doc_type=doc_type)
    await state.update_data(cert_doc_type=None)
    await message.answer("✅ Документ добавлен.")
    mat = get_material(mat_id)
    certs = get_certificates_for_material(mat_id, limit=50)
    await state.set_state(ProjectEdit.material_certs_menu)
    await message.answer(
        f"📜 Документы «{mat['name']}» ({len(certs)}):",
        reply_markup=project_certs_kb(mat_id, certs),
    )


@router.callback_query(F.data.startswith("pcert:del:"))
async def cb_pcert_del(call: CallbackQuery, state: FSMContext):
    cert_id = int(call.data.split(":")[2])
    conn = get_conn()
    row = conn.execute("SELECT material_id FROM certificates WHERE id = ?",
                       (cert_id,)).fetchone()
    conn.close()
    if not row:
        await call.answer("Не найдено")
        return
    mat_id = row["material_id"]
    delete_certificate(cert_id)
    await call.answer("🗑 Удалено")
    mat = get_material(mat_id)
    certs = get_certificates_for_material(mat_id, limit=50)
    await state.set_state(ProjectEdit.material_certs_menu)
    try:
        await call.message.edit_text(
            f"📜 Документы «{mat['name']}» ({len(certs)}):",
            reply_markup=project_certs_kb(mat_id, certs),
        )
    except Exception:
        await call.message.answer(
            f"📜 Документы «{mat['name']}» ({len(certs)}):",
            reply_markup=project_certs_kb(mat_id, certs),
        )


# =====================================================================
#  ПЕРЕСКАНИРОВАНИЕ
# =====================================================================

@router.callback_query(F.data == "pj:rescan")
async def cb_pj_rescan(call: CallbackQuery, state: FSMContext):
    await call.answer("Сканирую…")
    obj = _current_object()
    try:
        result = scan_only()
    except Exception as e:
        await call.message.answer(f"❌ {e}")
        return
    added_pos, added_drw = apply_scan(obj["id"], result)
    await call.message.answer(
        f"✅ Пересканировано.\n"
        f"Позиций добавлено: {added_pos}\n"
        f"Чертежей записано: {added_drw}"
    )
    await _show_project_menu(call.message, state)


# =====================================================================
#  CANCEL в состояниях проекта
# =====================================================================

@router.callback_query(StateFilter(ProjectSetup), F.data == "cancel")
@router.callback_query(StateFilter(ProjectEdit), F.data == "cancel")
async def cb_cancel_project(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text("❌ Отменено.")
    except Exception:
        await call.message.answer("❌ Отменено.")
    await call.answer()
    if _current_object():
        await call.message.answer("Выбери действие:",
                                  reply_markup=main_menu_kb())