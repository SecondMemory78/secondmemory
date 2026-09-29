"""AuditEvent.detail шифруется в БД (152-ФЗ): в приложении — открытый текст,
в сырой базе — шифр. Старые нешифрованные записи читаются как есть (fallback)."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from app import seed
from app.db import engine
from app.models import AuditEvent
from sqlmodel import Session, select
import sqlite3
seed.run()


def test_audit_detail_encrypted_at_rest():
    secret = "N40 рак предстательной железы"
    with Session(engine) as s:
        e = AuditEvent(doctor_id=1, entity_type="diagnosis", entity_id=1,
                       action="add", detail=secret)
        s.add(e); s.commit(); eid = e.id
    # через ORM — открытый текст
    with Session(engine) as s:
        assert s.get(AuditEvent, eid).detail == secret
    # в сырой БД — НЕ открытый текст
    db_path = str(engine.url.database)
    raw = sqlite3.connect(db_path).execute(
        "SELECT detail FROM auditevent WHERE id=?", (eid,)).fetchone()[0]
    assert raw != secret, "detail хранится открытым текстом!"
    assert "рак" not in raw and "N40" not in raw
