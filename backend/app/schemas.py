from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel


class PatientIn(BaseModel):
    last_name: str
    first_name: str
    middle_name: str = ""
    birth_date: Optional[date] = None
    sex: str = ""
    phone: str = ""
    diagnosis_code: str = ""
    diagnosis_text: str = ""
    external_system: str = ""
    external_value: str = ""


class ObservationIn(BaseModel):
    parameter_code: str
    value_num: Optional[float] = None
    value_text: Optional[str] = None
    unit: str = ""
    effective_date: Optional[date] = None
    status: str = "confirmed"


class SafetyIn(BaseModel):
    kind: str
    state: str
    detail: str = ""


class PrescriptionIn(BaseModel):
    """Универсальное назначение: и лекарство, и режим/контроль/ограничение."""
    drug_name: str                       # ЧТО (название или краткая формулировка)
    dose: str = ""
    regimen: str = ""
    override_reason: str = ""

    category: str = "drug"
    indication: str = ""                 # ЗАЧЕМ
    instruction: str = ""                # КАК
    route: str = ""
    frequency: str = ""
    duration: str = ""
    starts_on: Optional[date] = None
    control: str = ""
    control_date: Optional[date] = None
    source: str = "doctor"
    priority: str = "normal"
    status: str = "active"


class PrescriptionPatch(BaseModel):
    """Изменение назначения. Причина нужна: история должна быть объяснимой."""
    reason: str = ""
    dose: Optional[str] = None
    regimen: Optional[str] = None
    indication: Optional[str] = None
    instruction: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    starts_on: Optional[date] = None
    control: Optional[str] = None
    control_date: Optional[date] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    cancel_reason: Optional[str] = None
    effect: Optional[str] = None
    confirmed: Optional[bool] = None


class ReminderIn(BaseModel):
    title: str
    due_at: Optional[datetime] = None
    kind: str = "task"
    patient_id: Optional[int] = None
    project: str = "Входящие"
    priority: int = 4
    repeat_days: Optional[int] = None
    repeat_unit: str = ""
    repeat_interval: int = 1
    labels: str = ""
    source: str = "manual"


class ProtocolIn(BaseModel):
    complaints: str = ""
    anamnesis_morbi: str = ""
    anamnesis_vitae: str = ""
    objective: str = ""
    status_localis: str = ""
    diagnosis_code: str = ""
    diagnosis_text: str = ""
    recommendations: str = ""
    template_code: str = ""
    tpl_additional: str = ""
    tpl_exam_docs: str = ""
    tpl_plan: str = ""


class AppointmentIn(BaseModel):
    patient_id: int
    starts_at: str          # ISO datetime
    kind: str = "repeat"    # primary | repeat
    reason: str = ""
    duration_min: int = 20  # длительность приёма, мин


class QuickReminderIn(BaseModel):
    text: str
    patient_id: Optional[int] = None


class CohortQuery(BaseModel):
    diagnosis_code: Optional[str] = None
    parameter_code: Optional[str] = None
    op: Optional[str] = None          # ">" | "<" | ">=" | "<="
    threshold: Optional[float] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
