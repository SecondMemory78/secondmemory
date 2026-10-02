from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from sqlmodel import Session
from ..db import get_session
from ..deps import current_doctor_id
from ..services.usage import meter
from ..services.assistant import route_command
from ..services.stt import transcribe
from ..services.telemetry import log_event

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def _deny_in_demo(s: Session):
    """В демо ассистент — витрина: показываем, но не выполняем.
    Демо-аккаунт одноразовый, действия ассистента там не имеют смысла."""
    from ..models import Doctor
    from ..services.demo import is_disposable_demo
    doc = s.get(Doctor, current_doctor_id())
    if is_disposable_demo(doc):
        raise HTTPException(403, "В демо-режиме ассистент недоступен — "
                                 "это витрина. Создайте аккаунт, чтобы пользоваться им.")


class CommandIn(BaseModel):
    text: str


@router.post("/command")
def command(body: CommandIn, s: Session = Depends(get_session)):
    _deny_in_demo(s)
    meter(s, current_doctor_id(), "llm", detail="command")
    res = route_command(body.text, s, channel="text")
    log_event(s, "assistant.command", {"intent": res.get("intent"), "channel": "text"})
    return res


@router.post("/voice")
async def voice(audio: UploadFile = File(None), audio_format: str = Form(""),
                s: Session = Depends(get_session)):
    _deny_in_demo(s)
    meter(s, current_doctor_id(), "stt", detail="assistant")
    data = await audio.read() if audio else b""
    text = transcribe(data, audio_format)
    res = route_command(text, s, channel="voice")
    log_event(s, "assistant.voice", {"intent": res.get("intent")})
    return {"transcript": text, **res}


@router.get("/actions")
def actions(limit: int = 50, s: Session = Depends(get_session)):
    """Журнал действий ассистента для текущего врача — экран «Что сделал ассистент»."""
    from ..models import AssistantAction
    from sqlmodel import select
    rows = s.exec(select(AssistantAction)
                  .where(AssistantAction.doctor_id == current_doctor_id())
                  .order_by(AssistantAction.created_at.desc()).limit(limit)).all()
    return [{"id": a.id, "channel": a.channel, "area": a.area, "intent": a.intent,
             "input_text": a.input_text, "message": a.message,
             "entity_type": a.entity_type, "entity_id": a.entity_id,
             "ok": a.ok, "created_at": a.created_at.isoformat()} for a in rows]
