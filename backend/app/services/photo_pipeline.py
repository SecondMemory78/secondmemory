"""Асинхронный конвейер разбора фото (Вариант C: очередь в БД + тик планировщика).

Загрузка только ставит пакет в очередь (proc_status="queued") и мгновенно отвечает —
запрос НЕ ждёт разбора. Фоновый тик берёт queued-пакеты и обрабатывает: split_photo
→ фрагменты → done. Когда подключат реальный (медленный) Yandex OCR вместо заглушки
split_photo, он встанет сюда без переделки. Персистентно: незавершённые пакеты
остаются queued в БД и переживают рестарт.
"""
import json
import base64
from sqlmodel import Session, select
from ..models import PhotoBatch, PhotoFragment
from ..services.ocr import split_photo
from ..services.usage import meter
import logging

log = logging.getLogger("photo_pipeline")


def process_batch(s: Session, batch: PhotoBatch, notify: bool = False) -> None:
    """Обработать один пакет: split_photo → фрагменты. Меняет proc_status.
    notify=True (для отложенной обработки тиком) — шлём врачу уведомление об исходе;
    при немедленной обработке в запросе (notify=False) не шумим — врач видит результат."""
    if batch.proc_status not in ("queued", "processing"):
        return
    batch.proc_status = "processing"; s.add(batch); s.commit()
    try:
        image_bytes = base64.b64decode(batch.image_b64) if batch.image_b64 else b""
        sim_list = json.loads(batch.sim_json) if batch.sim_json else None
        fragments = split_photo(image_bytes, sim=sim_list)
        # учёт расхода — в момент фактической обработки, а не загрузки
        meter(s, batch.doctor_id, "ocr", units=max(1, len(fragments)), detail="photo-batch")
        existing = s.exec(select(PhotoFragment).where(PhotoFragment.batch_id == batch.id)).first()
        if not existing:
            for fr in fragments:
                nm = fr.get("name", {})
                full = " ".join(x for x in [nm.get("last", ""), nm.get("first", ""), nm.get("middle", "")] if x)
                s.add(PhotoFragment(batch_id=batch.id, doctor_id=batch.doctor_id,
                                    region=json.dumps(fr.get("region", {})),
                                    extracted_name=full, extracted_dob=fr.get("birth_date", ""),
                                    values_json=json.dumps(fr.get("values", []), ensure_ascii=False)))
        batch.proc_status = "done"; batch.proc_error = ""
        s.add(batch); s.commit()
        if notify:
            _notify(s, batch.doctor_id, "ocr", "info",
                    "Фото распознано — проверьте и разнесите по картам.")
    except Exception as e:
        s.rollback()
        batch.proc_status = "failed"; batch.proc_error = str(e)[:300]
        s.add(batch); s.commit()
        log.exception("photo batch %s failed", batch.id)
        if notify:
            _notify(s, batch.doctor_id, "ocr", "warn",
                    "Не удалось распознать фото — нужна пересъёмка (снимок чёткий и полный).")


def _notify(s: Session, doctor_id: int, kind: str, level: str, text: str) -> None:
    """Уведомление в приложении + пуш (если подключён). Не роняет обработку."""
    from ..models import Notification
    try:
        s.add(Notification(doctor_id=doctor_id, kind=kind, level=level, text=text))
        s.commit()
    except Exception:
        s.rollback()
    try:
        from . import push as push_svc
        push_svc.push_to_doctor(s, doctor_id, kind, "Вторая память", text)
    except Exception:
        pass


def process_queued(s: Session, limit: int = 20) -> int:
    """Обработать до limit пакетов в очереди (отложенный путь тиком → с уведомлением).
    Возвращает число обработанных."""
    rows = s.exec(select(PhotoBatch).where(PhotoBatch.proc_status == "queued").limit(limit)).all()
    for b in rows:
        process_batch(s, b, notify=True)
    return len(rows)
