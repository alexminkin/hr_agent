"""Local Telegram control without a public webhook."""
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.orm import Session

from .config import settings
from .db import AuditEvent, SessionLocal, Setting, init_db

dp = Dispatcher()


def allowed(message: Message) -> bool:
    return settings.telegram_user_id is not None and message.from_user is not None and message.from_user.id == settings.telegram_user_id


def set_pause(value: bool, db: Session) -> None:
    db.merge(Setting(key="paused", value={"value": value}))
    db.add(AuditEvent(kind="paused" if value else "resumed", payload={"via": "telegram"}))
    db.commit()


@dp.message(Command("start", "status"))
async def status(message: Message):
    if not allowed(message):
        return
    with SessionLocal() as db:
        setting = db.get(Setting, "paused")
    await message.answer("Система на паузе" if setting and setting.value.get("value") else "Система активна")


@dp.message(Command("pause", "stop"))
async def pause(message: Message):
    if not allowed(message):
        return
    with SessionLocal() as db:
        set_pause(True, db)
    await message.answer("Новые внешние действия остановлены")


@dp.message(Command("resume"))
async def resume(message: Message):
    if not allowed(message):
        return
    with SessionLocal() as db:
        set_pause(False, db)
    await message.answer("Работа возобновлена")


async def main():
    if not settings.telegram_bot_token or settings.telegram_user_id is None:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_USER_ID")
    init_db()
    bot = Bot(settings.telegram_bot_token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
