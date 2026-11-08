"""Local Telegram control without a public webhook."""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import Application, AuditEvent, Notification, SessionLocal, Setting, Vacancy, init_db

dp = Dispatcher()
logger = logging.getLogger(__name__)


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
    if setting and setting.value.get("value"):
        reply = "Система на паузе"
    elif not settings.hh_autonomy_enabled:
        reply = "Поиск доступен; автономная отправка откликов выключена"
    else:
        reply = "Система активна"
    await message.answer(reply)


@dp.message(Command("pending"))
async def pending(message: Message):
    if not allowed(message):
        return
    with SessionLocal() as db:
        rows = db.execute(
            select(Application.id, Application.state, Vacancy.title)
            .join(Vacancy, Application.vacancy_id == Vacancy.id)
            .where(Application.state.in_(["NEEDS_HUMAN", "NEEDS_RECONCILIATION"]))
            .order_by(Application.updated_at.desc())
            .limit(10)
        ).all()
    reply = "\n".join(f"#{app_id} · {state} · {title[:80]}" for app_id, state, title in rows)
    await message.answer(reply or "Нет задач, требующих вашего участия")


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


async def notify_pending(bot: Bot) -> None:
    while True:
        try:
            with SessionLocal() as db:
                already_sent = select(Notification.id).where(
                    Notification.application_id == Application.id,
                    Notification.state == Application.state,
                ).exists()
                rows = db.execute(
                    select(Application.id, Application.state, Vacancy.title)
                    .join(Vacancy, Application.vacancy_id == Vacancy.id)
                    .where(Application.state.in_(["NEEDS_HUMAN", "NEEDS_RECONCILIATION"]), ~already_sent)
                    .order_by(Application.updated_at)
                    .limit(10)
                ).all()
                for app_id, state, title in rows:
                    reason = "требуется ваше действие" if state == "NEEDS_HUMAN" else "нужно проверить результат на HH"
                    await bot.send_message(settings.telegram_user_id, f"Отклик #{app_id}: {reason}.\n{title[:120]}")
                    db.add(Notification(application_id=app_id, state=state))
                    db.commit()
        except Exception:
            logger.warning("Could not deliver pending application notification")
        await asyncio.sleep(30)


async def main():
    if not settings.telegram_bot_token or settings.telegram_user_id is None:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_USER_ID")
    init_db()
    bot = Bot(settings.telegram_bot_token)
    notifier = asyncio.create_task(notify_pending(bot))
    try:
        await dp.start_polling(bot)
    finally:
        notifier.cancel()


if __name__ == "__main__":
    asyncio.run(main())
