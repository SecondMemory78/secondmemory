"""Диктовка → разделы протокола приёма.

Правила из «Структуры консультации»:
  • ничего не додумывать — заполняем только то, что врач реально сказал;
  • отсутствие данных должно отличаться от нормы («без особенностей» не пишем);
  • результат разбора показываем врачу и просим подтверждение, молча не сохраняем;
  • происхождение факта помечаем: извлечено ИИ, требует проверки.

Сначала пробуем модель, при её недоступности — разбор по ключевым словам.
"""
import re

from . import ai

# «Жалобы: ...», «Анамнез заболевания — ...», «Осмотр ...»
_MARKERS = [
    ("complaints", r"жалоб\w*"),
    ("anamnesis_morbi", r"анамнез\w*\s+заболевани\w*|анамнез\s+болезни|история\s+болезни"),
    ("anamnesis_vitae", r"анамнез\w*\s+жизни|сопутствующ\w*|аллерги\w*|принимает"),
    ("objective", r"объективн\w*|общее\s+состояние|осмотр\b"),
    ("status_localis", r"локальн\w*\s+статус|status\s+localis|урологическ\w*\s+статус"),
    ("diagnosis_text", r"диагноз\w*"),
    ("recommendations", r"рекомендаци\w*|назначени\w*|план\b"),
]


def rule_split(text: str) -> dict:
    """Разбор по явным словам-маркерам. Без маркеров — ничего не выдумываем."""
    t = (text or "").strip()
    if not t:
        return {}
    pattern = "|".join(f"(?P<{key}>{rx})" for key, rx in _MARKERS)
    hits = list(re.finditer(rf"(?:^|[.;\n])\s*(?:{pattern})\s*[:\-—]?\s*", t, re.I))
    if not hits:
        return {"unsorted": t}              # маркеров нет — пусть врач разложит сам

    out, prev_key, prev_end = {}, None, None
    for m in hits:
        key = m.lastgroup
        if prev_key is not None:
            chunk = t[prev_end:m.start()].strip(" .;\n—-")
            if chunk:
                out[prev_key] = (out.get(prev_key, "") + " " + chunk).strip()
        elif m.start() > 0:
            head = t[:m.start()].strip(" .;\n—-")
            if head:
                out["unsorted"] = head
        prev_key, prev_end = key, m.end()
    tail = t[prev_end:].strip(" .;\n—-")
    if prev_key and tail:
        out[prev_key] = (out.get(prev_key, "") + " " + tail).strip()
    return {k: v for k, v in out.items() if v}


def parse(text: str) -> dict:
    """Итог для предпросмотра: разделы + чем разобрано + пометка достоверности."""
    by_model = ai.parse_protocol(text)
    if by_model:
        sections, source = by_model, "ии"
    else:
        sections, source = rule_split(text), "правила"
    return {
        "transcript": text,
        "source": source,                      # чем разобрано — видно врачу
        "sections": [
            {"key": k, "label": ai.PROTOCOL_SECTIONS.get(k, "Не разобрано"), "text": v}
            for k, v in sections.items()
        ],
        # статус факта по «Структуре консультации»
        "status": "извлечено ИИ, требует проверки",
        "note": "Ничего не сохранено. Проверьте и подтвердите — пустые разделы "
                "оставлены пустыми намеренно.",
    }
