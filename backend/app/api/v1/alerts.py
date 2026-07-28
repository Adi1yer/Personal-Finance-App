from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.recurring_detection import detect_recurring
from app.services.weekly_digest import build_digest, send_weekly_digest

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/weekly-digest")
def get_weekly_digest(db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_digest(db)


@router.post("/weekly-digest/send")
def post_send_digest(db: Session = Depends(get_db)) -> dict[str, Any]:
    return send_weekly_digest(db)


@router.get("/recurring")
def get_recurring(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return detect_recurring(db)
