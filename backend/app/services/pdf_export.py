"""PDF-выписка пациента. Кириллица через вшитый DejaVuSans (в app/assets/fonts).

Поддерживает выбор разделов и период. Данные берём из того же экспорта, что и
JSON-выгрузка (право субъекта), поэтому выписка всегда согласована с картой.
"""
import io
import os
from datetime import datetime, date
from .. import clock
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
_REGISTERED = False


def _ensure_fonts():
    global _REGISTERED
    if _REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))
    _REGISTERED = True


def _styles():
    ss = getSampleStyleSheet()
    base = ParagraphStyle("body", parent=ss["Normal"], fontName="DejaVu", fontSize=9, leading=13)
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName="DejaVu-Bold", fontSize=16, leading=20, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="DejaVu-Bold", fontSize=11, leading=15,
                        spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1e40af"))
    small = ParagraphStyle("small", parent=base, fontSize=8, textColor=colors.grey)
    return base, h1, h2, small


ALL_SECTIONS = ["observations", "prescriptions", "notes", "appointments", "protocol"]
SECTION_TITLES = {
    "observations": "Показатели",
    "prescriptions": "Назначения",
    "notes": "Заметки",
    "appointments": "Приёмы",
    "protocol": "Протокол приёма",
}


def _ru_date(value) -> str:
    """Дата для показа человеку — российский стандарт ДД.ММ.ГГГГ.
    Только для вывода: сравнения/сортировки в коде остаются на ISO-строках."""
    s = str(value or "")[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}.{s[5:7]}.{s[0:4]}"
    return s


def _ru_datetime(value) -> str:
    """Дата и время для показа человеку — ДД.ММ.ГГГГ ЧЧ:ММ."""
    s = str(value or "").replace("T", " ")
    if len(s) >= 16 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}.{s[5:7]}.{s[0:4]} {s[11:16]}"
    return _ru_date(value)


def _in_period(d_str, date_from, date_to):
    if not d_str:
        return True
    d = str(d_str)[:10]
    if date_from and d < date_from:
        return False
    if date_to and d > date_to:
        return False
    return True


def _table(rows, col_widths, base):
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
        ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fb")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d7e2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def build_pdf(data: dict, sections=None, date_from: str = "", date_to: str = "",
              doctor_name: str = "", param_labels: dict | None = None) -> bytes:
    _ensure_fonts()
    base, h1, h2, small = _styles()
    param_labels = param_labels or {}
    sections = [s for s in (sections or ALL_SECTIONS) if s in ALL_SECTIONS]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            title="Выписка пациента")
    story = []
    p = data.get("patient", {})
    fio = " ".join(x for x in [p.get("last_name"), p.get("first_name"), p.get("middle_name")] if x)
    story.append(Paragraph("Выписка из карты пациента", h1))
    meta = []
    if p.get("birth_date"):
        meta.append(f"Дата рождения: {_ru_date(p['birth_date'])}")
    diag = " · ".join(x for x in [p.get("diagnosis_code"), p.get("diagnosis_text")] if x)
    story.append(Paragraph(f"<b>{fio}</b>" + (f" · {meta[0]}" if meta else ""), base))
    if diag:
        story.append(Paragraph(f"Диагноз: {diag}", base))
    period = ""
    if date_from or date_to:
        period = f" · период: {date_from or '…'} — {date_to or '…'}"
    story.append(Paragraph(f"Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                           + (f" · врач: {doctor_name}" if doctor_name else "") + period, small))
    story.append(Spacer(1, 4))

    if "observations" in sections:
        obs = [o for o in data.get("observations", [])
               if o.get("status") == "confirmed" and _in_period(o.get("effective_date"), date_from, date_to)]
        obs.sort(key=lambda o: (o.get("parameter_code", ""), str(o.get("effective_date") or "")))
        if obs:
            story.append(Paragraph(SECTION_TITLES["observations"], h2))
            rows = [["Показатель", "Значение", "Ед.", "Дата"]]
            for o in obs:
                name = param_labels.get(o.get("parameter_code"), o.get("parameter_code"))
                val = o.get("value_num") if o.get("value_num") is not None else o.get("value_text", "")
                rows.append([name, str(val), o.get("unit", ""), _ru_date(o.get("effective_date"))])
            story.append(_table(rows, [70 * mm, 30 * mm, 25 * mm, 30 * mm], base))

    if "prescriptions" in sections:
        rx = data.get("prescriptions", [])
        if rx:
            story.append(Paragraph(SECTION_TITLES["prescriptions"], h2))
            rows = [["Препарат", "Дозировка", "Дата"]]
            for r in rx:
                rows.append([r.get("drug_name", ""), r.get("dose", ""),
                             _ru_date(r.get("created_at"))])
            story.append(_table(rows, [75 * mm, 55 * mm, 30 * mm], base))

    if "notes" in sections:
        notes = [n for n in data.get("notes", []) if _in_period(n.get("created_at"), date_from, date_to)]
        if notes:
            story.append(Paragraph(SECTION_TITLES["notes"], h2))
            for n in notes:
                story.append(Paragraph(f"<b>{_ru_date(n.get('created_at'))}</b> — {n.get('text','')}", base))
                story.append(Spacer(1, 2))

    if "appointments" in sections:
        appts = [a for a in data.get("appointments", []) if _in_period(a.get("starts_at"), date_from, date_to)]
        appts.sort(key=lambda a: str(a.get("starts_at") or ""))
        if appts:
            story.append(Paragraph(SECTION_TITLES["appointments"], h2))
            rows = [["Дата/время", "Тип", "Причина", "Статус"]]
            for a in appts:
                st = str(a.get("starts_at") or "").replace("T", " ")[:16]
                kind = "первичный" if a.get("kind") == "primary" else "повторный"
                rows.append([st, kind, a.get("reason", ""), a.get("status", "")])
            story.append(_table(rows, [35 * mm, 25 * mm, 55 * mm, 25 * mm], base))

    if "protocol" in sections:
        prots = data.get("protocol", [])
        if prots:
            story.append(Paragraph(SECTION_TITLES["protocol"], h2))
            for pr in prots:
                for field in ("complaints", "anamnesis", "exam", "plan"):
                    if pr.get(field):
                        label = {"complaints": "Жалобы", "anamnesis": "Анамнез",
                                 "exam": "Осмотр", "plan": "План"}[field]
                        story.append(Paragraph(f"<b>{label}:</b> {pr[field]}", base))
                story.append(Spacer(1, 4))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Документ сформирован системой «Вторая память». "
                           "Клинические решения принимает врач.", small))

    doc.build(story)
    return buf.getvalue()


def build_consent_pdf(patient: dict, consent: dict, doctor_name: str = "") -> bytes:
    """Доказательство согласия: карточка подписанта, текст версии согласия,
    метод, дата, кто подписал — и сама нарисованная подпись, если это ПЭП.
    Отдельный документ (не часть общей выписки), чтобы врач мог быстро
    предъявить именно факт согласия при споре."""
    import base64
    from reportlab.platypus import Image as RLImage
    _ensure_fonts()
    base, h1, h2, small = _styles()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            title="Подтверждение согласия")
    story = []
    fio = " ".join(x for x in [patient.get("last_name"), patient.get("first_name"),
                                patient.get("middle_name")] if x)
    story.append(Paragraph("Подтверждение согласия на обработку персональных данных", h1))
    story.append(Paragraph(f"<b>Пациент:</b> {fio}", base))
    if patient.get("birth_date"):
        story.append(Paragraph(f"<b>Дата рождения:</b> {_ru_date(patient['birth_date'])}", base))

    method_names = {"paper": "бумажный бланк", "electronic": "электронно на устройстве",
                    "remote": "удалённо"}
    story.append(Spacer(1, 6))
    rows = [
        ["Статус", "Действует" if consent.get("status") == "granted" else str(consent.get("status") or "")],
        ["Способ", method_names.get(consent.get("method"), consent.get("method") or "")],
        ["Версия текста согласия", consent.get("text_version") or ""],
        ["Подписал(а)", consent.get("signer_name") or ""],
        ["Дата и время", _ru_datetime(consent.get("granted_at"))],
        ["Врач", doctor_name or ""],
    ]
    if consent.get("es_agreement_version"):
        rows.append(["Соглашение о простой ЭП", consent["es_agreement_version"]])
    if consent.get("verify_note"):
        rows.append(["Примечание", consent["verify_note"]])
    story.append(_table([["Параметр", "Значение"]] + rows, [55 * mm, 105 * mm], base))

    sig = consent.get("signature") or ""
    if sig.startswith("data:image/"):
        story.append(Spacer(1, 10))
        story.append(Paragraph("Подпись пациента (простая электронная подпись):", h2))
        try:
            raw = base64.b64decode(sig.split(",", 1)[1])
            img = RLImage(io.BytesIO(raw), width=80 * mm, height=37 * mm)
            story.append(img)
        except Exception:
            story.append(Paragraph("(не удалось отобразить изображение подписи)", small))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Документ сформирован системой «Вторая память» на основании данных, "
        "сохранённых при оформлении согласия, и предназначен для подтверждения "
        "факта согласия при спорных ситуациях.", small))

    doc.build(story)
    return buf.getvalue()


def build_schedule_pdf(days: list, doctor_name: str = "", title: str = "Расписание") -> bytes:
    """Расписание на день/неделю для печати: приёмы и задачи по дням.

    Офлайн-сценарий (бумажный журнал, вахта), поэтому печатаем ровно то, что
    нужно в руках: время, пациент, тип приёма, повод, статус — и отдельно
    задачи дня. days: [{"day": "2026-10-15", "appointments": [...], "tasks": [...]}]
    """
    _ensure_fonts()
    base, h1, h2, small = _styles()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=14 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm, title=title)
    story = [Paragraph(title, h1)]
    if doctor_name:
        story.append(Paragraph(f"Врач: {doctor_name}", base))
    story.append(Paragraph(f"Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}", small))
    story.append(Spacer(1, 8))

    STATUS_RU = {"planned": "", "done": "завершён", "no_show": "не пришёл",
                 "cancelled": "отменён"}

    total_appts = total_tasks = 0
    for d in days:
        appts = d.get("appointments") or []
        tasks = d.get("tasks") or []
        total_appts += len(appts)
        total_tasks += len(tasks)
        story.append(Spacer(1, 6))
        story.append(Paragraph(_ru_date(d.get("day")), h2))

        if appts:
            rows = [["Время", "Пациент", "Тип", "Повод", "Статус"]]
            for a in appts:
                rows.append([
                    f"{a.get('time','')}–{a.get('ends_time','')}",
                    a.get("patient_name", ""),
                    "первичный" if a.get("kind") == "primary" else "повторный",
                    a.get("reason", ""),
                    STATUS_RU.get(a.get("status"), a.get("status") or ""),
                ])
            story.append(_table(rows, [24 * mm, 45 * mm, 24 * mm, 55 * mm, 22 * mm], base))
        else:
            story.append(Paragraph("Приёмов нет.", small))

        if tasks:
            story.append(Spacer(1, 4))
            rows = [["Время", "Задача"]]
            for t in tasks:
                rows.append([t.get("time", ""), t.get("title", "")])
            story.append(_table(rows, [24 * mm, 146 * mm], base))

    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Всего: приёмов {total_appts}, задач {total_tasks}.", base))
    story.append(Paragraph("Документ сформирован системой «Вторая память».", small))

    doc.build(story)
    return buf.getvalue()


# ── Памятка пациенту ────────────────────────────────────────────────────────
# Отдаётся человеку на руки: что изменилось, что принимать, что сдать, когда
# прийти. Это НЕ медицинский документ и не выписной эпикриз — врачебные
# документы описаны отдельно и собираются иначе.
#
# Правила, которых держимся (из ТЗ, раздел «Основные принципы»):
#   • не выдумывать отсутствующее: пустой раздел не печатается вовсе, вместо
#     него не появляется «без особенностей» или «состояние удовлетворительное»;
#   • только подтверждённое врачом: значения со статусом «ожидает проверки»
#     в памятку не попадают ни при каких условиях;
#   • у каждого факта дата — пациент должен видеть, к какому числу относится
#     значение.

# Насколько должно измениться значение, чтобы попасть в памятку.
# ТЗ запрещает печатать динамику подряд по всем показателям: она выводится,
# когда показатель связан с диагнозом, существенно изменился, определяет
# тактику или отмечен врачом. Связь с диагнозом и «определяет тактику» мы
# сейчас из данных не выводим, поэтому работает одно условие — существенное
# изменение. Порог вынесен сюда: цифру должен утвердить врач.
SIGNIFICANT_CHANGE = 0.20          # 20% от прежнего значения


def _worth_showing(prev: float, last: float, obs: dict) -> bool:
    if obs.get("for_handout"):     # врач отметил показатель сам — печатаем всегда
        return True
    if prev == 0:
        return last != 0
    return abs(last - prev) / abs(prev) >= SIGNIFICANT_CHANGE


def handout_sections(data: dict, when: date | None = None) -> list[dict]:
    """ЧТО попадает в памятку — отдельно от того, КАК это рисуется.

    Отбор здесь и есть правило, которое нужно проверять, поэтому он вынесен из
    отрисовки: текст внутри PDF закодирован подмножеством шрифта и словами по
    нему не проверяется.

    Каждый раздел: {"key", "title", "head", "rows"} либо {"key", "title", "text"}.
    Пустые разделы не возвращаются вовсе — документ не дополняется типовыми
    фразами там, где данных нет.
    """
    today = when or clock.now().date()
    out: list[dict] = []

    def iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else (v or "")

    # ── что изменилось: только подтверждённое и только где есть «было» ──────
    # Конфликтующие показатели исключаем: ТЗ прямо запрещает печатать данные,
    # по которым есть противоречие, до его разрешения врачом.
    conflicted = set(data.get("conflicts") or [])
    # Сведения со слов пациента в памятку не идут: пациент получит бумагу, где
    # его же слова напечатаны как результат обследования.
    obs = [o for o in (data.get("observations") or [])
           if o.get("status") != "pending"
           and o.get("parameter_code") not in conflicted
           and o.get("provenance") != "patient_words"]
    by_code: dict[str, list] = {}
    for o in obs:
        by_code.setdefault(o.get("parameter_code") or o.get("label") or "", []).append(o)

    rows = []
    for code, items in by_code.items():
        items = sorted(items, key=lambda x: iso(x.get("effective_date")))
        if len(items) < 2:
            continue                      # одного значения для «было → стало» мало
        prev, last = items[-2], items[-1]
        if prev.get("value_num") is None or last.get("value_num") is None:
            continue
        if not _worth_showing(prev["value_num"], last["value_num"], last):
            continue                      # незначимое колебание пациенту не нужно
        rows.append([last.get("label") or code,
                     f"{_num(prev['value_num'])} \u2192 {_num(last['value_num'])} {last.get('unit', '')}".strip(),
                     _ru_date(iso(last.get("effective_date")))])
    if rows:
        out.append({"key": "changes", "title": "Что изменилось",
                    "head": ["Показатель", "Было \u2192 стало", "Дата"], "rows": rows})

    # ── назначения. Задачи врача СЮДА НЕ ИДУТ: «снять катетер» — дело врача,
    #    пациент прочитает это как указание себе, а в заголовке задачи может
    #    стоять фамилия другого человека.
    rx = [r for r in (data.get("prescriptions") or [])
          if r.get("status") == "active" and r.get("confirmed", True)]
    def cat(r):
        return r.get("category") or "drug"

    meds = [r for r in rx if cat(r) in ("drug", "fluid")]
    # Что сделать — обследования, процедуры, консультации, повторный приём.
    todo = [r for r in rx if cat(r) in ("lab", "imaging", "procedure", "followup")]
    # Рекомендации — режим, питание, уход за устройством, самоконтроль,
    # ограничения. ТЗ выделяет их отдельным разделом.
    recs = [r for r in rx if cat(r) in ("diet", "activity", "care", "selfcontrol", "restriction", "other")]

    if meds:
        rows = []
        for r in meds:
            how = ", ".join(x for x in [r.get("dose", ""), r.get("frequency", ""), r.get("route", "")] if x)
            how = how or r.get("instruction", "") or r.get("regimen", "") or "по назначению врача"
            rows.append([r.get("drug_name") or "\u2014", how, r.get("duration", "") or "\u2014"])
        out.append({"key": "meds", "title": "Что принимать",
                    "head": ["Что", "Как принимать", "Сколько"], "rows": rows})

    if todo:
        rows = []
        for r in todo:
            when_s = _ru_date(iso(r.get("control_date"))) or r.get("duration", "") or "срок не задан"
            rows.append([r.get("instruction") or r.get("drug_name") or "\u2014",
                         r.get("indication", "") or "\u2014", when_s])
        out.append({"key": "todo", "title": "Что сделать до следующего визита",
                    "head": ["Что сделать", "Зачем", "К какому сроку"], "rows": rows})

    if recs:
        out.append({"key": "recs", "title": "Рекомендации",
                    "bullets": [
                        ((r.get("instruction") or r.get("drug_name") or "").strip()
                         + (f" — {r['indication']}" if r.get("indication") else ""))
                        for r in recs if (r.get("instruction") or r.get("drug_name"))
                    ]})

    # ── что было сделано ────────────────────────────────────────────────────
    # Только подтверждённые: предложенное ассистентом пациенту не отдаём.
    procs = [x for x in (data.get("procedures") or [])
             if x.get("status") != "cancelled" and x.get("confirmed", True)]
    if procs:
        rows = []
        for x in sorted(procs, key=lambda v: iso(v.get("performed_at")), reverse=True):
            rows.append([x.get("title") or x.get("name") or "\u2014",
                         _ru_date(iso(x.get("performed_at"))) or "дата не указана"])
        out.append({"key": "procedures", "title": "Что было сделано",
                    "head": ["Операция или процедура", "Когда"], "rows": rows})

    # ── активные устройства ─────────────────────────────────────────────────
    # По ТЗ для уролога это обязательный блок: если устройство остаётся с
    # пациентом, оно должно быть в документе, а отсутствие срока удаления —
    # повод предупредить врача (см. handout_warnings).
    devices = [d for d in (data.get("devices") or []) if d.get("active")]
    if devices:
        rows = []
        for d in devices:
            rows.append([_device_label(d),
                         _ru_date(iso(d.get("installed_at"))) or "дата не указана",
                         _ru_date(iso(d.get("due_at"))) or "срок не назначен"])
        out.append({"key": "devices", "title": "Установленные устройства",
                    "head": ["Что стоит", "Установлено", "Замена / удаление"],
                    "rows": rows})

    # ── когда обращаться срочно ─────────────────────────────────────────────
    # Только по тем устройствам, что реально стоят: универсальный список всем
    # пациентам ТЗ запрещает.
    signs = _urgent_signs([d.get("kind") for d in devices])
    if signs:
        out.append({"key": "urgent", "title": "Когда обратиться, не дожидаясь срока",
                    "bullets": signs})

    # ── ближайший приём ─────────────────────────────────────────────────────
    appts = [a for a in (data.get("appointments") or [])
             if iso(a.get("starts_at"))[:10] >= today.isoformat()]
    if appts:
        nearest = sorted(appts, key=lambda a: iso(a.get("starts_at")))[0]
        out.append({"key": "visit", "title": "Когда прийти",
                    "text": _ru_datetime(iso(nearest.get("starts_at")))})
    return out


def handout_warnings(data: dict) -> list[str]:
    """Что сказать ВРАЧУ перед печатью. В памятку это не попадает.

    ТЗ: предупредить, если у активного устройства не указан срок контроля.
    """
    out = []
    for d in (data.get("devices") or []):
        if not d.get("active"):
            continue
        name = _device_label(d)
        if not d.get("due_at"):
            out.append(f"{name}: не указан срок замены или удаления")
        if not d.get("installed_at"):
            out.append(f"{name}: не указана дата установки")
    return out


_DEVICE_NAMES = {"catheter": "Уретральный катетер", "nephrostomy": "Нефростома",
                 "stent": "Мочеточниковый стент"}


_SIDE_WORDS = {"left": "слева", "right": "справа", "both": "с обеих сторон"}


def _device_label(d: dict) -> str:
    """Название устройства для пациента. Сторона обязательна, если задана:
    перепутать бок — самая дорогая ошибка в этом блоке."""
    base = _DEVICE_NAMES.get(d.get("kind"), d.get("kind") or "Устройство")
    parts = [base]
    side = _SIDE_WORDS.get(d.get("side") or "")
    if side:
        parts.append(side)
    if (d.get("location") or "").strip():
        parts.append(d["location"].strip())
    mark = (d.get("device_label") or "").strip()
    out = " ".join(parts)
    return f"{out} ({mark})" if mark else out


def _urgent_signs(kinds) -> list[str]:
    """Признаки срочного обращения по установленным устройствам.

    Список лежит в reference/urgent_signs.json и должен быть утверждён врачом:
    пока reviewed_by_doctor = false, он используется, но это отмечено в файле.
    Ничего не выдумываем на лету — только то, что в справочнике.
    """
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "reference", "urgent_signs.json")
    try:
        with open(path, encoding="utf-8") as f:
            ref = json.load(f)
    except Exception:
        return []
    seen, out = set(), []
    for k in kinds:
        for sign in (ref.get("by_device", {}).get(k, {}) or {}).get("signs", []):
            if sign not in seen:
                seen.add(sign); out.append(sign)
    return out


def build_patient_handout(data: dict, doctor: dict, patient_name: str = "",
                          when: date | None = None) -> bytes:
    """Памятка пациенту на руки. Не медицинский документ и не выписной эпикриз."""
    _ensure_fonts()
    base, h1, h2, small = _styles()
    lead = ParagraphStyle("lead", parent=base, fontSize=10, leading=15)
    note = ParagraphStyle("note", parent=small, fontSize=8, leading=11)
    today = when or clock.now().date()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm, title="Памятка пациенту")
    story = [Paragraph("Памятка пациенту", h1)]
    doctor_line = ", ".join(x for x in [doctor.get("full_name", ""), doctor.get("specialty", "")] if x)
    if doctor_line:
        story.append(Paragraph(doctor_line, small))
    story.append(Paragraph(f"{patient_name.strip() or 'Пациент'} \u00b7 {_ru_date(today.isoformat())}", small))
    story.append(Spacer(1, 8))

    widths = {"changes": [70 * mm, 60 * mm, 40 * mm],
              "meds": [60 * mm, 70 * mm, 40 * mm],
              "todo": [80 * mm, 50 * mm, 40 * mm],
              "devices": [78 * mm, 45 * mm, 47 * mm],
              "procedures": [110 * mm, 60 * mm]}

    sections = handout_sections(data, when=today)
    for sec in sections:
        story.append(Paragraph(sec["title"], h2))
        if "text" in sec:
            story.append(Paragraph(sec["text"], lead))
        elif "bullets" in sec:
            for b in sec["bullets"]:
                story.append(Paragraph("\u2022 " + b, base))
        else:
            rows = [sec["head"]] + [[Paragraph(str(c), base) for c in r] for r in sec["rows"]]
            story.append(_table(rows, widths.get(sec["key"], [60 * mm, 60 * mm, 50 * mm]), base))

    if not sections:
        story.append(Paragraph("На эту дату сведений для памятки нет.", lead))

    # Схема, которую врач начертил и объяснил. Ради этого рисование и делалось:
    # бумажка с объяснением теряется, а памятку пациент уносит целиком.
    for png in (data.get("drawings") or [])[:2]:
        try:
            story.append(Paragraph("Схема", h2))
            story.append(_image_from_data_url(png))
        except Exception:
            pass                      # битый рисунок не должен ронять памятку

    story.append(Spacer(1, 16))
    story.append(Paragraph("Врач ______________________ / подпись /", base))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Памятка составлена лечащим врачом по данным приёма. Это не медицинский документ "
        "и не заменяет консультацию. При ухудшении самочувствия обратитесь к врачу, "
        "не дожидаясь назначенного срока.", note))

    doc.build(story)
    return buf.getvalue()


def _image_from_data_url(data_url: str):
    """PNG строкой data: → картинка для документа."""
    import base64
    from reportlab.platypus import Image as RLImage
    raw = base64.b64decode(data_url.split(",", 1)[1])
    buf = io.BytesIO(raw)
    img = RLImage(buf)
    # Вписываем по ширине полосы, высоту считаем по пропорции
    max_w = 170 * mm
    ratio = img.imageHeight / img.imageWidth if img.imageWidth else 0.6
    img.drawWidth = max_w
    img.drawHeight = max_w * ratio
    return img


def _num(v) -> str:
    """Число по-русски: 4,82 вместо 4.82; целое — без хвоста."""
    if v is None:
        return "—"
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")
