from datetime import timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import Application, AuditEvent, Setting, Vacancy, utcnow
from .hh import HHClient


def dispatch_one(db: Session, hh: HHClient) -> dict:
    """Send at most one prepared application. Unknown POST outcomes are never retried here."""
    if not settings.hh_autonomy_enabled or not settings.hh_api_verified:
        return {"status": "disabled"}
    pause = db.get(Setting, "paused")
    if pause and pause.value.get("value"):
        return {"status": "paused"}
    now = utcnow()
    local = now.astimezone(ZoneInfo("Europe/Moscow"))
    # The normal window crosses midnight. Extra 02:00–04:00 requires a setting.
    hour = local.hour
    extra = db.get(Setting, "extra_window")
    if not (hour >= 16 or hour < 2 or (hour < 4 and extra and extra.value.get("value"))):
        return {"status": "outside_window"}
    recent = db.scalars(select(Application).where(
        (Application.sent_at >= now - timedelta(seconds=60)) |
        ((Application.state == "CHECKING") & (Application.updated_at >= now - timedelta(seconds=60)))
    )).all()
    daily = db.scalars(select(Application).where(Application.sent_at >= now - timedelta(hours=24))).all()
    if len(recent) >= 3 or len(daily) >= settings.hh_daily_limit:
        return {"status": "rate_limited"}
    app = db.scalar(select(Application).where(Application.state == "READY").order_by(Application.id).with_for_update(skip_locked=True))
    if app is None:
        return {"status": "empty"}
    vacancy = db.get(Vacancy, app.vacancy_id)
    app.state = "CHECKING"
    db.commit()
    try:
        existing = hh.find_application(vacancy.hh_id, app.hh_resume_id)
        if existing:
            app.state = "SENT"
            app.hh_negotiation_id = str(existing.get("id"))
            app.sent_at = now
            db.add(AuditEvent(kind="application_reconciled", payload={"application_id": app.id}))
            db.commit()
            return {"status": "reconciled", "application_id": app.id}
        detail = hh.vacancy(vacancy.hh_id)
        if detail.get("archived"):
            app.state = "CLOSED"
            db.commit()
            return {"status": "closed", "application_id": app.id}
        result = hh.apply(vacancy.hh_id, app.hh_resume_id, app.cover_letter)
        app.state = "SENT"
        app.hh_negotiation_id = str(result.get("id")) if result.get("id") else None
        app.sent_at = utcnow()
        db.add(AuditEvent(kind="application_sent", payload={"application_id": app.id, "hh_result": result}))
        db.commit()
        return {"status": "sent", "application_id": app.id}
    except (httpx.HTTPError, ValueError) as exc:
        app.state = "NEEDS_RECONCILIATION"
        db.add(AuditEvent(kind="application_unknown", payload={"application_id": app.id, "error": str(exc)[:300]}))
        db.commit()
        return {"status": "needs_reconciliation", "application_id": app.id}
