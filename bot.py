# bot.py
import asyncio
import logging

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from config import (
    ACCESS_OPEN, ALLOWED_USER_IDS, ALLOW_ANY_USER, BOT_TOKEN,
    ensure_dirs, is_user_allowed,
)
from db import init_db
from handlers import router
from project_handlers import router as project_router
from handlers_common import router as common_router
from handlers_certs import router as certs_router
from handlers_materials import router as materials_router
from handlers_cycles import router as cycles_router
from handlers_my_acts import router as my_acts_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден. Создайте файл .env в корне проекта "
        "со строкой: BOT_TOKEN=ваш_токен"
    )

bot = Bot(token=BOT_TOKEN, request_timeout=300)
dp = Dispatcher(storage=MemoryStorage())


class LogMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            if hasattr(event, "text") and event.text:
                print(f"📥 TEXT: {event.text!r}")
            elif hasattr(event, "data") and event.data:
                print(f"📥 CALLBACK: {event.data!r}")
        except Exception:
            pass
        return await handler(event, data)


class AccessMiddleware(BaseMiddleware):
    """Пускать в бота только пользователей из ALLOWED_USER_IDS/ADMIN_IDS."""

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if is_user_allowed(user.id if user else None):
            return await handler(event, data)

        user_id = user.id if user else "не определён"
        logger.warning(
            "Отказ доступа: id=%s username=%s",
            user_id, getattr(user, "username", None),
        )
        if isinstance(event, CallbackQuery):
            await event.answer(
                f"⛔ Доступ запрещён. Ваш ID: {user_id}",
                show_alert=True,
            )
        elif isinstance(event, Message):
            await event.answer(
                "⛔ Доступ запрещён.\n\n"
                f"Ваш Telegram ID: {user_id}\n\n"
                "Передайте его администратору и попросите добавить "
                "в ALLOWED_USER_IDS или ADMIN_IDS в файле .env."
            )
        return None


dp.message.middleware(LogMiddleware())
dp.callback_query.middleware(LogMiddleware())
dp.message.middleware(AccessMiddleware())
dp.callback_query.middleware(AccessMiddleware())

# Порядок:
#   1. project_router    — /start, /scan_server, /project
#   2. common_router     — главное меню, /cancel
#   3. certs_router      — сертификаты
#   4. materials_router  — добавление материала «на лету»
#   5. cycles_router     — циклы
#   6. my_acts_router    — Мои акты + редактирование
#   7. router            — NewAct + back + ловушка
dp.include_router(project_router)
dp.include_router(common_router)
dp.include_router(certs_router)
dp.include_router(materials_router)
dp.include_router(cycles_router)
dp.include_router(my_acts_router)
dp.include_router(router)


async def main():
    ensure_dirs()
    # Миграции и создание таблиц при старте (безопасно, IF NOT EXISTS)
    init_db()

    if ACCESS_OPEN:
        logger.warning(
            "⚠️ ALLOW_ANY_USER=1 — бот открыт для всех. "
            "Для продакшена заполните ADMIN_IDS/ALLOWED_USER_IDS в .env."
        )
    elif not ALLOWED_USER_IDS:
        logger.warning(
            "⚠️ ADMIN_IDS/ALLOWED_USER_IDS не заполнены — доступ закрыт. "
            "Запустите бота, отправьте /myid и добавьте ID в .env."
        )
    else:
        logger.info("Доступ разрешён пользователям: %s", sorted(ALLOWED_USER_IDS))

    print("🤖 Бот запущен. Ctrl+C для остановки.")
    me = await bot.get_me()
    print(f"→ @{me.username}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен.")