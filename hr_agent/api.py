from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .applications import dispatch_one
from .browser import BrowserNeedsReview, BrowserUnavailable
from .config import settings
from .db import AuditEvent, SessionLocal, Setting, Vacancy, init_db
from .routing import HHOperationRouter, OperationBlocked


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="HR multi-agent core", lifespan=lifespan)


def authorized(x_admin_token: str = Header(default="")) -> None:
    if not settings.app_admin_token or x_admin_token != settings.app_admin_token:
        raise HTTPException(401, "unauthorized")


def session():
    with SessionLocal() as db:
        yield db


class SearchRequest(BaseModel):
    text: str
    pages: int = 1


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/search", dependencies=[Depends(authorized)])
def search(request: SearchRequest, db: Session = Depends(session)):
    if not 1 <= request.pages <= 20:
        raise HTTPException(400, "pages out of range")
    hh = HHOperationRouter()
    count = 0
    for page in range(request.pages):
        try:
            items = hh.search(request.text, page).get("items", [])
        except (OperationBlocked, BrowserNeedsReview, BrowserUnavailable) as exc:
            raise HTTPException(503, str(exc)) from exc
        for row in items:
            hh_id = str(row["id"])
            if db.scalar(select(Vacancy).where(Vacancy.hh_id == hh_id)):
                continue
            db.add(Vacancy(hh_id=hh_id, title=row["name"], url=row["alternate_url"], raw={**row, "source_channel": hh.last_channel}))
            count += 1
    db.commit()
    return {"new_vacancies": count}


@app.post("/dispatch", dependencies=[Depends(authorized)])
def dispatch(db: Session = Depends(session)):
    return dispatch_one(db, HHOperationRouter())


@app.post("/pause", dependencies=[Depends(authorized)])
def pause(db: Session = Depends(session)):
    db.merge(Setting(key="paused", value={"value": True}))
    db.add(AuditEvent(kind="paused", payload={}))
    db.commit()
    return {"paused": True}


@app.post("/resume", dependencies=[Depends(authorized)])
def resume(db: Session = Depends(session)):
    db.merge(Setting(key="paused", value={"value": False}))
    db.add(AuditEvent(kind="resumed", payload={}))
    db.commit()
    return {"paused": False}
