from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session
from ..db import get_session
from ..deps import current_doctor_id
from ..models import Doctor

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsIn(BaseModel):
    notify_push: bool | None = None
    notify_tracking: bool | None = None
    timezone: str | None = None
    full_name: str | None = None
    specialty: str | None = None


@router.get("")
def get_settings(s: Session = Depends(get_session)):
    d = s.get(Doctor, current_doctor_id())
    if not d:
        return {}
    return {"full_name": d.full_name, "specialty": d.specialty, "email": d.email,
            "timezone": d.timezone, "notify_push": d.notify_push,
            "notify_tracking": d.notify_tracking}


@router.put("")
def update_settings(body: SettingsIn, s: Session = Depends(get_session)):
    d = s.get(Doctor, current_doctor_id())
    if body.notify_push is not None:
        d.notify_push = body.notify_push
    if body.notify_tracking is not None:
        d.notify_tracking = body.notify_tracking
    if body.timezone:
        d.timezone = body.timezone
    if body.full_name:
        d.full_name = body.full_name
    if body.specialty:
        d.specialty = body.specialty
    s.add(d); s.commit()
    return {"ok": True, "notify_push": d.notify_push,
            "notify_tracking": d.notify_tracking, "timezone": d.timezone}
