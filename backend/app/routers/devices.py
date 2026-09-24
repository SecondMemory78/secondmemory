from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import date
from typing import Optional
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id, get_owned_patient
from ..models import Device

router = APIRouter(prefix="/api/patients", tags=["devices"])

KINDS = {"catheter", "stent", "nephrostomy"}


class DeviceIn(BaseModel):
    kind: str
    device_label: str = ""
    installed_at: Optional[date] = None
    due_at: Optional[date] = None            # None → «срок не задан»
    note: str = ""


def _dump(d: Device) -> dict:
    return {
        "id": d.id, "kind": d.kind, "device_label": d.device_label, "active": d.active,
        "installed_at": d.installed_at.isoformat() if d.installed_at else None,
        "due_at": d.due_at.isoformat() if d.due_at else None,
        "closed_at": d.closed_at.isoformat() if d.closed_at else None,
        "closed_action": d.closed_action, "note": d.note, "version": d.version,
    }


@router.get("/{pid}/devices")
def list_devices(pid: int, s: Session = Depends(get_session)):
    """Устройства пациента: активные и закрытые (историю не прячем)."""
    get_owned_patient(s, pid)                 # чужой/несуществующий пациент → 404
    rows = s.exec(select(Device).where(Device.patient_id == pid)
                  .order_by(Device.active.desc(), Device.id.desc())).all()
    return {"items": [_dump(d) for d in rows]}


@router.post("/{pid}/devices")
def add_device(pid: int, body: DeviceIn, s: Session = Depends(get_session)):
    """Завести устройство пациенту."""
    get_owned_patient(s, pid)                 # чужой/несуществующий пациент → 404
    if body.kind not in KINDS:
        raise HTTPException(400, "Неизвестный тип устройства")
    d = Device(doctor_id=current_doctor_id(), patient_id=pid, kind=body.kind,
               device_label=body.device_label, installed_at=body.installed_at,
               due_at=body.due_at, note=body.note)
    s.add(d); s.commit(); s.refresh(d)
    return _dump(d)


def _get_owned_device(s: Session, did: int) -> Device:
    """Устройство текущего врача, иначе 404 (не раскрываем чужие)."""
    d = s.get(Device, did)
    if not d or d.doctor_id != current_doctor_id():
        raise HTTPException(404, "Устройство не найдено")
    return d


class CloseIn(BaseModel):
    action: str = "removed"                  # removed | replaced
    closed_at: Optional[date] = None         # дата действия; по умолчанию сегодня
    expected_version: Optional[int] = None   # защита от одновременного изменения


class ReplaceIn(BaseModel):
    closed_at: Optional[date] = None         # когда заменено (у старого)
    expected_version: Optional[int] = None
    # параметры НОВОГО устройства (того же пациента):
    kind: Optional[str] = None               # по умолчанию — тот же тип
    device_label: str = ""
    installed_at: Optional[date] = None
    due_at: Optional[date] = None
    note: str = ""


@router.post("/{pid}/devices/{did}/close")
def close_device(pid: int, did: int, body: CloseIn = CloseIn(), s: Session = Depends(get_session)):
    """Удаление/закрытие КОНКРЕТНОГО устройства. Другие активные устройства не трогаются."""
    from .. import clock
    get_owned_patient(s, pid)
    d = _get_owned_device(s, did)
    if d.patient_id != pid:
        raise HTTPException(404, "Устройство не найдено")
    if not d.active:
        raise HTTPException(409, "Устройство уже закрыто")
    if body.expected_version is not None and body.expected_version != d.version:
        raise HTTPException(409, "Устройство изменено в другом месте — обновите данные")
    if body.action not in {"removed", "replaced"}:
        raise HTTPException(400, "Недопустимое действие")
    d.active = False
    d.closed_action = body.action
    d.closed_at = body.closed_at or clock.today()
    d.version += 1
    s.add(d); s.commit(); s.refresh(d)
    return _dump(d)


@router.post("/{pid}/devices/{did}/replace")
def replace_device(pid: int, did: int, body: ReplaceIn, s: Session = Depends(get_session)):
    """Замена КОНКРЕТНОГО устройства: старое закрывается (replaced), новое заводится
    отдельной записью со своим сроком. Прочие активные устройства не затрагиваются."""
    from .. import clock
    get_owned_patient(s, pid)
    old = _get_owned_device(s, did)
    if old.patient_id != pid:
        raise HTTPException(404, "Устройство не найдено")
    if not old.active:
        raise HTTPException(409, "Устройство уже закрыто")
    if body.expected_version is not None and body.expected_version != old.version:
        raise HTTPException(409, "Устройство изменено в другом месте — обновите данные")
    new_kind = body.kind or old.kind
    if new_kind not in KINDS:
        raise HTTPException(400, "Неизвестный тип устройства")
    # закрыть старое
    old.active = False
    old.closed_action = "replaced"
    old.closed_at = body.closed_at or clock.today()
    old.version += 1
    s.add(old)
    # завести новое
    new = Device(doctor_id=current_doctor_id(), patient_id=pid, kind=new_kind,
                 device_label=body.device_label, installed_at=body.installed_at or clock.today(),
                 due_at=body.due_at, note=body.note)
    s.add(new); s.commit(); s.refresh(new); s.refresh(old)
    return {"closed": _dump(old), "new": _dump(new)}
