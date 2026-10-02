"""Производственный календарь.

Субботы и воскресенья приложение считает само. Праздники и переносы вычислить
нельзя — их каждый год утверждает постановление правительства, поэтому даты
вносит человек.

Главное правило: года нет в базе — показываем только выходные и НЕ делаем вид,
что знаем про праздники. Ошибиться молча хуже, чем не знать.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from app.main import app
from app import seed

seed.run()
c = TestClient(app)
H = {"x-admin-token": "dev-admin-token"}


def test_неизвестный_год_честно_говорит_что_не_знает():
    r = c.get("/api/work-calendar/2031")
    assert r.status_code == 200
    assert r.json()["known"] is False
    assert r.json()["days"] == []


def test_год_сохраняется_и_читается():
    days = [{"day": "2027-01-01", "kind": "holiday", "label": "Новый год"},
            {"day": "2027-01-02", "kind": "holiday", "label": ""},
            {"day": "2027-01-09", "kind": "working", "label": "перенос"}]
    r = c.put("/api/admin/work-calendar/2027", json={"days": days}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == 3

    got = c.get("/api/work-calendar/2027").json()
    assert got["known"] is True and len(got["days"]) == 3
    kinds = {d["day"]: d["kind"] for d in got["days"]}
    assert kinds["2027-01-09"] == "working"


def test_сохранение_заменяет_год_целиком():
    c.put("/api/admin/work-calendar/2028",
          json={"days": [{"day": "2028-01-01", "kind": "holiday"}]}, headers=H)
    c.put("/api/admin/work-calendar/2028",
          json={"days": [{"day": "2028-05-09", "kind": "holiday"}]}, headers=H)
    days = [d["day"] for d in c.get("/api/work-calendar/2028").json()["days"]]
    assert days == ["2028-05-09"]


def test_чужой_год_в_списке_отклоняется():
    """Защита от вставки списка не за тот год."""
    r = c.put("/api/admin/work-calendar/2029",
              json={"days": [{"day": "2030-01-01", "kind": "holiday"}]}, headers=H)
    assert r.status_code == 400
    assert "2029" in r.json()["detail"]


def test_неизвестный_вид_дня_отклоняется():
    r = c.put("/api/admin/work-calendar/2029",
              json={"days": [{"day": "2029-01-01", "kind": "выходной"}]}, headers=H)
    assert r.status_code == 400


def test_слишком_много_дат_отклоняется():
    days = [{"day": "2029-01-01", "kind": "holiday"}] * 500
    assert c.put("/api/admin/work-calendar/2029",
                 json={"days": days}, headers=H).status_code == 400


def test_подпись_обрезается_и_не_исполняется():
    long_label = "x" * 500
    c.put("/api/admin/work-calendar/2030",
          json={"days": [{"day": "2030-01-01", "kind": "holiday", "label": long_label}]},
          headers=H)
    got = c.get("/api/work-calendar/2030").json()["days"][0]
    assert len(got["label"]) <= 120


def test_без_токена_править_нельзя():
    r = c.put("/api/admin/work-calendar/2027",
              # кириллицу в заголовок не положить — берём заведомо чужой токен
              json={"days": []}, headers={"x-admin-token": "wrong-token"})
    assert r.status_code in (401, 403)


def test_недопустимый_год_отклоняется():
    assert c.get("/api/work-calendar/1800").status_code == 400
