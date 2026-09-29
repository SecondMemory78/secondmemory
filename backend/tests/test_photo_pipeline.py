"""Async фото-конвейер: очередь в БД + обработка тиком. Загрузка не блокируется,
застрявшие queued-пакеты обрабатываются process_queued, ошибка → failed."""
import os, tempfile, json, base64
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from app import seed
from app.db import engine
from app.models import PhotoBatch, PhotoFragment
from app.services.photo_pipeline import process_queued, process_batch
from sqlmodel import Session, select
seed.run()


def _queued_batch(sim):
    with Session(engine) as s:
        b = PhotoBatch(doctor_id=1, status="pending", proc_status="queued",
                       sim_json=json.dumps(sim), image_b64="")
        s.add(b); s.commit(); s.refresh(b)
        return b.id


def test_process_queued_creates_fragments():
    bid = _queued_batch([{"last_name": "Иванов", "first_name": "И"},
                         {"last_name": "Петров", "first_name": "П"}])
    with Session(engine) as s:
        n = process_queued(s)
        assert n >= 1
        b = s.get(PhotoBatch, bid)
        assert b.proc_status == "done"
        frags = s.exec(select(PhotoFragment).where(PhotoFragment.batch_id == bid)).all()
        assert len(frags) == 2
        assert frags[0].extracted_name.startswith("Иванов")


def test_queued_only_processed_once():
    bid = _queued_batch([{"last_name": "Одинов", "first_name": "О"}])
    with Session(engine) as s:
        process_queued(s)
        # повторный прогон не должен создавать дубли фрагментов и не трогает done
        process_queued(s)
        frags = s.exec(select(PhotoFragment).where(PhotoFragment.batch_id == bid)).all()
        assert len(frags) == 1


def test_done_batch_not_reprocessed():
    with Session(engine) as s:
        b = PhotoBatch(doctor_id=1, status="pending", proc_status="done", image_b64="")
        s.add(b); s.commit(); s.refresh(b)
        process_batch(s, b)   # done → no-op
        frags = s.exec(select(PhotoFragment).where(PhotoFragment.batch_id == b.id)).all()
        assert len(frags) == 0


def test_failed_on_bad_sim():
    # sim_json невалидный JSON → обработка падает → failed, не роняет тик
    with Session(engine) as s:
        b = PhotoBatch(doctor_id=1, status="pending", proc_status="queued",
                       sim_json="{не json", image_b64="")
        s.add(b); s.commit(); s.refresh(b)
        process_batch(s, b)
        b2 = s.get(PhotoBatch, b.id)
        assert b2.proc_status == "failed" and b2.proc_error


def test_tick_processing_notifies_doctor():
    from app.models import Notification
    bid = _queued_batch([{"last_name": "Уведомов", "first_name": "У"}])
    with Session(engine) as s:
        before = len(s.exec(select(Notification).where(Notification.doctor_id == 1,
                                                       Notification.kind == "ocr")).all())
        process_queued(s)   # тик → notify=True
        after = s.exec(select(Notification).where(Notification.doctor_id == 1,
                                                  Notification.kind == "ocr")).all()
        assert len(after) == before + 1
        assert "распознано" in after[-1].text.lower()


def test_immediate_processing_no_notification():
    from app.models import Notification
    with Session(engine) as s:
        b = PhotoBatch(doctor_id=1, status="pending", proc_status="queued",
                       sim_json=json.dumps([{"last_name": "Тихонов", "first_name": "Т"}]), image_b64="")
        s.add(b); s.commit(); s.refresh(b)
        before = len(s.exec(select(Notification).where(Notification.doctor_id == 1, Notification.kind == "ocr")).all())
        process_batch(s, b)   # notify=False по умолчанию (немедленный путь)
        after = len(s.exec(select(Notification).where(Notification.doctor_id == 1, Notification.kind == "ocr")).all())
        assert after == before


def test_failed_tick_notifies_retake():
    from app.models import Notification
    with Session(engine) as s:
        b = PhotoBatch(doctor_id=1, status="pending", proc_status="queued",
                       sim_json="{битый", image_b64="")
        s.add(b); s.commit()
        process_queued(s)
        notifs = s.exec(select(Notification).where(Notification.doctor_id == 1, Notification.kind == "ocr")).all()
        assert any("пересъёмка" in n.text.lower() for n in notifs)
