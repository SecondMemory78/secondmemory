from datetime import date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select
from ..db import get_session
from ..services.consent import require_consent
from ..services.telemetry import log_event
from ..deps import current_doctor_id
from ..deps import get_owned_patient
from ..reference_data import parameter_label
from ..services.visits import active_encounter_id
from ..models import VisitProtocol, Patient, Observation, SafetyItem
from ..schemas import ProtocolIn

router = APIRouter(prefix="/api/patients", tags=["protocol"])

# Читаемые названия параметров для блока «Объективно»


@router.get("/{pid}/protocol")
def get_protocol(pid: int, s: Session = Depends(get_session)):
    p = get_owned_patient(s, pid)                # чужой/несуществующий пациент → 404
    row = s.exec(select(VisitProtocol).where(VisitProtocol.patient_id == pid)).first()
    if row:
        return row.model_dump()
    # черновик, собранный из данных пациента
    return _draft(s, p)


@router.put("/{pid}/protocol")
def save_protocol(pid: int, body: ProtocolIn, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                     # сначала владелец (чужой/нет → 404), потом согласие
    require_consent(s, pid)
    row = s.exec(select(VisitProtocol).where(VisitProtocol.patient_id == pid)).first()
    if row:
        for k, v in body.model_dump().items():
            setattr(row, k, v)
    else:
        row = VisitProtocol(patient_id=pid, encounter_id=active_encounter_id(s, pid), **body.model_dump())
    s.add(row); s.commit(); s.refresh(row)
    dump = row.model_dump()
    log_event(s, "protocol.saved", {}, current_doctor_id())
    return dump


def _draft(s: Session, p: Patient):
    # Объективно: последние подтверждённые значения ключевых показателей
    obs = s.exec(select(Observation).where(Observation.patient_id == p.id,
                                           Observation.status == "confirmed")).all()
    latest = {}
    for o in obs:
        if o.value_num is None:
            continue
        cur = latest.get(o.parameter_code)
        if not cur or (o.effective_date or date.min) > (cur.effective_date or date.min):
            latest[o.parameter_code] = o
    parts = []
    for code, o in latest.items():
        parts.append(f"{parameter_label(code)} {o.value_num} {o.unit}".strip())
    objective = ("По данным обследования: " + "; ".join(parts) + ".") if parts else ""

    return {
        "patient_id": p.id,
        "complaints": "",
        "anamnesis_morbi": "",
        "anamnesis_vitae": "",
        "objective": objective,
        "status_localis": "",
        "diagnosis_code": p.diagnosis_code or "",
        "diagnosis_text": p.diagnosis_text or "",
        "recommendations": "",
        "_draft": True,
    }


@router.post("/{pid}/protocol/dictate")
async def dictate_protocol(pid: int, audio: UploadFile = File(None),
                           audio_format: str = Form(""), text: str = Form(""),
                           s: Session = Depends(get_session)):
    """Диктовка протокола: раскладываем по разделам и ВОЗВРАЩАЕМ предпросмотр.

    Ничего не сохраняем: по «Структуре консультации» результат разбора должен
    быть показан врачу и подтверждён им. Пустые разделы остаются пустыми —
    отсутствие данных не равно норме.
    """
    get_owned_patient(s, pid)                    # чужой/несуществующий → 404
    require_consent(s, pid)

    said = (text or "").strip()
    if not said and audio is not None:
        from ..services.stt import transcribe
        from ..services.usage import meter
        meter(s, current_doctor_id(), "stt", detail="protocol")
        data = await audio.read()
        said = transcribe(data, audio_format)
    if not said:
        raise HTTPException(400, "Нечего разбирать: пустая диктовка")

    from ..services.protocol_dictation import parse
    from ..services.telemetry import log_event
    out = parse(said)
    log_event(s, "protocol.dictated", {"source": out["source"],
                                       "sections": len(out["sections"])},
              current_doctor_id())
    return out
