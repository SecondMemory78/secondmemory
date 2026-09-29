"""Диктовка нескольких назначений одной фразой.

Спецификация, п.21: врач диктует подряд, система распознаёт отдельные сущности,
показывает результат разбора и запрашивает подтверждение. Ничего не сохраняем
молча; предложение ИИ не становится назначением без врача (п.18).
"""
import re

from . import ai

# Грубая классификация по ключевым словам — когда модель недоступна.
_RULES = [
    ("fluid", r"питьев\w*|жидкост\w*|воды|пить\b"),
    ("diet", r"диет\w*|питани\w*|соль|солён\w*|алкогол\w*"),
    ("activity", r"нагрузк\w*|ходьб\w*|упражнен\w*|лфк|кегел\w*|спорт"),
    ("care", r"перевязк\w*|уход\b|катетер\w*|стом\w*|дренаж\w*|рана|раны"),
    ("selfcontrol", r"дневник\w*|измер\w*|самоконтрол\w*|давлени\w*|вес\b|диурез"),
    ("lab", r"анализ\w*|пса\b|psa\b|креатинин\w*|посев\w*|кровь|мочи\b"),
    ("imaging", r"узи\b|кт\b|мрт\b|рентген\w*|урофлоуметри\w*|цистоскопи\w*"),
    ("procedure", r"процедур\w*|операци\w*|биопси\w*|физиотерапи\w*"),
    ("restriction", r"ограничи\w*|запрет\w*|нельзя|исключить|воздержат\w*"),
    ("followup", r"контрольн\w*\s+осмотр|повторн\w*\s+(?:осмотр|приём|прием|консультаци)|"
                 r"явк\w*|контроль через"),
]

_DOSE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:мг|миллиграмм\w*|мкг|микрограмм\w*|г|грамм\w*|"
    r"мл|миллилитр\w*|л|литр\w*|таб\w*|капс\w*|ед|единиц\w*)\b", re.I)
_DURATION = re.compile(r"\b(?:на\s+)?\d+\s*(?:день|дня|дней|недел\w*|месяц\w*|год\w*)\b", re.I)
_FREQ = re.compile(r"\b(?:\d+\s*раз\w*\s*(?:в|/)?\s*(?:день|сут\w*|недел\w*)|"
                   r"ежедневн\w*|на\s+ночь|утром|вечером|по\s+требовани\w*)\b", re.I)


def _classify(chunk: str) -> str:
    low = chunk.lower()
    for cat, rx in _RULES:
        if re.search(rx, low):
            return cat
    if _DOSE.search(low):
        return "drug"                     # есть доза — почти наверняка препарат
    return "other"


# Слова, с которых начинается НОВОЕ назначение. Нужны потому, что распознанная
# речь приходит БЕЗ знаков препинания: «тадалафил 5 мг раз в день месяц питьевой
# режим до двух литров контроль через месяц» — делить по запятым бесполезно.
_STARTERS = re.compile(
    r"(?=(?:"
    r"питьев\w*\s+режим|режим\s+питья|"
    r"питани\w*|диет\w*|"
    r"ограничи\w*|исключи\w*|запрет\w*|нельзя\b|воздержат\w*|"
    r"контрольн\w*\s+осмотр|контроль\s+через|повторн\w*\s+(?:осмотр|приём|прием|консультаци)|явка\b|"
    r"контроль\s+\w+|сдать\b|анализ\w*|посев\w*|"
    r"узи\b|кт\b|мрт\b|рентген\w*|цистоскопи\w*|урофлоуметри\w*|"
    r"перевязк\w*|уход\s+за|"
    r"дневник\w*|измер\w*|самоконтрол\w*|"
    r"ходьб\w*|упражнени\w*|лфк\b|гимнастик\w*"
    r"))", re.I)

# Препарат: слово + доза рядом («тадалафил 5 мг», «омник 0,4 мг»)
_DRUG_WITH_DOSE = re.compile(
    r"\b([А-ЯЁA-Z][а-яёa-z\-]{3,}|[а-яёa-z\-]{4,})\s+(?=\d+(?:[.,]\d+)?\s*"
    r"(?:мг|миллиграмм\w*|мкг|микрограмм\w*|г\b|грамм\w*|мл\b|таб\w*|капс\w*))", re.I)

_LEAD = re.compile(r"^\s*(?:назнач\w*|выпиши|пропиши|добавь|поставь|рекомендую|"
                   r"а\s+также|также|и\s+ещ[её]|ещ[её])\s*", re.I)


def _cut_points(t: str) -> list:
    """Позиции, где начинается новое назначение."""
    points = {0}
    for m in re.finditer(r"[;,]|\s+и\s+|\.\s+", t):     # если знаки всё же есть
        if m.group(0) in (",", ";") and re.match(r"^\d", t[m.end():m.end() + 1] or ""):
            continue                                       # «0,4 мг» — не разрываем число
        points.add(m.end())
    for m in _STARTERS.finditer(t):
        points.add(m.start())
    for m in _DRUG_WITH_DOSE.finditer(t):                 # начало препарата с дозой
        points.add(m.start(1))
    return sorted(p for p in points if 0 <= p < len(t))


def rule_split(text: str) -> list:
    """Делим диктовку на отдельные назначения — по смысловым словам, а не только
    по знакам препинания (в распознанной речи их нет)."""
    t = (text or "").strip()
    if not t:
        return []
    cuts = _cut_points(t)
    parts = []
    for i, start in enumerate(cuts):
        end = cuts[i + 1] if i + 1 < len(cuts) else len(t)
        chunk = t[start:end].strip(" .,;:-—")
        if len(chunk) < 3:
            continue
        # слишком короткий кусок — это хвост предыдущего («ограничить» + «нагрузки»)
        if parts and len(chunk.split()) <= 1 and len(parts[-1].split()) <= 2:
            parts[-1] = f"{parts[-1]} {chunk}"
            continue
        if parts and len(parts[-1].split()) <= 1:
            parts[-1] = f"{parts[-1]} {chunk}"
            continue
        parts.append(chunk)

    out = []
    for p in parts:
        p = _LEAD.sub("", p).strip(" .,;:-—")
        if len(p) < 3:
            continue
        cat = _classify(p)
        dose_m, dur_m, freq_m = _DOSE.search(p), _DURATION.search(p), _FREQ.search(p)
        # объём жидкости — это не доза препарата, в поле дозы ему не место
        dose = dose_m.group(0) if (dose_m and cat == "drug") else ""
        dur = dur_m.group(0) if dur_m else ""
        freq = freq_m.group(0) if freq_m else ""
        name = p
        for cut in (dose, dur, freq):
            if cut:
                name = name.replace(cut, " ")
        name = re.sub(r"\s{2,}", " ", name)
        name = re.sub(r"\s+(?:и|а|до)$", "", name.strip(" ,.-—")).strip(" ,.-—")
        out.append({"drug_name": (name or p)[:200], "category": cat, "dose": dose,
                    "route": "", "frequency": freq, "duration": dur,
                    "indication": "", "instruction": "", "control": "",
                    "confidence": 0.5})
    return out


def parse(text: str) -> dict:
    """Предпросмотр: список распознанных назначений + чем разобрано."""
    by_model = ai.parse_prescriptions(text)
    items, source = (by_model, "ии") if by_model else (rule_split(text), "правила")
    return {
        "transcript": text,
        "source": source,
        "items": items,
        "status": "предложение ИИ — не назначение, пока врач не подтвердит",
        "note": "Ничего не сохранено. Проверьте состав и подтвердите нужные.",
    }
