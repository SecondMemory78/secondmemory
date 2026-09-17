"""PDF-выписка пациента. Кириллица через вшитый DejaVuSans (в app/assets/fonts).

Поддерживает выбор разделов и период. Данные берём из того же экспорта, что и
JSON-выгрузка (право субъекта), поэтому выписка всегда согласована с картой.
"""
import io
import os
from datetime import datetime, date
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
        meta.append(f"Дата рождения: {str(p['birth_date'])[:10]}")
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
                rows.append([name, str(val), o.get("unit", ""), str(o.get("effective_date") or "")[:10]])
            story.append(_table(rows, [70 * mm, 30 * mm, 25 * mm, 30 * mm], base))

    if "prescriptions" in sections:
        rx = data.get("prescriptions", [])
        if rx:
            story.append(Paragraph(SECTION_TITLES["prescriptions"], h2))
            rows = [["Препарат", "Дозировка", "Дата"]]
            for r in rx:
                rows.append([r.get("drug_name", ""), r.get("dose", ""),
                             str(r.get("created_at") or "")[:10]])
            story.append(_table(rows, [75 * mm, 55 * mm, 30 * mm], base))

    if "notes" in sections:
        notes = [n for n in data.get("notes", []) if _in_period(n.get("created_at"), date_from, date_to)]
        if notes:
            story.append(Paragraph(SECTION_TITLES["notes"], h2))
            for n in notes:
                story.append(Paragraph(f"<b>{str(n.get('created_at') or '')[:10]}</b> — {n.get('text','')}", base))
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
