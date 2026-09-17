"""Доменная модель «Второй памяти».

Ключевой принцип: значение привязано к ПАРАМЕТРУ, а не к документу
(Observation — временной ряд). Документ — лишь источник. Ничего не удаляется
безвозвратно, каждое изменение фиксируется в AuditEvent (append-only).
"""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import Column
from .crypto import EncryptedStr
from sqlmodel import SQLModel, Field


def now() -> datetime:
    return datetime.utcnow()


class Doctor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str
    specialty: str = "Уролог"
    license_no: str = ""
    email: str = Field(default="", index=True)
    phone: str = Field(default="", index=True)    # обязателен при регистрации; уникален
    password_hash: str = ""
    role: str = "doctor"          # doctor | support | admin
    is_demo: bool = False          # демо-аккаунт — исключён из барьера подписки
    timezone: str = "Europe/Moscow"
    notify_push: bool = True          # push при распознавании документов
    notify_tracking: bool = True      # уведомления автослежения (триггеры)
    pin_hash: str = ""            # локальный разблок (биометрия/PIN) — заглушка
    created_at: datetime = Field(default_factory=now)


class AuthSession(SQLModel, table=True):
    """Сессия устройства. Живёт 30 дней (или 90, если 'запомнить устройство').
    В БД храним ТОЛЬКО хеш токена (sha256) — дамп базы не выдаёт рабочих токенов."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    token_hash: str = Field(index=True)
    device_id: str = ""
    user_agent: str = ""          # для человекочитаемого списка «мои устройства»
    remembered: bool = False
    expires_at: datetime
    created_at: datetime = Field(default_factory=now)


class LoginCode(SQLModel, table=True):
    """Одноразовый код для входа на новом устройстве (2FA по почте)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True)
    code: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=now)


class PasswordReset(SQLModel, table=True):
    """Сброс пароля: храним ХЕШ токена (не сам токен), одноразовый, с TTL."""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True)
    token_hash: str = Field(index=True)
    used: bool = False
    expires_at: datetime
    created_at: datetime = Field(default_factory=now)


class Patient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    last_name: str = Field(sa_column=Column(EncryptedStr, nullable=False))
    first_name: str = Field(sa_column=Column(EncryptedStr, nullable=False))
    middle_name: str = Field(default="", sa_column=Column(EncryptedStr))
    birth_date: Optional[date] = None
    birth_date_precision: str = "day"    # day | unknown — ДР не выдумываем
    sex: str = ""                 # "м" / "ж" / "" (не угадываем из имени)
    phone: str = Field(default="", sa_column=Column(EncryptedStr))
    diagnosis_code: str = ""      # МКБ-10 — основной/наблюдательный диагноз (в шапке карты)
    diagnosis_text: str = ""
    identity_status: str = "confirmed"   # confirmed | provisional (неполные данные)
    version: int = 1              # для защиты от одновременного изменения (expected_version)
    # слепой индекс: HMAC ФИО для ТОЧНОЙ сверки личности без расшифровки всех карточек
    name_index: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=now)

    @property
    def short_name(self) -> str:
        i = (self.first_name[:1] + "." if self.first_name else "")
        m = (self.middle_name[:1] + "." if self.middle_name else "")
        return f"{self.last_name} {i} {m}".strip()


class PatientExternalId(SQLModel, table=True):
    """Внешний идентификатор пациента с named-системой (ЕМИАС, № карты и т.п.).
    Номер палаты/стационарной карты НЕ является идентификатором человека."""
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    system: str = Field(index=True)      # название системы
    value: str = Field(index=True)       # значение ID в этой системе
    created_at: datetime = Field(default_factory=now)


class Encounter(SQLModel, table=True):
    """Эпизод ведения пациента. Тип «приём» (амбулаторно) или «госпитализация».
    К эпизоду привязываются наблюдения, заметки, назначения, протокол и документы.
    История пациента = список эпизодов. У пациента может быть несколько ОДНОВРЕМЕННО
    открытых эпизодов (напр. стационар + запланированный приём)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    type: str = "visit"                       # visit (приём) | hospitalization (госпитализация)
    reason: str = ""
    status: str = "open"                      # open | closed
    # мягкая связь с планом в календаре (может быть None — внезапная госпитализация)
    appointment_id: Optional[int] = Field(default=None, foreign_key="appointment.id")
    # даты стационара: плановые и фактические (ничего не выдумываем — None пока не указано)
    planned_admission_at: Optional[datetime] = None
    actual_admission_at: Optional[datetime] = None
    planned_discharge_at: Optional[datetime] = None
    actual_discharge_at: Optional[datetime] = None
    ward: str = ""                            # палата (необязательно)
    # диагноз эпизода — отдельно от «основного» диагноза пациента (в шапке карты)
    diagnosis_code: str = ""
    diagnosis_text: str = ""
    version: int = 1                          # expected_version — защита от одновременного изменения
    started_at: datetime = Field(default_factory=now)
    closed_at: Optional[datetime] = None


class SickLeave(SQLModel, table=True):
    """Больничный лист — отдельный жизненный цикл, НЕ привязан жёстко к выписке
    (эпизод может закрыться, а больничный остаться открытым → попадёт в «требует внимания»)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    encounter_id: Optional[int] = Field(default=None, foreign_key="encounter.id", index=True)
    status: str = "open"                      # open | extended | closed
    number: str = ""                          # номер листа (необязательно)
    opened_at: Optional[date] = None
    closed_at: Optional[date] = None
    note: str = ""
    version: int = 1
    created_at: datetime = Field(default_factory=now)


class Observation(SQLModel, table=True):
    """Одно значение показателя во времени. Основа динамики «было → стало»."""
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    encounter_id: Optional[int] = Field(default=None, foreign_key="encounter.id", index=True)
    parameter_code: str = Field(index=True)   # psa_total, prostate_volume, ...
    value_num: Optional[float] = None
    value_text: Optional[str] = None
    unit: str = ""
    effective_date: Optional[date] = None
    source_document_id: Optional[int] = Field(default=None, foreign_key="sourcedocument.id")
    status: str = "confirmed"                 # confirmed | pending  (juридический щит)
    created_at: datetime = Field(default_factory=now)


class NotificationPreference(SQLModel, table=True):
    """Личные настройки уведомлений врача. Один ряд на врача, создаётся при первом обращении.
    default_offsets_json: {"appointment": [30, 5], "control": [1440], "task": [15], "call": [30]}
    (минуты до срока; список — можно несколько будильников на тип события по умолчанию)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True, unique=True)
    digest_enabled: bool = True
    digest_hour: int = 8                      # час (0-23) присылки утренней сводки, по времени врача
    quiet_hours_start: int = 22               # тихие часы: с 22:00
    quiet_hours_end: int = 7                  # до 7:00 — пуши копятся, не шлём (кроме срочного)
    escalation_enabled: bool = True           # повторить пуш, если не открыт
    escalation_minutes: int = 10              # через сколько минут повторить (один раз)
    default_offsets_json: str = '{"appointment": [15], "control": [1440], "task": [15], "call": [30]}'
    push_appointment: bool = True             # какие типы разрешены пушем (в доп. к «в приложении» — всегда)
    push_control: bool = True
    push_task: bool = True
    push_call: bool = True
    push_billing: bool = True
    # сводка по выполненному: off | daily | weekly
    recap_mode: str = "off"
    recap_hour: int = 20                       # час присылки (по умолчанию вечер 20:00)
    recap_weekday: int = 6                      # для weekly: день недели (0=пн … 6=вс)
    version: int = 1
    created_at: datetime = Field(default_factory=now)


class ReminderAlert(SQLModel, table=True):
    """Один будильник к событию (Reminder или Appointment) — минут ДО срока.
    На одно событие может быть несколько записей (напр. 30 и 5 минут)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    entity_type: str = Field(index=True)      # reminder | appointment
    entity_id: int = Field(index=True)
    offset_minutes: int = 15                  # за сколько минут до due_at/starts_at
    fire_at: datetime = Field(index=True)     # вычисленное время срабатывания (due_at - offset)
    status: str = "pending"                   # pending | sent | escalated | cancelled
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)


class PushSubscription(SQLModel, table=True):
    """Подписка браузера на Web Push. doctor_id=None → подписка админ-канала (поддержка)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: Optional[int] = Field(default=None, foreign_key="doctor.id", index=True)
    is_admin_channel: bool = False
    endpoint: str = Field(default="", index=True)   # URL push-сервиса (для дедупа/поиска)
    p256dh: str = Field(default="", sa_column=Column(EncryptedStr))
    auth: str = Field(default="", sa_column=Column(EncryptedStr))
    user_agent: str = ""
    created_at: datetime = Field(default_factory=now)


class PushDelivery(SQLModel, table=True):
    """Журнал попыток доставки push — для мониторинга здоровья в админке.
    Без ПДн: только тип уведомления, платформа, успех/ошибка."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: Optional[int] = Field(default=None, index=True)
    kind: str = ""                            # тип уведомления
    platform: str = ""                        # ios | android | desktop | unknown
    ok: bool = True
    status_code: Optional[int] = None
    error: str = ""
    created_at: datetime = Field(default_factory=now, index=True)


class Dictation(SQLModel, table=True):
    """Смешанная голосовая запись. Расшифровка целиком → разметка на сегменты-намерения
    (разные пациенты, задачи, звонки, идеи). Текст храним, аудио — нет."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    text: str = Field(default="", sa_column=Column(EncryptedStr))
    status: str = "pending"                   # pending | confirmed | discarded
    idempotency_key: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=now)


class DictationSegment(SQLModel, table=True):
    """Один фрагмент-намерение из диктовки. Сопоставление с пациентом — детерминированной
    логикой (Задача 1); сам ИИ доступа к базе пациентов не имеет."""
    id: Optional[int] = Field(default=None, primary_key=True)
    dictation_id: int = Field(foreign_key="dictation.id", index=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    seg_type: str = "note"                    # patient_note | task | call | idea
    extracted_name: str = Field(default="", sa_column=Column(EncryptedStr))
    content: str = Field(default="", sa_column=Column(EncryptedStr))
    when_text: str = ""                       # «завтра в 12», «через 3 месяца» — как сказано
    resolved_patient_id: Optional[int] = Field(default=None, foreign_key="patient.id")
    status: str = "pending"                   # pending | assigned | committed | discarded
    created_at: datetime = Field(default_factory=now)


class PhotoBatch(SQLModel, table=True):
    """Загруженное фото, на котором может быть НЕСКОЛЬКО пациентов (список из отделения).
    Изображение хранится ВРЕМЕННО (зашифровано) до подтверждения разбивки — затем
    удаляется. Единственное осознанное исключение из принципа «фото не храним»."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    image_b64: str = Field(default="", sa_column=Column(EncryptedStr))   # временно, до подтверждения
    status: str = "pending"                   # pending | confirmed | discarded
    idempotency_key: str = Field(default="", index=True)   # защита от дублей при повторе загрузки
    created_at: datetime = Field(default_factory=now)


class PhotoFragment(SQLModel, table=True):
    """Фрагмент фото под одного пациента: своя область, свои распознанные данные,
    своя проверка личности. Данные фрагмента одного пациента НЕ видны в карте другого."""
    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="photobatch.id", index=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    region: str = ""                          # координаты области (JSON: x,y,w,h)
    extracted_name: str = Field(default="", sa_column=Column(EncryptedStr))
    extracted_dob: str = ""
    values_json: str = ""                     # распознанные значения (JSON)
    resolved_patient_id: Optional[int] = Field(default=None, foreign_key="patient.id")
    status: str = "pending"                   # pending | assigned | committed | discarded
    created_at: datetime = Field(default_factory=now)


class SourceDocument(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: Optional[int] = Field(default=None, foreign_key="patient.id", index=True)
    encounter_id: Optional[int] = Field(default=None, foreign_key="encounter.id", index=True)
    kind: str = "photo"                       # photo | pdf | voice
    storage_ref: str = ""                     # путь/ключ; очищается после распознавания
    extracted_text: str = ""                  # распознанный текст (храним ЕГО, не фото)
    ocr_status: str = "queued"                # queued | done | failed
    match_status: str = "ok"                  # ok | name_mismatch | dob_mismatch (защита №1)
    extracted_name: str = ""
    extracted_dob: str = ""
    image_purged: bool = False                # фото удалено после распознавания
    created_at: datetime = Field(default_factory=now)


class SafetyItem(SQLModel, table=True):
    """Блок безопасности первичного приёма. Три состояния на пункт."""
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    kind: str                                 # allergy|anticoag|surgery|chronic|consent
    state: str = "unknown"                    # unknown | none | present
    detail: str = ""
    updated_at: datetime = Field(default_factory=now)


class Prescription(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    encounter_id: Optional[int] = Field(default=None, foreign_key="encounter.id", index=True)
    drug_name: str
    dose: str = ""
    regimen: str = ""
    conflict_flag: bool = False
    override_reason: str = ""
    created_at: datetime = Field(default_factory=now)


class AdminAudit(SQLModel, table=True):
    """Журнал действий администрации/поддержки (кто из персонала что смотрел/делал).
    Ограничение: пока один общий админ-токен на команду — конкретный сотрудник не
    различается (появится при именных админ-аккаунтах). Фиксируем действие и цель."""
    id: Optional[int] = Field(default=None, primary_key=True)
    action: str = Field(index=True)      # напр. "GET /api/admin/usage/by-doctor"
    detail: str = ""                     # параметры запроса (без тела/секретов)
    created_at: datetime = Field(default_factory=now, index=True)


class SystemMeta(SQLModel, table=True):
    """Служебные пары ключ-значение (например, отпечаток FIELD_KEY для самопроверки)."""
    key: str = Field(primary_key=True)
    value: str = ""


class Subscription(SQLModel, table=True):
    """Подписка врача. Без активной подписки (кроме демо-аккаунта) — только просмотр,
    вся запись заблокирована (SubscriptionGateMiddleware)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    plan: str = "1m"                       # 1m | 3m | 6m | 12m
    status: str = "active"                 # active | cancelled | expired
    period_start: datetime = Field(default_factory=now)
    period_end: datetime
    amount: int = 0                        # уплачено, руб. (на момент покупки — фиксируем)
    auto_renew: bool = True
    payment_id: str = ""                   # id платежа у ЮKassa
    reminder5_sent: bool = False           # письмо «осталось 5 дней» уже отправлено
    reminder3_sent: bool = False           # письмо «осталось 3 дня» уже отправлено
    created_at: datetime = Field(default_factory=now)


class Notification(SQLModel, table=True):
    """Уведомление врачу: просроченный контроль, лимит расхода, срабатывание и т.п.
    dedup_key не даёт плодить дубли одного и того же события."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    kind: str = "info"                # overdue | limit | trigger | ocr | info
    level: str = "info"               # info | warn
    text: str = ""
    patient_id: Optional[int] = Field(default=None, foreign_key="patient.id")
    dedup_key: str = Field(default="", index=True)
    read: bool = False
    created_at: datetime = Field(default_factory=now, index=True)


class UsageRecord(SQLModel, table=True):
    """Учёт ИИ-операций для лимитов и аналитики расхода.
    kind: ocr (распознавание файла/снимка) | stt (расшифровка речи) | llm (агент/команда).
    units — «стоимость» (страницы/секунды/токены); для заглушек = 1 на операцию."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    kind: str = Field(index=True)
    units: int = 1
    detail: str = ""
    created_at: datetime = Field(default_factory=now, index=True)


class Reminder(SQLModel, table=True):
    """Задачи/напоминания в духе Todoist/Toki. Могут быть привязаны к пациенту."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    patient_id: Optional[int] = Field(default=None, foreign_key="patient.id")
    title: str
    due_at: Optional[datetime] = None
    kind: str = "task"                        # task | control | appointment | call
    project: str = "Входящие"                 # раздел (свой тег-список, как в Todoist)
    priority: int = 4                         # 1 (срочно) .. 4 (обычный) — как в Todoist
    repeat_days: Optional[int] = None         # legacy: повтор каждые N дней (совместимость)
    repeat_unit: str = ""                      # "" | day | week | month | year
    repeat_interval: int = 1                   # каждые N единиц (напр. каждые 2 месяца)
    labels: str = ""                          # через запятую: контроль,звонок,...
    source: str = "manual"                    # manual | voice | nl | filter
    status: str = "open"                      # open | done
    completed_at: Optional[datetime] = None   # когда выполнена (для раздела «Выполненные»)
    spawned_id: Optional[int] = None          # id авто-созданного повтора (для честной отмены)
    created_at: datetime = Field(default_factory=now)


class Appointment(SQLModel, table=True):
    """Запись на приём с конкретным временем — для календаря месяц/неделя/день."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    patient_id: int = Field(foreign_key="patient.id")
    starts_at: datetime = Field(index=True)
    kind: str = "repeat"                       # primary | repeat
    reason: str = ""
    status: str = "planned"                    # planned | done | cancelled


class VisitTemplate(SQLModel, table=True):
    """Пользовательский шаблон приёма врача (свой набор блоков). Автор и версия — по ТЗ."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    name: str = ""
    category: str = "Мои шаблоны"
    based_on: str = ""                         # код встроенного шаблона-основы (T0x), если есть
    additional: str = ""
    exam_docs: str = ""
    plan: str = ""
    version: int = 1
    created_at: datetime = Field(default_factory=now)


class VisitProtocol(SQLModel, table=True):
    """Структурированный протокол осмотра (поля как в ЕМИАС) — для переноса
    в государственную систему копированием по блокам."""
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    encounter_id: Optional[int] = Field(default=None, foreign_key="encounter.id", index=True)
    complaints: str = ""                       # Жалобы
    anamnesis_morbi: str = ""                  # Анамнез заболевания
    anamnesis_vitae: str = ""                  # Анамнез жизни
    objective: str = ""                        # Объективный статус (status praesens)
    status_localis: str = ""                   # Локальный статус
    diagnosis_code: str = ""                   # МКБ-10
    diagnosis_text: str = ""                   # Формулировка диагноза
    recommendations: str = ""                  # Назначения и рекомендации
    template_code: str = ""                    # какой шаблон использован (T0x или custom:ID)
    tpl_additional: str = ""                   # блок «Дополнительные поля» шаблона
    tpl_exam_docs: str = ""                    # блок «Осмотр и документы»
    tpl_plan: str = ""                         # блок «План и результат приёма»
    updated_at: datetime = Field(default_factory=now)


class VisitSession(SQLModel, table=True):
    """Сессия приёма. Нужна для защиты №2 (продолжить с тем же пациентом?)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    patient_id: int = Field(foreign_key="patient.id")
    started_at: datetime = Field(default_factory=now)
    last_active_at: datetime = Field(default_factory=now)
    status: str = "active"                    # active | paused | finished


class AuditEvent(SQLModel, table=True):
    """Append-only журнал. Несущая конструкция для юридической защиты."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: Optional[int] = None
    entity_type: str = ""
    entity_id: Optional[int] = None
    action: str = ""
    detail: str = ""
    created_at: datetime = Field(default_factory=now)


class Note(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    encounter_id: Optional[int] = Field(default=None, foreign_key="encounter.id", index=True)
    text: str = Field(sa_column=Column(EncryptedStr, nullable=False))
    source: str = "typed"                     # typed | voice
    created_at: datetime = Field(default_factory=now)


class AnalyticsEvent(SQLModel, table=True):
    """Обезличенная телеметрия использования — для админ-панели аналитики.
    В props НЕ кладём персональные данные пациентов, только факты использования."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: Optional[int] = Field(default=None, index=True)
    event: str = Field(index=True)            # feature.used, appointment.created, ...
    props: str = ""                           # JSON-строка без ПДн
    created_at: datetime = Field(default_factory=now)


class PatientDiagnosis(SQLModel, table=True):
    """Диагноз пациента. У пациента их несколько; один — «основной» (в шапке).
    История не затирается: снятый диагноз получает status=removed, но остаётся."""
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    code: str = ""                            # МКБ-10
    title: str = ""                           # официальное название из справочника
    wording: str = ""                         # формулировка врача
    status: str = "active"                    # active | removed
    is_primary: bool = False
    icd_version: str = "МКБ-10 (НСИ Минздрава M001)"
    encounter_id: Optional[int] = Field(default=None, foreign_key="encounter.id")
    created_at: datetime = Field(default_factory=now)
    removed_at: Optional[datetime] = None


class Trigger(SQLModel, table=True):
    """Сохранённое условие слежения (в духе Toki): когда показатель пересекает
    порог — система сама заводит контроль. Проверяется при поступлении данных
    и по расписанию."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    name: str = ""
    parameter_code: str = "psa_total"
    op: str = ">"                              # > < >= <=
    threshold: float = 4.0
    diagnosis_code: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=now)


# ============ 152-ФЗ: согласия и журнал доступа ============
class PatientConsent(SQLModel, table=True):
    """Согласие пациента на обработку данных о здоровье (спец. категория ПДн).
    Барьер: без активного granted-согласия приём вести нельзя.
    Из всех фото хранится ТОЛЬКО распознанный текст бланка (form_text), само фото
    после анализа удаляется (инвариант минимизации ПДн)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    kind: str = "data_processing"
    method: str = "electronic"                # paper | electronic | remote
    text_version: str = "v1"
    status: str = "granted"                   # granted | pending | revoked
    signer_name: str = Field(default="", sa_column=Column(EncryptedStr))  # кто подписал
    form_text: str = Field(default="", sa_column=Column(EncryptedStr))    # текст бланка (фото не храним)
    verified: bool = False                    # ИИ подтвердил корректность бланка
    verify_note: str = ""                     # пояснение проверки
    granted_at: datetime = Field(default_factory=now)
    revoked_at: Optional[datetime] = None


class AccessLog(SQLModel, table=True):
    """Журнал доступа к персональным данным (требование 152-ФЗ)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: Optional[int] = None
    patient_id: Optional[int] = None
    action: str = "view"                       # view | export | erase
    created_at: datetime = Field(default_factory=now)


# ============ Поддержка (адаптировано под наш стек: врач вместо tenant) ============
class SupportThread(SQLModel, table=True):
    """Одно обращение: переписка от первого вопроса до закрытия.
    Открытое обращение одно; закрытые остаются в истории."""
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    status: str = "open"                       # open | closed
    subject: str = ""                          # первая строка первого сообщения
    closed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)


class SupportMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    doctor_id: int = Field(foreign_key="doctor.id", index=True)
    thread_id: Optional[int] = Field(default=None, foreign_key="supportthread.id", index=True)
    author_name: str = ""
    from_staff: bool = False                    # True — поддержка, False — врач
    body: str
    read_at: Optional[datetime] = None          # когда прочитала противоположная сторона
    created_at: datetime = Field(default_factory=now)
