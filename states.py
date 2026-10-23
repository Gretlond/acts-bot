# states.py
from aiogram.fsm.state import State, StatesGroup


class ProjectSetup(StatesGroup):
    waiting_zip = State()
    showing_scan = State()
    entering_object_name = State()
    entering_tech_post = State()
    entering_tech_place = State()
    entering_tech_name = State()
    entering_author_post = State()
    entering_author_place = State()
    entering_author_name = State()
    entering_designer_firm = State()
    entering_designer_date = State()
    choosing_author_works = State()
    entering_new_author_work = State()


class ProjectEdit(StatesGroup):
    menu = State()
    entering_object_name = State()

    entering_gen_post = State()
    entering_gen_firm = State()
    entering_gen_name = State()

    entering_subgen_post = State()
    entering_subgen_firm = State()
    entering_subgen_name = State()

    entering_tech_post = State()
    entering_tech_place = State()
    entering_tech_name = State()

    entering_author_post = State()
    entering_author_place = State()
    entering_author_name = State()

    entering_designer_firm = State()
    entering_designer_date = State()

    choosing_author_works = State()
    entering_new_author_work = State()

    # материалы
    materials_menu = State()
    entering_material_name = State()
    entering_material_qdoc = State()
    entering_material_work_types = State()
    choosing_category_for_new_material = State()
    editing_material_choice = State()
    editing_material_name = State()
    editing_material_qdoc = State()
    deleting_material_choice = State()
    choosing_category_for_move = State()
    material_certs_menu = State()
    entering_cert_doc_type = State()
    entering_cert_doc_type_custom = State()
    entering_cert_number = State()
    entering_cert_date = State()
    deleting_cert_choice = State()

    # категории материалов
    entering_material_category_name = State()
    editing_material_category_name = State()


class NewAct(StatesGroup):
    entering_act_number = State()
    choosing_position = State()
    choosing_work_type = State()
    entering_work_type_new = State()
    entering_work_name = State()
    choosing_section = State()
    viewing_drawing = State()
    viewing_all_drawings = State()
    entering_sheets = State()
    choosing_materials = State()
    choosing_cert = State()
    entering_cert_doc_type = State()
    entering_cert_doc_type_custom = State()
    entering_cert_number = State()
    entering_cert_date = State()
    asking_save_cert = State()
    entering_start_date = State()
    entering_end_date = State()
    final_preview = State()


class CycleRun(StatesGroup):
    choosing_cycle = State()
    viewing_cycle = State()
    entering_cycle_name = State()
    entering_cycle_description = State()
    editing_cycle_name = State()
    editing_cycle_description = State()
    adding_step_work_type = State()
    adding_step_template = State()
    adding_step_custom_template = State()
    viewing_cycle_edit_menu = State()
    choosing_item_to_manage = State()
    editing_item_template = State()
    editing_item_custom_template = State()
    confirming_delete_cycle = State()

    choosing_object = State()
    choosing_position = State()
    entering_common_part = State()

    item_dates = State()
    item_section = State()
    item_pdf_choice = State()
    item_sheets = State()
    item_sheets_apply = State()
    item_materials = State()
    item_cert_choosing = State()
    item_cert_doc_type = State()
    item_cert_doc_type_custom = State()
    item_cert_number = State()
    item_cert_date = State()
    item_cert_asking_save = State()
    item_preview = State()


class MyActs(StatesGroup):
    choosing_category = State()
    choosing_date = State()
    viewing_act = State()


class EditAct(StatesGroup):
    menu = State()
    entering_work_name = State()
    entering_act_number = State()
    entering_act_date = State()
    entering_start_date = State()
    entering_end_date = State()
    entering_sheets = State()
    choosing_section = State()
    choosing_materials = State()
    choosing_cert = State()
    entering_cert_doc_type = State()
    entering_cert_doc_type_custom = State()
    entering_cert_number = State()
    entering_cert_date = State()
    asking_save_cert = State()


class MaterialFromAct(StatesGroup):
    """Добавление нового материала прямо из акта."""
    entering_name = State()
    entering_qdoc = State()
    entering_work_types = State()
    choosing_category = State()
    asking_add_doc = State()