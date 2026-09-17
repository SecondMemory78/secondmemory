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
    drug_name: str
    dose: str = ""
    regimen: str = ""
    override_reason: str = ""


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
