"""Поиск по доверенным источникам.

Правила, о которых договорились с врачом:
  • искать только по доверенному списку (app/reference/trusted_sources.json);
  • отдавать ТОЛЬКО цитату и ссылку — никаких выводов и советов от ИИ;
  • запрос в кеше обезличен: ни имени пациента, ни даты рождения;
  • кеш общий: первый врач наполняет его для остальных;
  • у ответа есть дата проверки, устаревшее перепроверяем (раз в 6 месяцев);
  • зарубежные источники помечаются EU/US и не выдаются за российские.

Сам выход в интернет появится с ключом, у которого есть веб-поиск. Пока
ищущая часть — заглушка: запрос ставится в очередь со статусом «нужен поиск».
"""
import json
import re
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from sqlmodel import Session, select

from .. import clock
from ..models import SourceLookup

REFRESH_AFTER = timedelta(days=183)        # полгода — как договорились
_PATH = Path(__file__).resolve().parent.parent / "reference" / "trusted_sources.json"

SCOPE_LABEL = {"rf": "", "eaeu": "ЕАЭС", "eu": "EU", "us": "US",
               "author": "первоисточник автора"}


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def sources() -> list[dict]:
    return _data()["sources"]


@lru_cache(maxsize=1)
def trusted_domains() -> dict:
    """домен → источник. Всё, чего здесь нет, показывать нельзя."""
    out = {}
    for src in sources():
        for d in src["domains"]:
            out[d.lower()] = src
    return out


def is_trusted(url: str) -> bool:
    """Ссылка из доверенного списка? Поддомены тоже считаются."""
    m = re.match(r"https?://([^/]+)", (url or "").strip(), re.I)
    if not m:
        return False
    host = m.group(1).lower().split(":")[0]
    for domain in trusted_domains():
        if host == domain or host.endswith("." + domain):
            return True
    return False


def source_for(url: str) -> dict | None:
    m = re.match(r"https?://([^/]+)", (url or "").strip(), re.I)
    if not m:
        return None
    host = m.group(1).lower().split(":")[0]
    for domain, src in trusted_domains().items():
        if host == domain or host.endswith("." + domain):
            return src
    return None


# ── обезличивание запроса ───────────────────────────────────────────────────
# Фамилии по окончанию НЕ ищем: такая регулярка резала «тамсулозин» и
# «аллопуринол» вместе с именами — два разных препарата давали один ключ кеша.
# Имена определяются по реальному списку пациентов, см. _patient_stems().
_DATE = re.compile(r"\b\d{2}[.\-/]\d{2}[.\-/]\d{4}\b")
_AGE = re.compile(r"\b\d{1,3}\s*(?:лет|года|год)\b", re.I)
_LONGNUM = re.compile(r"\b\d{6,}\b")        # номера полисов, заказов, ID


def _patient_stems(s, doctor_id: int | None = None) -> set:
    """Основы фамилий/имён пациентов. С doctor_id — только его пациенты,
    без него (админский путь сохранения) — всех, потому что кеш общий.

    Угадывать имя по окончанию нельзя: «тамсулозин», «амлодипин»,
    «аллопуринол» кончаются так же, как фамилии, и препарат вырезался бы
    вместе с именем — два разных лекарства давали один ключ кеша и цитату
    одного показали бы для другого. Поэтому работаем по реальному списку.
    """
    from sqlmodel import select as _select
    from ..models import Patient
    stems = set()
    try:
        q = _select(Patient)
        if doctor_id is not None:
            q = q.where(Patient.doctor_id == doctor_id)
        rows = s.exec(q).all()
    except Exception:
        return stems
    for p in rows:
        for name in (p.last_name, p.first_name, p.middle_name):
            n = (name or "").strip().lower()
            if len(n) >= 4:
                stems.add(n[:-1])          # основа: покрывает падежные формы
            elif len(n) >= 3:
                stems.add(n)
    return stems


def anonymize(text: str, patient_stems: set | None = None) -> str:
    """Убирает то, чем можно опознать пациента: даты, возраст, длинные номера
    и фамилии/имена пациентов врача. Названия препаратов не трогаем."""
    q = (text or "").strip()
    q = _DATE.sub(" ", q)
    q = _AGE.sub(" ", q)
    q = _LONGNUM.sub(" ", q)

    stems = patient_stems or set()
    if stems:
        kept = []
        for w in q.split():
            low = w.strip(" ,.;:()-—«»\"'").lower()
            if any(low.startswith(st) for st in stems if st):
                continue                   # это пациент — вырезаем
            kept.append(w)
        q = " ".join(kept)

    q = re.sub(r"\s{2,}", " ", q).strip(" ,.;:-—")
    return q


def is_anonymous(text: str, patient_stems: set | None = None) -> bool:
    """Проверка перед сохранением в общий кеш."""
    q = (text or "")
    if _DATE.search(q) or _LONGNUM.search(q):
        return False
    for w in q.split():
        low = w.strip(" ,.;:()-—«»\"'").lower()
        if any(low.startswith(st) for st in (patient_stems or set()) if st):
            return False
    return True


def normalize(text: str, patient_stems: set | None = None) -> str:
    """Ключ кеша: обезличенный запрос в нижнем регистре без лишних слов."""
    q = anonymize(text, patient_stems).lower()
    q = re.sub(r"[^а-яёa-z0-9/\s.,-]", " ", q)
    q = re.sub(r"\s{2,}", " ", q).strip()
    return q[:200]


# ── работа с кешем ──────────────────────────────────────────────────────────
def _view(row: SourceLookup) -> dict:
    stale = bool(row.checked_at and clock.now() - row.checked_at > REFRESH_AFTER)
    return {
        "query": row.query, "status": row.status,
        "quote": row.quote, "url": row.url,
        "source": row.source_title, "source_code": row.source_code,
        "scope": row.scope, "scope_label": SCOPE_LABEL.get(row.scope, row.scope),
        "checked_at": row.checked_at.isoformat() if row.checked_at else None,
        "stale": stale,
        "note": ("Проверено более полугода назад — сведения могли измениться."
                 if stale else ""),
    }


def lookup(s: Session, question: str, doctor_id: int | None = None) -> dict:
    """Ответ из кеша. Нет записи — ставим в очередь на поиск.

    Никогда не придумываем содержание: если поиска ещё не было, честно
    говорим «не проверено».
    """
    stems = _patient_stems(s, doctor_id) if doctor_id else set()
    key = normalize(question, stems)
    if not key:
        return {"status": "empty", "query": "", "note": "Пустой запрос"}

    row = s.exec(select(SourceLookup).where(SourceLookup.query == key)).first()
    if row is None:
        row = SourceLookup(query=key, status="pending")
        s.add(row); s.commit(); s.refresh(row)
        return {**_view(row), "note": "Не проверено: поиск по источникам ещё не выполнялся."}

    row.hits = (row.hits or 0) + 1
    s.add(row); s.commit(); s.refresh(row)
    if row.status == "ok" and _view(row)["stale"]:
        row.status = "pending"               # пора перепроверить
        s.add(row); s.commit(); s.refresh(row)
    return _view(row)


def save_result(s: Session, question: str, *, quote: str, url: str) -> dict:
    """Сохранить найденное. Ссылку вне доверенного списка не принимаем.

    Проверку обезличивания ведём по фамилиям ВСЕХ пациентов: запись уходит
    в общий кеш, который видят все врачи, и на этом пути врача-владельца нет.
    """
    stems = _patient_stems(s)
    key = normalize(question, stems)
    if not key:
        raise ValueError("Пустой запрос")
    if not is_anonymous(key, stems):
        raise ValueError("В запросе остались личные данные — сохранять нельзя")
    src = source_for(url)
    if not src:
        raise ValueError("Ссылка не из доверенного списка источников")

    row = s.exec(select(SourceLookup).where(SourceLookup.query == key)).first()
    if row is None:
        row = SourceLookup(query=key)
    row.quote = (quote or "").strip()[:2000]
    row.url = url.strip()
    row.source_code = src["code"]
    row.source_title = src["title"]
    row.scope = src.get("scope", "")
    row.status = "ok" if row.quote else "empty"
    row.checked_at = clock.now()
    s.add(row); s.commit(); s.refresh(row)
    return _view(row)


def pending(s: Session, limit: int = 100) -> list[dict]:
    """Запросы, по которым нужен поиск (для будущей автоматики и для админа)."""
    rows = s.exec(select(SourceLookup).where(SourceLookup.status == "pending")
                  .order_by(SourceLookup.hits.desc())).all()
    return [_view(r) | {"hits": r.hits} for r in rows[:limit]]
