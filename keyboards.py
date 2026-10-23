# keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# =====================================================================
#  УТИЛИТЫ
# =====================================================================

def _compress_nums_for_display(numbers):
    nums = []
    for n in numbers:
        try:
            nums.append(int(n))
        except (ValueError, TypeError):
            pass
    if not nums:
        return ""
    nums = sorted(set(nums))
    if len(nums) == 1:
        return str(nums[0])
    if nums == list(range(nums[0], nums[-1] + 1)):
        return f"{nums[0]}-{nums[-1]}"
    return ",".join(str(n) for n in nums)


def act_label(act):
    num = act.get("act_number") or "?"
    wt = (act.get("work_type_name") or "").strip()
    pos = (act.get("position_number") or "").strip()
    if len(wt) > 35:
        wt = wt[:33] + "…"
    parts = [f"Акт{num}"]
    if wt:
        parts.append(wt)
    if pos:
        parts.append(f"позиция №{pos}")
    return " ".join(parts)


def _single_pos_label(pos):
    num = (pos.get("position_number") or "").strip()
    name = (pos.get("name") or "").strip()
    if num:
        return f"{name} (поз. {num})"
    return name


def _group_label(group):
    nums = [n for n in group.get("numbers", []) if n]
    range_str = _compress_nums_for_display(nums)
    name = group.get("name") or ""
    if range_str:
        return f"{name} (поз. {range_str})"
    return name


# =====================================================================
#  ГЛАВНОЕ МЕНЮ
# =====================================================================

def main_menu_kb():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆕 Новый акт"),
             KeyboardButton(text="📋 Циклы работ")],
            [KeyboardButton(text="📄 Мои акты"),
             KeyboardButton(text="🏗 Проект")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие…"
    )
    return kb


# =====================================================================
#  ПОЗИЦИИ
# =====================================================================

def positions_grouped_kb(groups):
    builder = InlineKeyboardBuilder()
    for i, g in enumerate(groups):
        positions = g["positions"]
        if len(positions) == 1:
            text = _single_pos_label(positions[0])
            if len(text) > 60:
                text = text[:58] + "…"
            builder.button(text=text, callback_data=f"pos_id:{positions[0]['id']}")
        else:
            text = _group_label(g)
            if len(text) > 60:
                text = text[:58] + "…"
            builder.button(text=text, callback_data=f"pos_grp:{i}")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def position_group_action_kb(group, group_index):
    builder = InlineKeyboardBuilder()
    nums = [n for n in group.get("numbers", []) if n]
    range_str = _compress_nums_for_display(nums)
    name = group.get("name") or ""
    if range_str:
        text_all = f"📦 Все: {name} (№{range_str})"
    else:
        text_all = f"📦 Все: {name}"
    if len(text_all) > 60:
        text_all = text_all[:58] + "…"
    builder.button(text=text_all, callback_data=f"pos_all:{group_index}")
    builder.button(text="🔢 Отдельная позиция",
                   callback_data=f"pos_single:{group_index}")
    builder.button(text="🔙", callback_data="pos_grp_back")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def positions_in_group_kb(positions, group_index):
    builder = InlineKeyboardBuilder()
    for p in positions:
        text = _single_pos_label(p)
        if len(text) > 60:
            text = text[:58] + "…"
        builder.button(text=text, callback_data=f"pos_id:{p['id']}")
    builder.button(text="🔙", callback_data=f"pos_back_group:{group_index}")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  ПРОЧИЕ БАЗОВЫЕ
# =====================================================================

def objects_kb(objects):
    builder = InlineKeyboardBuilder()
    for o in objects:
        text = o["name"][:60] + ("…" if len(o["name"]) > 60 else "")
        builder.button(text=text, callback_data=f"obj:{o['id']}")
    builder.button(text="➕ Добавить объект", callback_data="new_object")
    builder.button(text="🔙", callback_data="back")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def work_types_kb(work_types, add_new=True, back_cb="na:back",
                  del_cb="na:del"):
    builder = InlineKeyboardBuilder()
    for wt in work_types:
        builder.button(text=wt["name"], callback_data=f"wt:{wt['id']}")
    if add_new:
        builder.button(text="➕ Добавить новый тип работы",
                       callback_data="wt_new")
    if back_cb:
        builder.button(text="🔙 Назад", callback_data=back_cb)
    if del_cb:
        builder.button(text="🗑 Удалить акт", callback_data=del_cb)
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def sections_kb(sections, back_cb="na:back", del_cb="na:del"):
    builder = InlineKeyboardBuilder()
    for sec in sections:
        builder.button(text=f"📂 {sec}", callback_data=f"sec:{sec}")
    if back_cb:
        builder.button(text="🔙 Назад", callback_data=back_cb)
    if del_cb:
        builder.button(text="🗑 Удалить акт", callback_data=del_cb)
    builder.adjust(2, 1, 1)
    return builder.as_markup()


# =====================================================================
#  МАТЕРИАЛЫ — ВЫБОР В АКТЕ (двухуровнево: категории → материалы)
# =====================================================================

def material_categories_select_kb(cats_with_selected, total_count=None,
                                    any_selected=False):
    """Список категорий для выбора материалов в акте.
    cats_with_selected: [{"id":..,"name":..,"count":..,"selected":..,"matched":..}]
    id=0 → «Все материалы», id=-1 → «Без категории».
    """
    builder = InlineKeyboardBuilder()
    for c in cats_with_selected:
        cnt = c.get("count", 0)
        sel = c.get("selected", 0)
        mch = c.get("matched", 0)
        text = f"📁 {c['name']} ({cnt})"
        if mch:
            text += " ⭐"
        if sel:
            text += f" ✅ {sel}"
        if len(text) > 60:
            text = text[:58] + "…"
        builder.button(text=text, callback_data=f"matcat_pick:{c['id']}")
    if total_count is not None:
        builder.button(text=f"📂 Все материалы ({total_count})",
                       callback_data="matcat_pick:0")
    if any_selected:
        builder.button(text="✅ Готово", callback_data="mat_done")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def materials_in_category_kb(materials, selected_ids, matched_ids=None):
    """Список материалов внутри категории (или всех).
    Возврат «🔙 К категориям» показывается всегда.
    """
    builder = InlineKeyboardBuilder()
    matched_ids = matched_ids or set()
    for m in materials:
        prefix = "✅ " if m["id"] in selected_ids else "⬜ "
        star = "⭐ " if m["id"] in matched_ids else ""
        text = prefix + star + m["name"][:50]
        if len(text) > 60:
            text = text[:58] + "…"
        builder.button(text=text, callback_data=f"mat:{m['id']}")
    builder.button(text="➕ Добавить новый материал",
                   callback_data="mat_add_new")
    builder.button(text="✅ Готово", callback_data="mat_done")
    builder.button(text="🔙 К категориям", callback_data="matcat_back")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  МАТЕРИАЛЫ — ПРОЕКТ (просмотр категории с материалами)
# =====================================================================

def material_categories_kb(categories_with_counts, total_count=None,
                           back_cb="pj:menu", add_cb="pmat:add"):
    """Список категорий в меню проекта."""
    builder = InlineKeyboardBuilder()
    for c in categories_with_counts:
        cnt = c.get("count", 0)
        text = f"📁 {c['name']} ({cnt})" if cnt else f"📁 {c['name']}"
        if len(text) > 60:
            text = text[:58] + "…"
        builder.button(text=text, callback_data=f"pmat:cat:{c['id']}")
    if total_count is not None:
        builder.button(text=f"📂 Все материалы ({total_count})",
                       callback_data="pmat:all")
    builder.button(text="➕ Новый материал", callback_data=add_cb)
    builder.button(text="➕ Новая категория", callback_data="pmat:new_cat")
    builder.button(text="🔙", callback_data=back_cb)
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def project_materials_kb(materials, category_filter=None):
    builder = InlineKeyboardBuilder()
    for m in materials:
        text = m["name"][:50]
        if len(m["name"]) > 50:
            text += "…"
        builder.button(text=text, callback_data=f"pmat:view:{m['id']}")
    builder.button(text="➕ Добавить материал", callback_data="pmat:add")
    builder.button(text="🔙 К категориям", callback_data="pmat:list")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def material_card_ext_kb(material_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="📜 Паспорта / сертификаты",
                   callback_data=f"pmat:certs:{material_id}")
    builder.button(text="✏️ Переименовать",
                   callback_data=f"pmat:edit:{material_id}")
    builder.button(text="📁 Перенести в категорию",
                   callback_data=f"pmat:move:{material_id}")
    builder.button(text="🗑 Удалить материал",
                   callback_data=f"pmat:del:{material_id}")
    builder.button(text="🔙 К материалам", callback_data="pmat:list")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def move_material_category_kb(material_id, categories,
                               current_category_id=None):
    builder = InlineKeyboardBuilder()
    for cat in categories:
        if cat["id"] == current_category_id:
            continue
        text = f"📁 {cat['name']}"
        if len(text) > 60:
            text = text[:58] + "…"
        builder.button(text=text,
                       callback_data=f"pmat:move_to:{material_id}:{cat['id']}")
    if current_category_id is not None:
        builder.button(text="🚫 Без категории",
                       callback_data=f"pmat:move_to:{material_id}:0")
    builder.button(text="🔙 К материалу",
                   callback_data=f"pmat:view:{material_id}")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def material_add_category_kb(categories, back_cb="pmat:list",
                             cb_prefix="pmat:new_in_cat"):
    builder = InlineKeyboardBuilder()
    for cat in categories:
        text = f"📁 {cat['name']}"
        if len(text) > 60:
            text = text[:58] + "…"
        builder.button(text=text,
                       callback_data=f"{cb_prefix}:{cat['id']}")
    builder.button(text="🚫 Без категории",
                   callback_data=f"{cb_prefix}:0")
    builder.button(text="🔙", callback_data=back_cb)
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def project_certs_kb(material_id, certs):
    builder = InlineKeyboardBuilder()
    for c in certs:
        label = f"№{c['number']}"
        if c.get("date_from"):
            label += f" от {c['date_from']}"
        builder.button(text="🗑 " + label, callback_data=f"pcert:del:{c['id']}")
    builder.button(text="➕ Добавить документ",
                   callback_data=f"pcert:add:{material_id}")
    builder.button(text="🔙 К материалу",
                   callback_data=f"pmat:view:{material_id}")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def material_add_doc_ask_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📜 Да, добавить документ",
                   callback_data="mat_add_doc_yes")
    builder.button(text="⏭ Нет, потом",
                   callback_data="mat_add_doc_no")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  БАЗОВЫЕ ПРОЧИЕ
# =====================================================================

def back_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙", callback_data="back")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def cancel_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="❌", callback_data="cancel")
    return builder.as_markup()


def draft_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="⏸ Отложить", callback_data="na:draft")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def draft_after_number_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="⏸ Отложить", callback_data="na:draft")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


# =====================================================================
#  ШАГИ NEWACT
# =====================================================================

def step_with_back_and_delete_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="⏸ Отложить", callback_data="na:draft")
    builder.button(text="🔙 Назад", callback_data="na:back")
    builder.button(text="🗑 Удалить акт", callback_data="na:del")
    builder.adjust(2, 1)
    return builder.as_markup()


def step_only_delete_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="⏸ Отложить", callback_data="na:draft")
    builder.button(text="🗑 Удалить акт", callback_data="na:del")
    builder.adjust(2)
    return builder.as_markup()


def delete_confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить акт", callback_data="na:del_yes")
    builder.button(text="↩ Продолжить", callback_data="na:del_no")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  СЕРТИФИКАТЫ
# =====================================================================

def cert_choice_kb(saved_certs):
    builder = InlineKeyboardBuilder()
    for c in saved_certs[:5]:
        label = f"№{c['number']}"
        if c.get("date_from"):
            label += f" от {c['date_from']}"
        if len(label) > 60:
            label = label[:58] + "…"
        builder.button(text=label, callback_data=f"cert_pick:{c['id']}")
    builder.button(text="📝 Ввести новый", callback_data="cert_new")
    builder.button(text="⏭ Без сертификата", callback_data="cert_skip")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cert_save_ask_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📌 Сохранить для будущих актов",
                   callback_data="cert_save_yes")
    builder.button(text="💤 Только для этого акта",
                   callback_data="cert_save_no")
    builder.adjust(1)
    return builder.as_markup()


def cert_type_choice_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 Паспорт качества",
                   callback_data="cert_type:passport_quality")
    builder.button(text="📋 Сертификат качества",
                   callback_data="cert_type:cert_quality")
    builder.button(text="✔️ Сертификат соответствия",
                   callback_data="cert_type:cert_conformity")
    builder.button(text="✏️ Свой вариант",
                   callback_data="cert_type:custom")
    builder.button(text="⏭ Без типа",
                   callback_data="cert_type:skip")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  ЧЕРТЕЖИ
# =====================================================================

def drawing_view_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📎 Открыть этот файл", callback_data="drw:open")
    builder.button(text="📂 Все чертежи позиции", callback_data="drw:all")
    builder.button(text="✏️ Без PDF (только листы)", callback_data="drw:manual")
    builder.button(text="🔙 Назад", callback_data="na:back")
    builder.button(text="🗑 Удалить акт", callback_data="na:del")
    builder.adjust(1, 1, 1, 2)
    return builder.as_markup()


def drawings_list_kb(drawings):
    builder = InlineKeyboardBuilder()
    for d in drawings:
        text = f"📂 {d['section']} · {d['cipher']}"
        if len(text) > 60:
            text = text[:58] + "…"
        builder.button(text=text, callback_data=f"drwpick:{d['id']}")
    builder.button(text="🔙 Назад", callback_data="na:back")
    builder.button(text="🗑 Удалить акт", callback_data="na:del")
    builder.adjust(1, 2)
    return builder.as_markup()


# =====================================================================
#  ПРЕДПРОСМОТР АКТА
# =====================================================================

def act_preview_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="na:confirm")
    builder.button(text="✏️ Изменить", callback_data="na:edit")
    builder.button(text="⏸ Отложить", callback_data="na:draft")
    builder.button(text="🗑 Удалить акт", callback_data="na:del")
    builder.adjust(1)
    return builder.as_markup()


def act_edit_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔢 Номер акта", callback_data="nae:number")
    builder.button(text="📍 Позиция", callback_data="nae:position")
    builder.button(text="🔨 Тип работы", callback_data="nae:work_type")
    builder.button(text="📝 Наименование работы", callback_data="nae:work_name")
    builder.button(text="📐 Чертёж / раздел", callback_data="nae:drawing")
    builder.button(text="📄 Листы", callback_data="nae:sheets")
    builder.button(text="📦 Материалы", callback_data="nae:materials")
    builder.button(text="📅 Даты", callback_data="nae:dates")
    builder.button(text="🔙 Назад к итогу", callback_data="na:back")
    builder.button(text="🗑 Удалить акт", callback_data="na:del")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  МОИ АКТЫ
# =====================================================================

def my_acts_categories_kb(counts, object_name):
    builder = InlineKeyboardBuilder()
    ready = counts.get("ready", 0)
    printed = counts.get("printed", 0)
    draft = counts.get("draft", 0)
    builder.button(text=f"🆕 Готовые ({ready})", callback_data="myacts:ready")
    builder.button(text=f"🖨 История ({printed})", callback_data="myacts:printed")
    builder.button(text=f"✏️ Недоделанные ({draft})", callback_data="myacts:draft")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def acts_list_kb(acts, prefix):
    builder = InlineKeyboardBuilder()
    for a in acts:
        text = act_label(a)
        if len(text) > 60:
            text = text[:58] + "…"
        builder.button(text=text, callback_data=f"{prefix}:{a['id']}")
    builder.button(text="🔙", callback_data="myacts:menu")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def act_card_kb(act):
    builder = InlineKeyboardBuilder()
    act_id = act["id"]
    status = act.get("status") or "ready"
    if status == "draft":
        builder.button(text="▶️ Продолжить", callback_data=f"act_cont:{act_id}")
        builder.button(text="🗑 Удалить", callback_data=f"act_del:{act_id}")
    elif status == "ready":
        builder.button(text="🖨 Распечатать", callback_data=f"act_print:{act_id}")
        builder.button(text="✏️ Редактировать", callback_data=f"edit_act:{act_id}")
        builder.button(text="📄 Скачать .docx", callback_data=f"act_dl:{act_id}")
        builder.button(text="🗑 Удалить", callback_data=f"act_del:{act_id}")
    else:
        builder.button(text="↩ Вернуть в работу", callback_data=f"act_unprint:{act_id}")
        builder.button(text="✏️ Редактировать", callback_data=f"edit_act:{act_id}")
        builder.button(text="📄 Скачать .docx", callback_data=f"act_dl:{act_id}")
        builder.button(text="🗑 Удалить", callback_data=f"act_del:{act_id}")
    builder.button(text="🔙 К списку", callback_data=f"act_back:{status}")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def act_delete_confirm_kb(act_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить",
                   callback_data=f"act_del_yes:{act_id}")
    builder.button(text="↩ Отмена", callback_data=f"act_del_no:{act_id}")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  ПРОЕКТ
# =====================================================================

def project_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Название объекта", callback_data="pj:name")
    builder.button(text="👥 Генподрядчик", callback_data="pj:gen")
    builder.button(text="👥 Субподрядчик", callback_data="pj:subgen")
    builder.button(text="🔍 Госстройнадзор", callback_data="pj:tech")
    builder.button(text="🎨 Авторский надзор", callback_data="pj:author")
    builder.button(text="🏢 Проектировщик", callback_data="pj:designer")
    builder.button(text="🛡 Работы с автнадзором", callback_data="pj:author_works")
    builder.button(text="📦 Материалы и паспорта", callback_data="pj:materials")
    builder.button(text="📂 Пересканировать проект", callback_data="pj:rescan")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def project_person_kb(prefix):
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Должность", callback_data=f"{prefix}:post")
    builder.button(text="🏢 Организация", callback_data=f"{prefix}:place")
    builder.button(text="👤 ФИО", callback_data=f"{prefix}:name")
    builder.button(text="🔙 К проекту", callback_data="pj:menu")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def project_author_works_kb(all_works, selected):
    builder = InlineKeyboardBuilder()
    for w in all_works:
        prefix = "✅ " if w["name"] in selected else "⬜ "
        builder.button(text=prefix + w["name"][:55],
                       callback_data=f"paw:toggle:{w['id']}")
    builder.button(text="✅ Готово", callback_data="paw:done")
    builder.button(text="🔙 К проекту", callback_data="pj:menu")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  SETUP
# =====================================================================

def setup_confirm_scan_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Всё на месте", callback_data="setup:scan_ok")
    builder.button(text="🔄 Пересканировать", callback_data="setup:scan_again")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def setup_skip_kb(step):
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить", callback_data=f"setup:skip:{step}")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def setup_works_kb(all_works, selected):
    builder = InlineKeyboardBuilder()
    for w in all_works:
        prefix = "✅ " if w["name"] in selected else "⬜ "
        builder.button(text=prefix + w["name"][:55],
                       callback_data=f"setup:aw:{w['id']}")
    builder.button(text="✅ Готово", callback_data="setup:aw_done")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  ЦИКЛЫ
# =====================================================================

def cycles_kb(cycles, owner_tg_id=None):
    builder = InlineKeyboardBuilder()
    for c in cycles:
        prefix = "📝 " if c.get("owner_tg_id") else "⭐ "
        text = f"{prefix}{c['name']} ({c['items_count']})"
        if len(text) > 60:
            text = text[:58] + "…"
        builder.button(text=text, callback_data=f"cyc:{c['id']}")
    builder.button(text="➕ Создать свой цикл", callback_data="cyce:new")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cycle_view_kb(cycle_id, items_count, is_owner=False, is_default=False):
    builder = InlineKeyboardBuilder()
    builder.button(text=f"▶️ Создать {items_count} актов",
                   callback_data=f"cyc_run:{cycle_id}")
    if is_owner or not is_default:
        builder.button(text="✏️ Редактировать цикл",
                       callback_data=f"cyce:menu:{cycle_id}")
    if not is_owner:
        builder.button(text="📄 Скопировать в свои",
                       callback_data=f"cyc_copy:{cycle_id}")
    if is_owner:
        builder.button(text="🗑 Удалить цикл",
                       callback_data=f"cyce:del:{cycle_id}")
    builder.button(text="🔙 К списку циклов",
                   callback_data="cyc_back_list")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cycle_edit_menu_kb(cycle_id, is_owner):
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить работу",
                   callback_data=f"cyce:add_item:{cycle_id}")
    builder.button(text="📝 Переименовать цикл",
                   callback_data=f"cyce:rename:{cycle_id}")
    builder.button(text="📋 Изменить описание",
                   callback_data=f"cyce:desc:{cycle_id}")
    builder.button(text="🔀 Управление работами",
                   callback_data=f"cyce:manage:{cycle_id}")
    builder.button(text="🔙 К циклу", callback_data=f"cyc:{cycle_id}")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cycle_manage_items_kb(items):
    builder = InlineKeyboardBuilder()
    for it in items:
        builder.button(
            text=f"{it['order_num']}. {it['work_type'][:45]}",
            callback_data=f"cyci:edit:{it['id']}",
        )
    builder.button(text="🔙 К редактированию", callback_data="cyce:back_menu")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cycle_item_manage_kb(item_id, total_items, order_num):
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить шаблон",
                   callback_data=f"cyci:tmpl:{item_id}")
    builder.button(text="✏️ Изменить тип работы",
                   callback_data=f"cyci:wt:{item_id}")
    if order_num > 1:
        builder.button(text="⬆️ Вверх", callback_data=f"cyci:up:{item_id}")
    if order_num < total_items:
        builder.button(text="⬇️ Вниз", callback_data=f"cyci:down:{item_id}")
    if total_items > 1:
        builder.button(text="🗑 Удалить шаг", callback_data=f"cyci:del:{item_id}")
    builder.button(text="🔙 К списку", callback_data="cyce:back_manage")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def step_template_kb():
    from db import STEP_TEMPLATES
    builder = InlineKeyboardBuilder()
    for tmpl in STEP_TEMPLATES:
        builder.button(text=tmpl, callback_data=f"tmpl:{tmpl}")
    builder.button(text="✏️ Свой шаблон", callback_data="tmpl:custom")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cycle_confirm_delete_kb(cycle_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить",
                   callback_data=f"cyce:del_confirm:{cycle_id}")
    builder.button(text="↩ Отмена", callback_data=f"cyc:{cycle_id}")
    builder.adjust(1)
    return builder.as_markup()


def cycle_items_kb(items, prefix):
    builder = InlineKeyboardBuilder()
    for it in items:
        builder.button(
            text=f"{it['order_num']}. {it['work_type']}",
            callback_data=f"{prefix}:{it['id']}",
        )
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cycle_section_kb(sections):
    builder = InlineKeyboardBuilder()
    for sec in sections:
        builder.button(text=f"📂 {sec}", callback_data=f"csec:{sec}")
    builder.button(text="⏭ Без чертежа", callback_data="csec:none")
    builder.button(text="🔙 К датам", callback_data="item_back_dates")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def cycle_dates_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Изменить общую часть",
                   callback_data="item_back_common")
    builder.button(text="❌ Отмена цикла", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cycle_pdf_choice_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📎 Прислать PDF", callback_data="cpdf:send")
    builder.button(text="⏭ Пропустить PDF", callback_data="cpdf:skip")
    builder.button(text="🔙 К датам", callback_data="item_back_dates")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def cycle_sheets_kb(previous_sheets=None):
    builder = InlineKeyboardBuilder()
    if previous_sheets:
        builder.button(
            text=f"📋 Взять прошлые ({previous_sheets})",
            callback_data="use_prev_sheets",
        )
    builder.button(text="🔙 К PDF", callback_data="item_back_pdf")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cycle_sheets_apply_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Применить ко всем", callback_data="sheets_apply_all")
    builder.button(text="📝 Спросить по каждой", callback_data="sheets_per_item")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cycle_item_preview_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать акт", callback_data="preview_create")
    builder.button(text="✏️ Править", callback_data="preview_edit")
    builder.button(text="⏸ Завершить цикл",
                   callback_data="preview_pause")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


# =====================================================================
#  РЕДАКТИРОВАНИЕ АКТА
# =====================================================================

def edit_act_menu_kb(act_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Наименование работы",
                   callback_data=f"ea_name:{act_id}")
    builder.button(text="🔢 Номер акта",
                   callback_data=f"ea_num:{act_id}")
    builder.button(text="📅 Даты работ",
                   callback_data=f"ea_dates:{act_id}")
    builder.button(text="📄 Листы",
                   callback_data=f"ea_sheets:{act_id}")
    builder.button(text="📂 Раздел проекта",
                   callback_data=f"ea_section:{act_id}")
    builder.button(text="📦 Материалы и сертификаты",
                   callback_data=f"ea_materials:{act_id}")
    builder.button(text="💾 Сохранить и пересобрать акт",
                   callback_data=f"ea_save:{act_id}")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def edit_act_menu_back_kb(act_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 К меню акта",
                   callback_data=f"ea_back:{act_id}")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def dates_kb(dates):
    builder = InlineKeyboardBuilder()
    for d in dates:
        date_str = d["act_date"]
        cnt = d["cnt"]
        builder.button(
            text=f"📅 {date_str} — {cnt} акт(ов)",
            callback_data=f"actsdate:{act_date_key(date_str)}",
        )
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def act_date_key(date_str):
    return date_str.replace(".", "_")


def parse_act_date_key(key):
    return key.replace("_", ".")


def acts_of_date_kb(acts):
    builder = InlineKeyboardBuilder()
    for a in acts:
        text = act_label(a)
        if len(text) > 60:
            text = text[:58] + "…"
        builder.button(text=text, callback_data=f"edit_act:{a['id']}")
    builder.button(text="❌", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()