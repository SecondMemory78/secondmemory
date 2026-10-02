# Для тестов общий API rate-limit фактически выключаем (иначе быстрый прогон всего
import os as _os
_os.environ.setdefault("SCHEDULER_ENABLED", "0")
# набора упирается в общий счётчик). В проде значение берётся из .env (API_RATE_MAX=300).
# Точечный тест лимита сам понижает порог и чистит счётчик.
import os
os.environ.setdefault("API_RATE_MAX", "1000000")
# Антифлуд отправки кода (1 письмо/60с) выключаем в тестах: модульные хелперы
# логинятся подряд одним email на этапе импорта. В проде дефолт 60с/15 в сутки.
os.environ.setdefault("AUTH_CODE_COOLDOWN", "0")
os.environ.setdefault("AUTH_CODE_DAILY_MAX", "100000")

# ── Общая база для всех тестов ──────────────────────────────────────────────
# Все 90 файлов ставят DATABASE_URL через setdefault, то есть побеждает тот,
# кто импортировался первым. Это уже дважды кусало: соседний файл переназначал
# основной диагноз пациента, и тест выписки падал ТОЛЬКО в полном прогоне.
#
# Делать по базе на файл нельзя дёшево: движок создаётся один раз при импорте
# приложения. Поэтому делаем две вещи.
#
# Первая — ставим адрес ЗДЕСЬ, до любого тестового модуля. База общая, но
# предсказуемая: не «как повезёт с порядком импорта».
import tempfile as _tf
os.environ.setdefault("DATABASE_URL", "sqlite:///" + _tf.mktemp(suffix=".db"))

# Вторая — даём фикстуру own_patient (ниже). Тест, который МЕНЯЕТ пациента,
# обязан завести своего: общие seed-пациенты принадлежат всем сразу.

# ИИ в тестах — всегда заглушки: тесты не должны зависеть от локального .env
# разработчика и уж точно не должны ходить в платные API Яндекса.
os.environ["AI_PROVIDER"] = "stub"
os.environ.pop("YANDEX_API_KEY", None)
os.environ.pop("YANDEX_FOLDER_ID", None)


import pytest


@pytest.fixture
def own_patient():
    """Свой пациент для теста, который его меняет.

    База у тестов общая, поэтому `c.get("/api/patients")[0]` — это чужой
    пациент: соседний файл может поменять ему диагноз, добавить операции или
    устройства, и тест развалится только в полном прогоне. Такую поломку
    тяжело искать: поодиночке файл проходит.

    Правило: читаешь — можно общего, меняешь — заводи своего.
    """
    from sqlmodel import Session
    from app.db import engine
    from app.models import Patient

    created = []

    def _make(last_name="Тестов", with_consent=False, **kw):
        """with_consent=True — если тест будет ЗАПОЛНЯТЬ карту.

        Без согласия это запрещено продуктом, и так и должно быть: фикстура
        не обходит правило молча, а требует сказать об этом явно.
        """
        with Session(engine) as s:
            p = Patient(doctor_id=1, last_name=last_name,
                        first_name=kw.pop("first_name", "Иван"),
                        middle_name=kw.pop("middle_name", ""), **kw)
            s.add(p); s.commit(); s.refresh(p)
            created.append(p.id)
            pid = p.id

        if with_consent:
            from fastapi.testclient import TestClient
            from app.main import app as _app
            TestClient(_app).post(f"/api/patients/{pid}/consent/electronic",
                                  json={"agreed": True})
        with Session(engine) as s:
            return s.get(Patient, pid)

    yield _make

    # За собой убираем: иначе список пациентов разрастается и чужие тесты,
    # считающие их количество, начинают падать.
    #
    # ВАЖНО удалять и связанные записи. SQLite переиспользует освободившийся
    # номер, и следующий тестовый пациент получает тот же id — вместе с
    # чужими показателями, заметками и документами. Поймано на конфликте
    # источников: тест видел значения из предыдущего теста.
    from sqlmodel import delete as _delete
    from app.models import (Appointment, Device, DoctorNote, Note, Observation,
                            PatientDiagnosis, Procedure, Reminder, SourceDocument)
    related = (Observation, Note, PatientDiagnosis, Procedure, Device,
               Reminder, Appointment, SourceDocument, DoctorNote)
    with Session(engine) as s:
        for pid in created:
            for model in related:
                if hasattr(model, "patient_id"):
                    s.exec(_delete(model).where(model.patient_id == pid))
            obj = s.get(Patient, pid)
            if obj:
                s.delete(obj)
        s.commit()
