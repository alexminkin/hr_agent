from datetime import timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .browser import BrowserNeedsReview, BrowserUnavailable
from .db import Application, AuditEvent, JobAttempt, Setting, Vacancy, utcnow
from .routing import HHOperationRouter, OperationBlocked, OperationUnknown


def dispatch_one(db: Session, hh: HHOperationRouter) -> dict:
    """Send at most one prepared application. Unknown POST outcomes are never retried here."""
    now = utcnow()
    # A crash while CHECKING must not put the same application back into READY.
    stale = db.scalars(select(Application).where(
        (Application.state == "CHECKING") &
        (Application.updated_at < now - timedelta(minutes=2))
    ).limit(100)).all()
    for item in stale:
        item.state = "NEEDS_RECONCILIATION"
        db.add(AuditEvent(kind="application_interrupted", payload={"application_id": item.id}))
    if stale:
        db.commit()
    if not settings.hh_autonomy_enabled:
        return {"status": "disabled"}
    pause = db.get(Setting, "paused")
    if pause and pause.value.get("value"):
        return {"status": "paused"}
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
    attempt = JobAttempt(application_id=app.id, operation="apply", state="CHECKING")
    db.add(attempt)
    db.commit()
    try:
        existing = hh.find_application(vacancy.hh_id, app.hh_resume_id)
        if existing:
            if not existing.get("id"):
                raise OperationUnknown("Existing HH application has no confirmed id")
            app.state = "SENT"
            app.hh_negotiation_id = str(existing.get("id"))
            app.sent_at = now
            attempt.channel = hh.last_channel
            attempt.state = "RECONCILED"
            db.add(AuditEvent(kind="application_reconciled", payload={"application_id": app.id}))
            db.commit()
            return {"status": "reconciled", "application_id": app.id}
        detail = hh.vacancy(vacancy.hh_id)
        if detail.get("archived"):
            app.state = "CLOSED"
            attempt.channel = hh.last_channel
            attempt.state = "CLOSED"
            db.commit()
            return {"status": "closed", "application_id": app.id}
        result = hh.apply(vacancy.hh_id, app.hh_resume_id, app.cover_letter)
        if not result.get("id"):
            raise OperationUnknown("HH did not return a confirmed application id")
        app.state = "SENT"
        app.hh_negotiation_id = str(result.get("id")) if result.get("id") else None
        app.sent_at = utcnow()
        attempt.channel = hh.last_channel
        attempt.state = "CONFIRMED"
        db.add(AuditEvent(kind="application_sent", payload={"application_id": app.id, "hh_result": result}))
        db.commit()
        return {"status": "sent", "application_id": app.id}
    except (BrowserNeedsReview, BrowserUnavailable, OperationBlocked) as exc:
        app.state = "NEEDS_HUMAN"
        attempt.channel = hh.last_channel
        attempt.state = "BLOCKED"
        attempt.error = str(exc)[:300]
        db.add(AuditEvent(kind="application_blocked", payload={"application_id": app.id, "error": str(exc)[:300]}))
        db.commit()
        return {"status": "needs_human", "application_id": app.id}
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        app.state = "NEEDS_RECONCILIATION"
        attempt.channel = hh.last_channel
        attempt.state = "UNKNOWN"
        attempt.error = str(exc)[:300]
        db.add(AuditEvent(kind="application_unknown", payload={"application_id": app.id, "error": str(exc)[:300]}))
        db.commit()
        return {"status": "needs_reconciliation", "application_id": app.id}
