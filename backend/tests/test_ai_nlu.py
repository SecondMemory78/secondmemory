"""Слой понимания команд через YandexGPT.

Модель только КЛАССИФИЦИРУЕТ, действие выполняет наш код. Проверяем главное:
без ключа поведение прежнее; модель не может выдумать себе новое действие;
триггеры недоступны ей в принципе; при неуверенности ничего не создаём молча.
"""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import Reminder, Appointment, Note
from app.services import ai
seed.run()
c = TestClient(app)


def _mock(monkeypatch, payload):
    """Подменяем ответ модели, не трогая сеть."""
    monkeypatch.setattr(ai, "parse_command", lambda text, context=None: payload)


# ── защита разбора ответа модели ────────────────────────────────────────────
def test_coerce_rejects_invented_intent():
    r = ai._coerce_nlu('{"intent":"prescribe_drug","confidence":0.99}')
    assert r["intent"] == "unknown"            # своё намерение выдумать нельзя


def test_coerce_rejects_trigger_intent():
    r = ai._coerce_nlu('{"intent":"trigger","confidence":1.0}')
    assert r["intent"] == "unknown"            # триггеры модели недоступны


def test_coerce_handles_markdown_and_prose():
    assert ai._coerce_nlu('```json\n{"intent":"task","confidence":0.8}\n```')["intent"] == "task"
    assert ai._coerce_nlu('Ответ: {"intent":"task","confidence":0.8} .')["intent"] == "task"


def test_coerce_returns_none_on_garbage():
    assert ai._coerce_nlu("я не понял") is None
    assert ai._coerce_nlu("") is None


def test_coerce_normalizes_confidence():
    assert ai._coerce_nlu('{"intent":"task","confidence":"много"}')["confidence"] == 0.0
    assert ai._coerce_nlu('{"intent":"task","confidence":55}')["confidence"] == 1.0


# ── поведение ассистента с подключённой моделью ─────────────────────────────
def test_without_model_behaviour_unchanged(monkeypatch):
    _mock(monkeypatch, None)                   # как без ключа
    r = c.post("/api/assistant/command", json={"text": "напомни купить бумагу завтра"}).json()
    assert r["intent"] == "task"               # прежний путь по правилам


def test_low_confidence_falls_back_to_rules(monkeypatch):
    _mock(monkeypatch, {"intent": "appointment", "patient_hint": "", "title": "",
                        "datetime_hint": "", "confidence": 0.2})
    r = c.post("/api/assistant/command", json={"text": "что-то непонятное про бумагу"}).json()
    assert r["intent"] == "task"               # не доверяем неуверенной модели


def test_unknown_creates_nothing_and_explains(monkeypatch):
    _mock(monkeypatch, {"intent": "unknown", "patient_hint": "", "title": "",
                        "datetime_hint": "", "confidence": 0.95})
    with Session(engine) as s:
        before = len(s.exec(select(Reminder)).all())
    # Фраза должна оставаться непонятной: раньше здесь был пример про диагноз,
    # но диагнозы ассистент теперь разбирает, и тест проверял бы не то.
    r = c.post("/api/assistant/command", json={"text": "сделай мне красиво"}).json()
    assert r["intent"] == "unknown" and r["ok"] is False
    assert "не понял" in r["message"].lower()
    with Session(engine) as s:
        assert len(s.exec(select(Reminder)).all()) == before   # мусорной задачи не появилось


def test_model_cannot_bypass_trigger_ban(monkeypatch):
    # даже если модель уверенно скажет "task", фраза про триггер обрывается РАНЬШЕ
    _mock(monkeypatch, {"intent": "task", "patient_hint": "", "title": "триггер",
                        "datetime_hint": "", "confidence": 1.0})
    r = c.post("/api/assistant/command", json={"text": "поставь триггер на PSA"}).json()
    assert r["intent"] == "trigger_denied" and r["ok"] is False


def test_model_hint_creates_note_for_known_patient(monkeypatch):
    pid = c.post("/api/patients", json={"last_name": "Нлуев", "first_name": "Иван"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    _mock(monkeypatch, {"intent": "patient_note", "patient_hint": "Нлуев",
                        "title": "жалобы на никтурию", "datetime_hint": "", "confidence": 0.9})
    r = c.post("/api/assistant/command", json={"text": "у Нлуева жалобы на никтурию"}).json()
    assert r["intent"] == "patient_note" and r["patient_id"] == pid
    with Session(engine) as s:
        notes = s.exec(select(Note).where(Note.patient_id == pid)).all()
    assert any("никтурию" in n.text for n in notes)


def test_model_hint_asks_for_patient_when_unresolved(monkeypatch):
    _mock(monkeypatch, {"intent": "patient_note", "patient_hint": "Несуществующий",
                        "title": "что-то", "datetime_hint": "", "confidence": 0.9})
    r = c.post("/api/assistant/command", json={"text": "запиши в карту что-то"}).json()
    # пациента нет → ничего не создаём; либо уточняем, либо предлагаем создать карту
    assert r["patient_id"] is None
    assert "уточните" in r["message"].lower() or r.get("suggest_create")


# ── загрузка .env и диагностика режима ──────────────────────────────────────
def test_env_file_is_loaded_before_modules_read_it(tmp_path, monkeypatch):
    """Главная причина «ассистент отвечает одинаково»: .env не читался вовсе."""
    import app as app_pkg
    env = tmp_path / ".env"
    env.write_text("SM_TEST_VAR=из_файла\n# комментарий\nПУСТАЯ\n", encoding="utf-8")
    monkeypatch.delenv("SM_TEST_VAR", raising=False)
    app_pkg._load_env_file(env)
    assert os.environ["SM_TEST_VAR"] == "из_файла"


def test_real_env_wins_over_file(tmp_path, monkeypatch):
    import app as app_pkg
    env = tmp_path / ".env"
    env.write_text("SM_TEST_VAR2=из_файла\n", encoding="utf-8")
    monkeypatch.setenv("SM_TEST_VAR2", "из_окружения")
    app_pkg._load_env_file(env)
    assert os.environ["SM_TEST_VAR2"] == "из_окружения"   # иначе сломались бы тесты и прод


def test_missing_or_broken_env_does_not_crash(tmp_path):
    import app as app_pkg
    app_pkg._load_env_file(tmp_path / "нет-такого.env")   # отсутствует — норма
    broken = tmp_path / ".env"
    broken.write_text("мусор без равно\n\n", encoding="utf-8")
    app_pkg._load_env_file(broken)                        # не должно падать


def test_health_reports_ai_mode_without_leaking_keys():
    r = c.get("/api/health").json()
    assert r["ai"]["provider"] and "mode" in r["ai"]
    blob = str(r)
    assert "AQVN" not in blob and "api_key" not in blob.lower()


# ── типичные ошибки Windows при создании .env ───────────────────────────────
def test_env_with_bom_is_read(tmp_path, monkeypatch):
    """Блокнот пишет BOM в начало файла — без учёта этого первая строка терялась."""
    import app as app_pkg
    p = tmp_path / ".env"
    p.write_text("SM_BOM_TEST=works\n", encoding="utf-8-sig")
    monkeypatch.delenv("SM_BOM_TEST", raising=False)
    assert app_pkg._load_env_file(p) is True
    assert os.environ["SM_BOM_TEST"] == "works"


def test_env_with_crlf_quotes_and_spaces(tmp_path, monkeypatch):
    import app as app_pkg
    p = tmp_path / ".env"
    p.write_bytes(b'SM_CRLF_TEST = "works" \r\n# comment\r\n')
    monkeypatch.delenv("SM_CRLF_TEST", raising=False)
    app_pkg._load_env_file(p)
    assert os.environ["SM_CRLF_TEST"] == "works"


def test_env_export_prefix(tmp_path, monkeypatch):
    import app as app_pkg
    p = tmp_path / ".env"
    p.write_text("export SM_EXPORT_TEST=works\n", encoding="utf-8")
    monkeypatch.delenv("SM_EXPORT_TEST", raising=False)
    app_pkg._load_env_file(p)
    assert os.environ["SM_EXPORT_TEST"] == "works"


def test_health_reports_where_env_was_looked_for():
    r = c.get("/api/health").json()
    cfg = r["config"]
    assert isinstance(cfg["looked_in"], list) and cfg["looked_in"]
    assert any(x.endswith(".env") for x in cfg["looked_in"])
    # подсказка появляется только когда файл не найден
    assert (cfg["hint"] is None) == (cfg["env_file"] is not None)


# ── формат звука и тип файла для Яндекса ────────────────────────────────────
def test_lpcm_format_is_passed_to_speechkit(monkeypatch):
    """Браузер пишет webm, SpeechKit его не принимает — шлём lpcm 16 кГц.
    Проверяем, что параметры формата реально доходят до запроса."""
    seen = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"result": "распознано"}

    import httpx
    monkeypatch.setattr(ai, "PROVIDER", "yandex")
    monkeypatch.setattr(ai, "YANDEX_API_KEY", "k")
    monkeypatch.setattr(ai, "YANDEX_FOLDER_ID", "f")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (seen.update(kw), _Resp())[1])

    assert ai.transcribe(b"\x00\x00" * 100, "lpcm") == "распознано"
    assert seen["params"]["format"] == "lpcm"
    assert seen["params"]["sampleRateHertz"] == "16000"


def test_no_format_means_no_format_params(monkeypatch):
    seen = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"result": ""}

    import httpx
    monkeypatch.setattr(ai, "PROVIDER", "yandex")
    monkeypatch.setattr(ai, "YANDEX_API_KEY", "k")
    monkeypatch.setattr(ai, "YANDEX_FOLDER_ID", "f")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (seen.update(kw), _Resp())[1])

    ai.transcribe(b"data", "")
    assert "format" not in seen["params"]        # не навязываем формат зря


def test_mime_sniffing_for_ocr():
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    assert ai._sniff_mime(png) == "image/png"
    assert ai._sniff_mime(b"%PDF-1.7 x") == "application/pdf"
    assert ai._sniff_mime(b"\xff\xd8\xff\xe0 jpeg") == "image/jpeg"


def test_selftest_probe_image_is_decodable_size():
    """1x1 Vision не декодирует — проба должна слать картинку нормального размера."""
    from app.routers.settings import _blank_png
    png = _blank_png(64, 64)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 100


# ── заглушки только в демо ──────────────────────────────────────────────────
def test_stub_text_never_leaks_when_ai_is_configured(monkeypatch):
    """Врач не должен получать выдуманный текст вместо ошибки распознавания."""
    import httpx
    monkeypatch.setattr(ai, "PROVIDER", "yandex")
    monkeypatch.setattr(ai, "YANDEX_API_KEY", "k")
    monkeypatch.setattr(ai, "YANDEX_FOLDER_ID", "f")

    def boom(*a, **kw):
        raise RuntimeError("сеть недоступна")
    monkeypatch.setattr(httpx, "post", boom)

    try:
        ai.transcribe(b"x", "lpcm")
        assert False, "должна быть ошибка, а не заглушка"
    except ai.AIError as e:
        assert "распознать речь" in str(e)
        assert "никтури" not in str(e).lower()     # шаблон не подставился


def test_ocr_also_errors_instead_of_stub(monkeypatch):
    import httpx
    monkeypatch.setattr(ai, "PROVIDER", "yandex")
    monkeypatch.setattr(ai, "YANDEX_API_KEY", "k")
    monkeypatch.setattr(ai, "YANDEX_FOLDER_ID", "f")
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("x")))
    try:
        ai.ocr_extract(b"img")
        assert False, "должна быть ошибка"
    except ai.AIError as e:
        assert "распознать документ" in str(e)


def test_stub_still_used_in_demo_mode(monkeypatch):
    """В демо ИИ недоступен — там пример уместен и ничего не ломает."""
    monkeypatch.setattr(ai, "PROVIDER", "stub")
    assert ai.transcribe(b"x") and ai.ocr_extract(b"x")


def test_model_datetime_is_used_for_appointment(monkeypatch):
    from datetime import datetime as _dt
    pid = c.post("/api/patients", json={"last_name": "Времев", "first_name": "И"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    _mock(monkeypatch, {"intent": "appointment", "patient_hint": "Времев", "title": "",
                        "datetime": _dt(2026, 9, 30, 15, 0), "datetime_hint": "",
                        "priority": "", "repeat": "", "confidence": 0.9})
    r = c.post("/api/assistant/command", json={"text": "запиши Времева в 3 часа дня на среду"}).json()
    assert r["intent"] == "appointment" and "15:00" in r["message"]


def test_model_creates_task_with_due_and_urgency(monkeypatch):
    from datetime import datetime as _dt
    _mock(monkeypatch, {"intent": "task", "patient_hint": "", "title": "позвонить человеку",
                        "datetime": _dt(2026, 9, 27, 14, 20), "datetime_hint": "",
                        "priority": "срочно", "repeat": "", "confidence": 0.9})
    r = c.post("/api/assistant/command",
               json={"text": "срочно позвонить человеку через 20 минут"}).json()
    assert r["intent"] == "task" and "14:20" in r["message"] and "срочная" in r["message"]


# ── несколько команд одной фразой (жалоба: «запишет только одного») ─────────
def test_splits_two_patients_in_one_phrase():
    from app.services.assistant import split_commands
    parts = split_commands("запиши Иванова на среду в 15 часов и Петрова на четверг в 10 утра")
    assert len(parts) == 2
    assert parts[1].lower().startswith("запиш")      # глагол перенесён во вторую часть


def test_does_not_split_ordinary_speech():
    """«боль и жжение» — не две команды."""
    from app.services.assistant import split_commands
    assert len(split_commands("в карту Иванова жалобы на боль и жжение")) == 1
    assert len(split_commands("заехать в магазин и аптеку")) == 1


def test_splits_on_explicit_verb():
    from app.services.assistant import split_commands
    parts = split_commands("напомни купить бумагу завтра и запиши Сидорова на пятницу")
    assert len(parts) == 2


def test_two_appointments_created_from_one_phrase():
    for fam in ("Мультиев", "Двоев"):
        c.post("/api/patients", json={"last_name": fam, "first_name": "И"})
    r = c.post("/api/assistant/command",
               json={"text": "запиши Мультиева на среду в 15 часов "
                             "и Двоева на четверг в 10 утра"}).json()
    assert r["intent"] == "multi" and r["count"] == 2
    assert r["message"].count("Записан приём") == 2


def test_repeat_survives_ai_created_task(monkeypatch):
    from datetime import datetime as _dt
    _mock(monkeypatch, {"intent": "task", "patient_hint": "", "title": "контроль ПСА",
                        "datetime": _dt(2026, 12, 1, 9, 0), "datetime_hint": "",
                        "priority": "", "repeat": "", "confidence": 0.9})
    r = c.post("/api/assistant/command",
               json={"text": "контроль ПСА каждые 3 месяца"}).json()
    assert "повтор" in r["message"]            # повтор не потерян


def test_adverb_repeat_forms():
    from app.services.nlp import parse_reminder
    assert parse_reminder("созвон еженедельно")["repeat_days"] == 7
    assert parse_reminder("пить таблетки ежедневно")["repeat_days"] == 1
    assert parse_reminder("осмотр ежегодно")["repeat_days"] == 365


# ── ассистент умеет всё: назначения, показатели, открыть карту ──────────────
def _patient(fam="Всеумев"):
    pid = c.post("/api/patients", json={"last_name": fam, "first_name": "И"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    return pid, fam


def test_assistant_can_prescribe_as_suggestion():
    pid, fam = _patient("Назначаев")
    r = c.post("/api/assistant/command",
               json={"text": f"назначь {fam}у тадалафил 5 мг раз в день месяц"}).json()
    assert r["intent"] == "prescription" and r["patient_id"] == pid
    items = c.get(f"/api/patients/{pid}/prescriptions").json()["items"]
    assert items and all(not x["confirmed"] for x in items)   # только предложение


def test_assistant_prescription_without_patient_asks():
    """Фамилии в команде нет — просим уточнить, карту не предлагаем наугад."""
    r = c.post("/api/assistant/command",
               json={"text": "назначь тадалафил 5 мг"}).json()
    assert r["intent"] == "patient_missing" and r["ok"] is False
    assert r["suggest_create"] is False and "фамилию" in r["message"].lower()


def test_unknown_patient_offers_to_create_card():
    """Пациента нет, но фамилия названа — предлагаем создать карту,
    а не заводим её голосом и не превращаем запись в задачу."""
    r = c.post("/api/assistant/command",
               json={"text": "запиши Небывалова на среду в 15"}).json()
    assert r["intent"] == "patient_missing" and r["suggest_create"] is True
    assert r["surname"] == "Небывалов"          # падежное окончание снято
    assert r["patient_id"] is None              # ничего не создано


def test_note_for_unknown_patient_also_offers_creation():
    r = c.post("/api/assistant/command",
               json={"text": "в карту Небывалова: жалобы на никтурию"}).json()
    assert r["intent"] == "patient_missing" and r["surname"] == "Небывалов"


def test_ordinary_task_is_not_mistaken_for_a_patient():
    for text in ("напомни завтра купить бумагу", "заехать в магазин вечером"):
        assert c.post("/api/assistant/command", json={"text": text}).json()["intent"] == "task"


def test_surname_guess_ignores_command_and_time_words():
    from app.services.assistant import guess_surname
    assert guess_surname("запиши Сидорова на среду в 15") == "Сидоров"
    assert guess_surname("назначь Петрову тадалафил") == "Петров"
    assert guess_surname("напомни завтра купить бумагу") == ""


def test_assistant_records_a_lab_value():
    pid, fam = _patient("Значаев")
    r = c.post("/api/assistant/command", json={"text": f"у {fam}а ПСА 7,2"}).json()
    assert r["intent"] == "observation" and r["patient_id"] == pid
    series = c.get(f"/api/patients/{pid}/timeline").json().get("psa_total", [])
    assert any(x["status"] == "pending" and x["value_num"] == 7.2 for x in series)


def test_assistant_opens_patient_card():
    pid, fam = _patient("Открываев")
    r = c.post("/api/assistant/command", json={"text": f"открой карту {fam}а"}).json()
    assert r["intent"] == "open_patient" and r["patient_id"] == pid


def test_open_does_not_become_a_note():
    """«открой карту» — просьба показать, а не записать в карту."""
    pid, fam = _patient("Смотрев")
    c.post("/api/assistant/command", json={"text": f"открой карту {fam}а"})
    notes = c.get(f"/api/patients/{pid}/notes").json()
    assert notes == [] or len(notes) == 0


# ── приглашение на контроль голосом ─────────────────────────────────────────
def test_assistant_invites_for_followup():
    pid, fam = _patient("Контролев")
    r = c.post("/api/assistant/command",
               json={"text": f"пригласи {fam}а на контроль через 6 месяцев"}).json()
    assert r["intent"] == "appointment" and r["patient_id"] == pid
    assert "10:00" in r["message"]             # час не назван → рабочее утро


def test_invite_without_term_asks_for_it():
    pid, fam = _patient("Срокова")
    r = c.post("/api/assistant/command", json={"text": f"пригласи {fam}у на контроль"}).json()
    assert r["intent"] == "appointment" and "уточните срок" in r["message"].lower()


def test_invite_respects_explicit_time():
    pid, fam = _patient("Часова")
    r = c.post("/api/assistant/command",
               json={"text": f"пригласи {fam}у на контроль 20 октября в 15 часов"}).json()
    assert "20.10.2026 15:00" in r["message"]
