"""Разметка смешанной диктовки на сегменты-намерения.

ВАЖНО: это чисто ТЕКСТОВАЯ задача — ИИ размечает текст и достаёт имя/дату/содержание,
но доступа к базе пациентов не имеет. Сопоставление с карточками делает наш код
(determined логика Задачи 1). Сейчас — эвристика; с ключами Yandex GPT тело функции
заменяется на LLM-разметку, контракт тот же.

Сегмент: {seg_type, name:{last,first,middle}, birth_date, content, when_text}.
seg_type: patient_note | task | call | idea
"""
import re

_CALL = ("позвон", "перезвон", "звонок", "набрать")
_TASK = ("напомн", "записать", "контрол", "проверить", "назначить приём", "запланир")
_NAME_RE = re.compile(r"\b([А-ЯЁ][а-яё]+(?:ов|ев|ин|ын|ский|ская|ко|ук|юк|ич|ова|ева|ина))\b")


def _split_sentences(text: str):
    parts = re.split(r"[.;\n]+|(?<=[а-яё])\s+(?=[А-ЯЁ][а-яё]+(?:ов|ев|ин|ский|ова|ева))", text)
    return [p.strip() for p in parts if p.strip()]


def _classify(sentence: str) -> str:
    low = sentence.lower()
    if any(w in low for w in _CALL):
        return "call"
    if any(w in low for w in _TASK) or "завтра" in low or "через" in low:
        return "task"
    if _NAME_RE.search(sentence):
        return "patient_note"
    return "idea"


def _when(sentence: str) -> str:
    low = sentence.lower()
    m = re.search(r"(завтра|послезавтра|сегодня|через\s+\d+\s+[а-яё]+)(?:\s+в\s+\d{1,2}(?::\d{2})?)?", low)
    return m.group(0) if m else ""


def segment(text: str, sim=None):
    """Разметка диктовки. sim (список готовых сегментов) — для отладки/тестов и демо."""
    if sim:
        out = []
        for x in sim:
            out.append({"seg_type": x.get("seg_type", "note"),
                        "name": {"last": x.get("last_name", ""), "first": x.get("first_name", ""),
                                 "middle": x.get("middle_name", "")},
                        "birth_date": x.get("birth_date", ""),
                        "content": x.get("content", ""), "when_text": x.get("when_text", "")})
        return out
    out = []
    for sent in _split_sentences(text or ""):
        seg_type = _classify(sent)
        nm = _NAME_RE.search(sent)
        last = nm.group(1) if nm else ""
        out.append({"seg_type": seg_type,
                    "name": {"last": last, "first": "", "middle": ""},
                    "birth_date": "", "content": sent, "when_text": _when(sent)})
    return out
