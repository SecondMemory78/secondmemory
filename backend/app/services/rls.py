"""Row-Level Security — второй слой защиты «врач видит только своих» на уровне БД.

Работает ТОЛЬКО на Postgres (в dev/тестах на SQLite молча пропускается — там RLS
не существует by design). Даже если в коде где-то забыт фильтр по doctor_id,
база физически не отдаст чужие строки.

Механика:
- на каждый запрос приложение выставляет GUC app.current_doctor_id (id врача) и
  app.bypass_rls ('on' для админ-контекста, где нужен доступ ко всем врачам);
- политики разрешают строку, если её doctor_id совпадает с app.current_doctor_id
  ИЛИ включён bypass. Дочерние таблицы (только patient_id) проверяются подзапросом
  к patient.

ВАЖНО (к боевому развёртыванию, проверить на staging):
- приложение должно подключаться к БД НЕ владельцем таблиц (владелец обходит RLS),
  либо таблицы помечаются FORCE ROW LEVEL SECURITY;
- таблицы аутентификации (doctor, authsession, logincode, passwordreset, systemmeta)
  СОЗНАТЕЛЬНО без RLS — иначе «курица и яйцо»: нельзя прочитать сессию, чтобы узнать,
  кто ты. Их защищает код (по токену) и сетевой периметр.
"""
from sqlalchemy import text

# Таблицы с прямым doctor_id
DOCTOR_TABLES = [
    "patient", "encounter", "appointment", "reminder", "notification",
    "usagerecord", "subscription", "auditevent", "accesslog",
    "supportthread", "supportmessage", "analyticsevent",
]
# Дочерние таблицы (только patient_id) — проверяем через принадлежность пациента
PATIENT_CHILD_TABLES = [
    "observation", "note", "prescription", "safetyitem", "visitprotocol",
    "patientconsent", "patientdiagnosis", "sourcedocument", "patientexternalid",
]

# NULLIF здесь обязателен, и вот почему.
#
# current_setting('app.current_doctor_id', true) возвращает NULL, только если
# параметр в этом подключении НИКОГДА не задавался. Если он задавался, а потом
# транзакция откатилась (любой упавший запрос), параметр возвращается к
# значению на начало транзакции — а это ПУСТАЯ СТРОКА, не NULL. И тогда
# ''::int падает с «invalid input syntax for type integer: ""».
#
# Отсюда и загадочная непостоянность на сервере: подключения берутся из пула,
# и запрос падал ровно на тех, где до этого что-то откатывалось. На SQLite не
# воспроизводилось, потому что там политик изоляции нет вовсе.
#
# NULLIF превращает пустую строку в NULL: сравнение даёт NULL → строка просто
# не видна, что для политики изоляции и есть правильное поведение.
_CUR_DOCTOR = "NULLIF(current_setting('app.current_doctor_id', true), '')::int"

_DOCTOR_MATCH = (f"doctor_id = {_CUR_DOCTOR} "
                 "OR current_setting('app.bypass_rls', true) = 'on'")
_CHILD_MATCH = ("patient_id IN (SELECT id FROM patient WHERE "
                f"doctor_id = {_CUR_DOCTOR}) "
                "OR current_setting('app.bypass_rls', true) = 'on'")


def is_postgres(engine) -> bool:
    return engine.dialect.name == "postgresql"


def apply_rls(engine) -> None:
    """Идемпотентно включает RLS и политики. No-op вне Postgres."""
    if not is_postgres(engine):
        return
    with engine.begin() as conn:
        for table, cond in ([(t, _DOCTOR_MATCH) for t in DOCTOR_TABLES]
                            + [(t, _CHILD_MATCH) for t in PATIENT_CHILD_TABLES]):
            conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
            conn.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
            conn.execute(text(f'DROP POLICY IF EXISTS sm_isolation ON "{table}"'))
            conn.execute(text(
                f'CREATE POLICY sm_isolation ON "{table}" USING ({cond}) WITH CHECK ({cond})'))


def set_session_scope(session, doctor_id, bypass: bool = False) -> None:
    """Выставляет GUC для сессии-подключения. No-op вне Postgres.
    is_local=false: значение держится на подключении и переживает commit внутри
    запроса; get_session перезаписывает его в начале каждого запроса."""
    if not is_postgres(session.get_bind()):
        return
    # Значение всегда строкой целого числа: пустая строка тут недопустима —
    # политика приводит её к int и падает.
    try:
        did = int(doctor_id)
    except (TypeError, ValueError):
        did = -1                       # «врач не определён» — не видно ничего
    session.execute(text("SELECT set_config('app.current_doctor_id', :d, false)"),
                    {"d": str(did)})
    session.execute(text("SELECT set_config('app.bypass_rls', :b, false)"),
                    {"b": "on" if bypass else "off"})
