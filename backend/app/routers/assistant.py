from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel
from sqlmodel import Session
from ..db import get_session
from ..deps import current_doctor_id
from ..services.usage import meter
from ..services.assistant import route_command
from ..services.stt import transcribe
from ..services.telemetry import log_event

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class CommandIn(BaseModel):
    text: str


@router.post("/command")
def command(body: CommandIn, s: Session = Depends(get_session)):
    meter(s, current_doctor_id(), "llm", detail="command")
    res = route_command(body.text, s)
    log_event(s, "assistant.command", {"intent": res.get("intent"), "channel": "text"})
    return res


@router.post("/voice")
async def voice(audio: UploadFile = File(None), s: Session = Depends(get_session)):
    meter(s, current_doctor_id(), "stt", detail="assistant")
    data = await audio.read() if audio else b""
    text = transcribe(data)
    res = route_command(text, s)
    log_event(s, "assistant.command", {"intent": res.get("intent"), "channel": "voice"})
    return {"transcript": text, **res}
