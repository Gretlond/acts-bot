# handlers_common.py
"""
Главное меню и общие команды.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from db import (
    get_all_objects,
    get_next_act_number, get_acts_by_status, get_act_status_counts,
    get_cycles_for_user,
)
from keyboards import (
    main_menu_kb, my_acts_categories_kb, cycles_kb,
    step_only_delete_kb,
)
from states import NewAct, CycleRun

router = Router()


@router.message(Command("new_act"))
@router.message(F.text == "🆕 Новый акт")
async def cmd_new_act(message: Message, state: FSMContext):
    await state.clear()
    objs = get_all_objects()
    if not objs:
        await message.answer("⚠️ Объект не настроен. /start")
        return
    obj = objs[0]
    await state.update_data(object_id=obj["id"])
    next_num = get_next_act_number(obj["id"])
    drafts = get_acts_by_status(obj["id"], "draft", limit=50)
    draft_nums = [a["act_number"] for a in drafts if a.get("act_number")]
    text = f"🔢 Введите номер акта (предлагаю {next_num}):"
    if draft_nums:
        text += ("\n\n⚠️ Есть недоделанные акты: "
                 + ", ".join(f"№{n}" for n in draft_nums[:10]))
    await state.set_state(NewAct.entering_act_number)
    await message.answer(text, reply_markup=step_only_delete_kb())


@router.message(Command("my_acts"))
@router.message(F.text == "📄 Мои акты")
async def cmd_my_acts(message: Message, state: FSMContext):
    await state.clear()
    objs = get_all_objects()
    if not objs:
        await message.answer("⚠️ Объект не настроен. /start")
        return
    obj = objs[0]
    await state.update_data(object_id=obj["id"])
    counts = get_act_status_counts(obj["id"])
    await message.answer(
        f"📄 Мои акты\nОбъект: {obj['name'][:80]}\n\nВыберите категорию:",
        reply_markup=my_acts_categories_kb(counts, obj["name"]),
    )


@router.message(Command("cycles"))
@router.message(F.text == "📋 Циклы работ")
async def cmd_cycles(message: Message, state: FSMContext):
    await state.clear()
    tg_id = message.from_user.id if message.from_user else None
    cycles = get_cycles_for_user(tg_id)
    if not cycles:
        await message.answer("⚠️ В БД нет циклов. Запустите seed_cycles.py.",
                             reply_markup=main_menu_kb())
        return
    await state.set_state(CycleRun.choosing_cycle)
    await message.answer("📋 Выберите цикл работ:",
                         reply_markup=cycles_kb(cycles, tg_id))


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    user = message.from_user
    if not user:
        return
    await message.answer(
        "🆔 Ваш Telegram ID:\n"
        f"{user.id}\n\n"
        "Добавьте его в .env:\n"
        f"ADMIN_IDS={user.id}\n"
        "или\n"
        f"ALLOWED_USER_IDS={user.id}"
    )


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Как работать:\n"
        "🆕 Новый акт — пошаговое создание\n"
        "📋 Циклы работ — группа типовых актов\n"
        "📄 Мои акты — готовые / история / недоделанные\n"
        "🏗 Проект — объект, представители, материалы\n\n"
        "Свои циклы можно создавать и редактировать.\n"
        "🆔 /myid — узнать свой Telegram ID.",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=main_menu_kb())


@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text("❌ Действие отменено.")
    except Exception:
        await call.message.answer("❌ Действие отменено.")
    await call.answer()
    await call.message.answer("Выбери действие:", reply_markup=main_menu_kb())