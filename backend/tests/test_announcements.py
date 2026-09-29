"""Объявления врачам: типы, адресация, срок, право закрыть."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock
seed.run()
c = TestClient(app)
AH = {"x-admin-token": "dev-admin-token"}


def _create(**kw):
    body = {"kind": "news", "title": "Заголовок", "text": "текст"}
    body.update(kw)
    return c.post("/api/admin/announcements", headers=AH, json=body)


def _titles():
    return [i["title"] for i in c.get("/api/announcements").json()["items"]]


def test_admin_auth_required():
    assert c.post("/api/admin/announcements", json={"title": "x"}).status_code == 401
    assert c.get("/api/admin/announcements").status_code == 401


def test_maintenance_cannot_be_dismissed_even_if_asked():
    """Техработы врач скрывать не должен — подстраховываем выбор админа."""
    a = _create(kind="maintenance", title="Работы", dismissible=True).json()
    assert a["dismissible"] is False
    assert c.post(f"/api/announcements/{a['id']}/dismiss").status_code == 400
    assert "Работы" in _titles()


def test_news_can_be_dismissed_and_stays_hidden():
    a = _create(kind="news", title="Новость").json()
    assert "Новость" in _titles()
    assert c.post(f"/api/announcements/{a['id']}/dismiss").json()["ok"] is True
    assert "Новость" not in _titles()


def test_dismissed_announcement_still_visible_in_notifications():
    """Полосу закрыли — в уведомлениях осталось, чтобы важное не потерялось."""
    a = _create(kind="news", title="Не теряем").json()
    c.post(f"/api/announcements/{a['id']}/dismiss")
    body = c.get("/api/notifications").json()
    # объявления идут отдельным блоком, чтобы не ломать отметку прочтения
    assert "Не теряем" in [a["title"] for a in body["announcements"]]
    assert all(isinstance(i["id"], int) for i in body["items"])   # уведомления — свои


def test_period_controls_visibility():
    future = (clock.now() + timedelta(days=3)).isoformat()
    past = (clock.now() - timedelta(days=3)).isoformat()
    _create(title="Ещё рано", starts_at=future)
    _create(title="Уже поздно", ends_at=past)
    _create(title="Сейчас", starts_at=past, ends_at=future)
    shown = _titles()
    assert "Сейчас" in shown and "Ещё рано" not in shown and "Уже поздно" not in shown


def test_end_before_start_is_rejected():
    r = _create(title="Кривой период",
                starts_at=(clock.now() + timedelta(days=2)).isoformat(),
                ends_at=clock.now().isoformat())
    assert r.status_code == 400


def _my_doctor_id() -> int:
    from sqlmodel import Session, select
    from app.db import engine
    from app.models import Doctor
    with Session(engine) as s:
        return s.exec(select(Doctor)).first().id


def test_selected_audience_only_reaches_chosen_doctors():
    me = _my_doctor_id()
    _create(title="Только мне", audience="selected", doctor_ids=[me])
    _create(title="Другому", audience="selected", doctor_ids=[me + 999])
    shown = _titles()
    assert "Только мне" in shown and "Другому" not in shown


def test_selected_without_doctors_is_rejected():
    assert _create(title="Никому", audience="selected", doctor_ids=[]).status_code == 400


def test_admin_can_stop_and_delete():
    a = _create(title="Снимем").json()
    assert "Снимем" in _titles()
    c.post(f"/api/admin/announcements/{a['id']}/stop", headers=AH)
    assert "Снимем" not in _titles()
    assert c.delete(f"/api/admin/announcements/{a['id']}", headers=AH).json()["ok"] is True


def test_unknown_kind_and_empty_title_rejected():
    assert _create(kind="выдуманный").status_code == 400
    assert _create(title="   ").status_code == 400


def test_important_comes_first():
    _create(kind="news", title="Новость-2")
    _create(kind="important", title="Важное")
    assert _titles()[0] == "Важное"


def test_барьер_подписки_не_мешает_админу(monkeypatch):
    """Раньше админские POST/DELETE упирались в барьер «без подписки только
    чтение»: объявление нельзя было ни опубликовать, ни снять. Админские
    эндпоинты защищены своим токеном и к подписке отношения не имеют.

    Подписку гасим принудительно — у демо-врача из seed она активна."""
    import app.services.billing as billing
    monkeypatch.setattr(billing, "subscription_ok", lambda s, did: False)

    # барьер действительно включён: обычная запись врача блокируется
    assert c.post("/api/patients", json={"last_name": "Барьеров"}).status_code == 402

    # а админ работает
    a = _create(title="Публикуем без подписки").json()
    assert c.post(f"/api/admin/announcements/{a['id']}/stop", headers=AH).status_code == 200
    assert c.delete(f"/api/admin/announcements/{a['id']}", headers=AH).status_code == 200
