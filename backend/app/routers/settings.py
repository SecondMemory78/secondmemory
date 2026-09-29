import os
from fastapi import APIRouter, Depends, HTTPException
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


@router.get("/ai-selftest")
def ai_selftest():
    """Самопроверка ИИ-сервисов: что именно отвечает Яндекс.

    В обычной работе ошибки ИИ намеренно проглатываются (приём важнее), поэтому
    при неверном ключе или роли всё выглядит как «ничего не происходит». Здесь
    ошибки показываются как есть. Ключи не выводим. Доступно только в dev-режиме
    (AUTH_OPTIONAL=1), чтобы наружу это не торчало.
    """
    from ..deps import AUTH_OPTIONAL
    if not AUTH_OPTIONAL:
        raise HTTPException(404, "Недоступно")

    from ..services import ai
    import base64, httpx

    out = {"provider": ai.PROVIDER,
           "keys_configured": bool(ai.YANDEX_API_KEY and ai.YANDEX_FOLDER_ID),
           "folder_id": ai.YANDEX_FOLDER_ID or None,
           "key_tail": ("…" + ai.YANDEX_API_KEY[-4:]) if ai.YANDEX_API_KEY else None,
           "checks": {}}

    if ai.PROVIDER != "yandex" or not out["keys_configured"]:
        out["checks"]["_"] = {"ok": False, "reason": "провайдер не yandex или ключи не заданы"}
        return out

    hdr = {"Authorization": f"Api-Key {ai.YANDEX_API_KEY}"}

    def _probe(name, fn):
        try:
            r = fn()
            body = (r.text or "")[:400]
            out["checks"][name] = {"ok": r.status_code == 200, "http": r.status_code,
                                   "response": body if r.status_code != 200 else "ok"}
        except Exception as e:                       # сеть/таймаут/DNS
            out["checks"][name] = {"ok": False, "http": None,
                                   "response": f"{type(e).__name__}: {str(e)[:200]}"}

    # 1) генерация текста (понимание команд)
    _probe("gpt", lambda: httpx.post(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        headers={**hdr, "x-folder-id": ai.YANDEX_FOLDER_ID},
        json={"modelUri": f"gpt://{ai.YANDEX_FOLDER_ID}/"
                          f"{os.getenv('YANDEX_GPT_MODEL', 'yandexgpt-lite')}/latest",
              "completionOptions": {"stream": False, "temperature": 0, "maxTokens": 10},
              "messages": [{"role": "user", "text": "ответь словом: тест"}]},
        timeout=20))

    # 2) распознавание речи — тем же форматом, что шлёт приложение:
    #    сырой LPCM 16 кГц моно (0.3 с тишины). Важно слать именно его:
    #    браузерный webm SpeechKit не принимает.
    pcm = b"\x00\x00" * 4800
    _probe("stt", lambda: httpx.post(
        "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
        params={"folderId": ai.YANDEX_FOLDER_ID, "lang": "ru-RU",
                "format": "lpcm", "sampleRateHertz": "16000"},
        headers=hdr, content=pcm, timeout=20))

    # 3) распознавание документов — картинка нормального размера: 1x1 Vision
    #    не декодирует и отвечает «Can't decode image» (ложная тревога).
    png = _blank_png(64, 64)
    _probe("ocr", lambda: httpx.post(
        "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
        headers={**hdr, "x-folder-id": ai.YANDEX_FOLDER_ID,
                 "x-data-logging-enabled": "false"},
        json={"mimeType": ai._sniff_mime(png), "languageCodes": ["ru", "en"],
              "content": base64.b64encode(png).decode()},
        timeout=20))

    failed = [k for k, v in out["checks"].items() if not v.get("ok")]
    out["summary"] = "всё работает" if not failed else f"не работает: {', '.join(failed)}"
    return out


def _blank_png(w: int, h: int) -> bytes:
    """Белый PNG без внешних зависимостей — для проверки доступности OCR."""
    import struct, zlib
    raw = b"".join(b"\x00" + b"\xff" * (w * 3) for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))
