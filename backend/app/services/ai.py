"""Слой ИИ с подключаемыми провайдерами.

Выбор провайдера — переменной окружения:
    AI_PROVIDER = yandex | gigachat | stub   (по умолчанию stub)

Пока не заданы ключи — работает заглушка, поэтому проект запускается без
внешних сервисов. Как только появятся ключи Yandex Cloud / Сбера — переключение
делается одной переменной, контракты функций не меняются.

Роли (по итогам анализа):
  • распознавание (STT/OCR) — Yandex SpeechKit + Vision OCR;
  • агент команд (NLU) — YandexGPT (function calling), альтернатива — GigaChat Pro.
"""
import logging
import os
from datetime import datetime

from .. import clock

_WD_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

_log = logging.getLogger("secondmemory.ai")

PROVIDER = os.getenv("AI_PROVIDER", "stub").lower()


def _provider() -> str:
    """Какой провайдер использовать в ЭТОМ запросе.

    Демо-аккаунт всегда работает на заглушках, даже когда ключи подключены:
    витрина открыта всем без регистрации, и каждый её посетитель иначе тратил
    бы платные запросы к Яндексу. Ограничить это лимитами нельзя — демо-врач
    каждый раз новый.
    """
    try:
        from ..deps import current_is_demo
        if current_is_demo():
            return "stub"
    except Exception:
        pass          # вне запроса (планировщик, тесты) — обычный режим
    return PROVIDER

# --- ключи (берутся из окружения; в репозиторий не коммитятся) ---
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")


class NotConfigured(Exception):
    pass


# ============================ STT: речь → текст ============================
class AIError(RuntimeError):
    """ИИ-сервис не отработал. Показываем врачу честную ошибку, а не заглушку."""


def transcribe(audio_bytes: bytes, audio_format: str = "") -> str:
    # ВАЖНО: заглушка допустима ТОЛЬКО в демо-режиме (PROVIDER=stub). Если ИИ
    # подключён, но не ответил — отдаём ошибку. Иначе врач получает придуманный
    # текст и не понимает, что распознавание не сработало.
    if _provider() == "yandex":
        try:
            return _yandex_stt(audio_bytes, audio_format)
        except Exception as e:
            raise AIError(_explain(e, "распознать речь")) from e
    if _provider() == "gigachat":
        try:
            return _gigachat_stt(audio_bytes)
        except Exception as e:
            raise AIError(_explain(e, "распознать речь")) from e
    return _stub_transcript()


def _explain(e: Exception, what: str) -> str:
    """Короткое понятное объяснение для врача (без ключей и внутренностей).

    Заодно пишем причину в журнал сервера. Без этого отказ провайдера уходил
    наверх как безликая «ошибка сервера», и разбираться приходилось вслепую:
    именно так случилось с распознаванием речи на iPhone, где Яндекс отклонял
    формат звука, а в логе была только строка «502».
    """
    detail = ""
    resp = getattr(e, "response", None)
    if resp is not None:
        try:
            detail = f" (код {resp.status_code}: {resp.text[:160]})"
        except Exception:
            detail = ""
    _log.warning("ИИ: не удалось %s%s [%s: %s]", what, detail, type(e).__name__, e)
    return f"Не удалось {what}{detail}"


# ============================ OCR: фото/PDF → текст+значения ============================
def ocr_extract(image_bytes: bytes) -> dict:
    if _provider() == "yandex":
        try:
            return _yandex_ocr(image_bytes)
        except Exception as e:
            raise AIError(_explain(e, "распознать документ")) from e
    return _stub_ocr()


# ============================ NLU: команда врача → намерение ============================
def parse_command(text: str, context: dict | None = None) -> dict | None:
    """Разобрать произвольную команду врача в структуру. None — если не смогли.

    Возврат None означает «не понял» — вызывающий код откатывается на
    детерминированные правила. Никаких догадок: если модель не уверена или
    ответила мусором, лучше честно вернуть None, чем выполнить не то действие.
    """
    if not (text or "").strip():
        return None
    try:
        if _provider() == "yandex":
            return _yandex_parse_command(text, context or {})
    except Exception:
        pass            # деградация до правил — приём не ломаем
    return None


# ============================ Заглушки ============================
def _stub_transcript() -> str:
    # То же самое: в демо речь не распознаётся, отдаём заведомо примерный текст.
    return ("Пример расшифровки (демо): пациент отмечает учащённое ночное "
            "мочеиспускание, направлен на контроль PSA через 3 месяца.")


def _stub_ocr() -> dict:
    # Заглушка отвечает одним и тем же, что бы ни прислали. В демо это видно
    # прямо в тексте: иначе врач фотографирует свой анализ, получает чужие
    # цифры и решает, что распознавание врёт.
    return {
        "text": ("ПРИМЕР РАСПОЗНАВАНИЯ (демо): настоящий документ здесь не читается\n"
                 "ПСА общий 4.82 нг/мл\nКреатинин 118 мкмоль/л\nдата 09.03.2026"),
        "extracted_name": "",
        "extracted_dob": "",
        "values": [
            {"parameter_code": "psa_total", "value_num": 4.82, "unit": "нг/мл", "effective_date": "2026-03-09"},
            {"parameter_code": "creatinine", "value_num": 118, "unit": "мкмоль/л", "effective_date": "2026-03-09"},
        ],
    }


# ============================ Yandex (боевые вызовы) ============================
def _require_yandex():
    if not (YANDEX_API_KEY and YANDEX_FOLDER_ID):
        raise NotConfigured("YANDEX_API_KEY / YANDEX_FOLDER_ID не заданы")


def _yandex_stt(audio_bytes: bytes, audio_format: str = "") -> str:
    _require_yandex()
    import httpx
    # SpeechKit v1 (короткое аудио). Для длинного — асинхронный режим v3.
    # Контейнер важен: браузерный webm SpeechKit НЕ принимает («ogg header has
    # not been found»), поэтому фронт присылает lpcm 16 кГц моно.
    params = {"folderId": YANDEX_FOLDER_ID, "lang": "ru-RU"}
    if audio_format == "lpcm":
        params["format"] = "lpcm"
        params["sampleRateHertz"] = "16000"
    r = httpx.post(
        "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
        params=params,
        headers={"Authorization": f"Api-Key {YANDEX_API_KEY}"},
        content=audio_bytes, timeout=30,
    )
    r.raise_for_status()
    return r.json().get("result", "")


def _sniff_mime(data: bytes) -> str:
    """Тип файла по сигнатуре: Vision ждёт конкретный mimeType, не просто «image»."""
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"                      # фото с камеры — почти всегда jpeg


# Vision не принимает всё подряд: есть предел по размеру и разрешению, а iPhone
# по умолчанию снимает в HEIC, который сервис не понимает. Готовим файл заранее,
# иначе «фото не распознаётся» без внятной причины.
_VISION_MAX_BYTES = 9 * 1024 * 1024
_VISION_MAX_SIDE = 4000


def _is_heic(data: bytes) -> bool:
    head = data[:32]
    return b"ftyp" in head and any(tag in head for tag in
                                   (b"heic", b"heix", b"hevc", b"heif", b"mif1"))


def prepare_image(data: bytes) -> bytes:
    """Ужимаем большое фото и отсекаем неподдерживаемые форматы."""
    if _is_heic(data):
        raise AIError("Формат HEIC (фото с iPhone) не поддерживается распознаванием. "
                      "Сохраните снимок как JPEG или измените формат камеры на «Совместимый».")
    if data[:4] == b"%PDF" or len(data) <= _VISION_MAX_BYTES:
        try:
            from PIL import Image
        except Exception:
            return data                      # без Pillow — отправляем как есть
        if data[:4] == b"%PDF":
            return data
        try:
            import io
            img = Image.open(io.BytesIO(data))
            if max(img.size) <= _VISION_MAX_SIDE and len(data) <= _VISION_MAX_BYTES:
                return data
        except Exception:
            return data

    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        img.thumbnail((_VISION_MAX_SIDE, _VISION_MAX_SIDE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        out = buf.getvalue()
        return out if out else data
    except Exception:
        return data                          # не смогли ужать — пусть решает сервис


def _yandex_ocr(image_bytes: bytes) -> dict:
    _require_yandex()
    import base64, httpx
    image_bytes = prepare_image(image_bytes)
    r = httpx.post(
        "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
        headers={"Authorization": f"Api-Key {YANDEX_API_KEY}",
                 "x-folder-id": YANDEX_FOLDER_ID, "x-data-logging-enabled": "false"},
        json={"mimeType": _sniff_mime(image_bytes), "languageCodes": ["ru", "en"],
              "content": base64.b64encode(image_bytes).decode()},
        timeout=30,
    )
    r.raise_for_status()
    text = r.json().get("result", {}).get("textAnnotation", {}).get("fullText", "")
    # разбор текста в значения — общий постпроцессор (parse_lab_text)
    from .parsing import parse_lab_text
    return parse_lab_text(text)


def _gigachat_stt(audio_bytes: bytes) -> str:
    # Сбер SaluteSpeech; оставлено как альтернатива
    raise NotConfigured("GigaChat STT адаптер не сконфигурирован")


# ── YandexGPT: разбор команды ────────────────────────────────────────────────
# Что модели РАЗРЕШЕНО предлагать. Всё остальное → unknown, решает врач.
ALLOWED_INTENTS = ("appointment", "task", "patient_note", "unknown")

_NLU_SYSTEM = """Ты — разборщик команд в приложении врача-уролога. Твоя ЕДИНСТВЕННАЯ задача —
превратить фразу врача в структуру. Ты НЕ даёшь медицинских советов, НЕ ставишь диагнозы,
НЕ назначаешь лечение и НЕ придумываешь данных, которых нет во фразе.

Верни ТОЛЬКО JSON без пояснений и без markdown, строго такой формы:
{"intent":"...","patient_hint":"","title":"","datetime":"","priority":"","repeat":"","confidence":0.0}

intent — одно из:
  "appointment"   — записать пациента на приём;
  "task"          — напоминание или дело врачу (позвонить, заехать, заказать, проверить);
  "patient_note"  — записать что-то в карту конкретного пациента;
  "unknown"       — всё остальное, включая: триггеры и автослежение, назначение
                    препаратов и доз, постановку диагноза, удаление данных,
                    любые запросы, где ты не уверен.

patient_hint — фамилия пациента как во фразе, иначе "".
title — краткая суть (текст задачи или заметки), своими словами не додумывать.

datetime — АБСОЛЮТНОЕ время в формате YYYY-MM-DDTHH:MM, если во фразе есть срок.
  Считай от «сейчас», которое дано ниже. Понимай разговорную речь:
    «в 3 часа дня» и «в 15 часов» = 15:00;  «в 6 вечера» = 18:00;
    «в 9 утра» = 09:00;  «в 3 ночи» = 03:00;  «в полдень» = 12:00;
    «через 20 минут», «через 2 часа» — прибавь к «сейчас»;
    «в среду» — ближайшая будущая среда; «завтра», «послезавтра» — от «сейчас».
  Если названа только дата без времени — поставь 09:00.
  Если срок НЕ назван — верни "". Не выдумывай время.

priority — "срочно", если врач сказал «срочно/важно/критично», иначе "".
repeat — «каждый день», «каждую неделю», «каждые 3 месяца» — как во фразе, иначе "".
confidence — 0.0..1.0. Сомневаешься — низкая и intent "unknown".

ВАЖНО: триггеры/автослежение менять нельзя никогда — это всегда "unknown"."""


def _yandex_parse_command(text: str, context: dict) -> dict | None:
    _require_yandex()
    import json as _json
    import httpx

    model = os.getenv("YANDEX_GPT_MODEL", "yandexgpt-lite")
    r = httpx.post(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        headers={"Authorization": f"Api-Key {YANDEX_API_KEY}",
                 "x-folder-id": YANDEX_FOLDER_ID,
                 "x-data-logging-enabled": "false"},   # не отдаём промпты в логи Яндекса
        json={
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/{model}",
            "completionOptions": {"stream": False, "temperature": 0.0, "maxTokens": 300},
            "messages": [
                {"role": "system", "text": _NLU_SYSTEM},
                # без «сейчас» модель не сможет посчитать «через 20 минут» и «в среду»
                {"role": "system", "text": "Сейчас: "
                                           + clock.now().strftime("%Y-%m-%dT%H:%M")
                                           + " (" + _WD_RU[clock.now().weekday()] + ")"},
                {"role": "user", "text": text.strip()[:1000]},
            ],
        },
        timeout=20,
    )
    r.raise_for_status()
    body = r.json()
    raw = (body.get("result", {}).get("alternatives") or [{}])[0] \
        .get("message", {}).get("text", "")
    return _coerce_nlu(raw)


def _coerce_nlu(raw: str) -> dict | None:
    """Привести ответ модели к нашей структуре. Мусор → None (откат на правила)."""
    import json as _json
    import re as _re
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):                     # модель иногда оборачивает в markdown
        cleaned = _re.sub(r"^```[a-z]*\s*|\s*```$", "", cleaned, flags=_re.S).strip()
    m = _re.search(r"\{.*\}", cleaned, _re.S)         # вытащим объект из возможной обвязки
    if not m:
        return None
    try:
        data = _json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    intent = str(data.get("intent") or "unknown").strip().lower()
    if intent not in ALLOWED_INTENTS:                 # выдумал своё намерение — не верим
        intent = "unknown"
    try:
        conf = float(data.get("confidence") or 0)
    except Exception:
        conf = 0.0
    conf = max(0.0, min(conf, 1.0))

    dt = str(data.get("datetime") or data.get("datetime_hint") or "").strip()[:40]
    parsed_dt = None
    if dt:
        try:                                  # модель обязана дать YYYY-MM-DDTHH:MM
            parsed_dt = datetime.fromisoformat(dt.replace("Z", "").strip())
        except Exception:
            parsed_dt = None                  # не разобрали — отдадим правилам

    return {
        "intent": intent,
        "patient_hint": str(data.get("patient_hint") or "").strip()[:120],
        "title": str(data.get("title") or "").strip()[:300],
        "datetime": parsed_dt,
        "datetime_hint": dt,
        "priority": str(data.get("priority") or "").strip()[:20],
        "repeat": str(data.get("repeat") or "").strip()[:40],
        "confidence": conf,
    }


# ============================ Диктовка → разделы протокола ============================
# Разделы ровно те, что есть в протоколе приёма (VisitProtocol).
PROTOCOL_SECTIONS = {
    "complaints": "Жалобы",
    "anamnesis_morbi": "Анамнез заболевания",
    "anamnesis_vitae": "Анамнез жизни",
    "objective": "Объективный статус",
    "status_localis": "Локальный статус",
    "diagnosis_text": "Диагноз",
    "recommendations": "Рекомендации и назначения",
}

_PROTOCOL_SYSTEM = """Ты раскладываешь продиктованную врачом речь по разделам протокола приёма.
Ты НЕ ставишь диагноз, НЕ назначаешь лечение и НЕ добавляешь ничего от себя.

Верни ТОЛЬКО JSON без markdown:
{"complaints":"","anamnesis_morbi":"","anamnesis_vitae":"","objective":"",
 "status_localis":"","diagnosis_text":"","recommendations":"","unsorted":""}

Правила:
- Переноси формулировки врача, можно слегка причесать речь (убрать «э-э», повторы).
- Заполняй ТОЛЬКО те разделы, о которых врач действительно сказал.
  Остальные оставь пустой строкой "". Ничего не выдумывай и не додумывай:
  отсутствие данных должно отличаться от нормы. Если осмотр не проводился —
  «objective» и «status_localis» оставь пустыми, не пиши «без особенностей».
- Что не относится ни к одному разделу — положи в "unsorted".
- Если врач назвал диагноз — это «diagnosis_text» (просто его слова, без твоей оценки).
- Назначения и план — в «recommendations».

Куда что относится:
  complaints — что беспокоит сейчас (боль, дизурия, никтурия, струя, гематурия…).
  anamnesis_morbi — когда началось, как развивалось, что обследовали и лечили.
  anamnesis_vitae — сопутствующие болезни, операции, аллергии, постоянные препараты.
  objective — общее состояние, кожа, давление, пульс, температура.
  status_localis — почки, мочевой пузырь, наружные половые органы, ПРИ."""


def parse_protocol(text: str) -> dict | None:
    """Речь врача → разделы протокола. None — модель недоступна/не поняла."""
    if not (text or "").strip():
        return None
    if _provider() != "yandex":
        return None
    try:
        return _coerce_protocol(_yandex_protocol(text))
    except Exception:
        return None                       # вызывающий откатится на правила


def _yandex_protocol(text: str) -> str:
    _require_yandex()
    import httpx
    model = os.getenv("YANDEX_GPT_MODEL", "yandexgpt-lite")
    r = httpx.post(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        headers={"Authorization": f"Api-Key {YANDEX_API_KEY}",
                 "x-folder-id": YANDEX_FOLDER_ID,
                 "x-data-logging-enabled": "false"},
        json={"modelUri": f"gpt://{YANDEX_FOLDER_ID}/{model}",
              "completionOptions": {"stream": False, "temperature": 0.0, "maxTokens": 1500},
              "messages": [{"role": "system", "text": _PROTOCOL_SYSTEM},
                           {"role": "user", "text": text.strip()[:6000]}]},
        timeout=40,
    )
    r.raise_for_status()
    return (r.json().get("result", {}).get("alternatives") or [{}])[0] \
        .get("message", {}).get("text", "")


def _coerce_protocol(raw: str) -> dict | None:
    """Оставляем только известные разделы и только непустые."""
    import json as _json
    import re as _re
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = _re.sub(r"^```[a-z]*\s*|\s*```$", "", cleaned, flags=_re.S).strip()
    m = _re.search(r"\{.*\}", cleaned, _re.S)
    if not m:
        return None
    try:
        data = _json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    out = {}
    for key in list(PROTOCOL_SECTIONS) + ["unsorted"]:
        val = str(data.get(key) or "").strip()
        if val:
            out[key] = val[:4000]
    return out or None


# ============================ Диктовка → несколько назначений ============================
_RX_SYSTEM = """Ты раскладываешь продиктованные врачом назначения в список записей.
Ты НЕ назначаешь лечение сам, НЕ меняешь дозы и НЕ добавляешь ничего от себя —
только структурируешь сказанное врачом.

Верни ТОЛЬКО JSON без markdown:
{"items":[{"drug_name":"","category":"","dose":"","route":"","frequency":"",
           "duration":"","indication":"","instruction":"","control":"","confidence":0.0}]}

category — одно из: drug (препарат), fluid (питьевой режим), diet (питание),
activity (физическая активность), care (уход), selfcontrol (самоконтроль),
lab (анализы), imaging (исследование), procedure (процедура),
restriction (ограничение), followup (повторный осмотр), other.

Правила:
- Одна фраза врача может содержать НЕСКОЛЬКО назначений — верни каждое отдельно.
- drug_name — краткая суть: для препарата его название, иначе «Питьевой режим»,
  «Ограничить нагрузки», «Контрольный осмотр» и т.п.
- Заполняй только то, что врач сказал. Не названо — пустая строка. Дозу,
  кратность и длительность НЕ придумывай.
- confidence — 0.0..1.0 на каждую запись.
Пример: «тадалафил 5 мг один раз в день месяц, питьевой режим до двух литров,
ограничить нагрузки две недели, контроль через месяц» → 4 записи."""


def parse_prescriptions(text: str) -> list | None:
    """Речь врача → список назначений. None — модель недоступна/не поняла."""
    if not (text or "").strip() or _provider() != "yandex":
        return None
    try:
        return _coerce_rx(_yandex_rx(text))
    except Exception:
        return None


def _yandex_rx(text: str) -> str:
    _require_yandex()
    import httpx
    model = os.getenv("YANDEX_GPT_MODEL", "yandexgpt-lite")
    r = httpx.post(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        headers={"Authorization": f"Api-Key {YANDEX_API_KEY}",
                 "x-folder-id": YANDEX_FOLDER_ID, "x-data-logging-enabled": "false"},
        json={"modelUri": f"gpt://{YANDEX_FOLDER_ID}/{model}",
              "completionOptions": {"stream": False, "temperature": 0.0, "maxTokens": 1500},
              "messages": [{"role": "system", "text": _RX_SYSTEM},
                           {"role": "user", "text": text.strip()[:4000]}]},
        timeout=40,
    )
    r.raise_for_status()
    return (r.json().get("result", {}).get("alternatives") or [{}])[0] \
        .get("message", {}).get("text", "")


RX_CATEGORIES = ("drug", "fluid", "diet", "activity", "care", "selfcontrol",
                 "lab", "imaging", "procedure", "restriction", "followup", "other")


def _coerce_rx(raw: str) -> list | None:
    """Чистим ответ модели: только известные категории, без выдуманных полей."""
    import json as _json
    import re as _re
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = _re.sub(r"^```[a-z]*\s*|\s*```$", "", cleaned, flags=_re.S).strip()
    m = _re.search(r"\{.*\}", cleaned, _re.S)
    if not m:
        return None
    try:
        data = _json.loads(m.group(0))
    except Exception:
        return None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None

    out = []
    for it in items[:20]:
        if not isinstance(it, dict):
            continue
        name = str(it.get("drug_name") or "").strip()[:200]
        if not name:
            continue
        cat = str(it.get("category") or "other").strip().lower()
        if cat not in RX_CATEGORIES:
            cat = "other"
        try:
            conf = max(0.0, min(float(it.get("confidence") or 0), 1.0))
        except Exception:
            conf = 0.0
        out.append({
            "drug_name": name, "category": cat,
            "dose": str(it.get("dose") or "").strip()[:80],
            "route": str(it.get("route") or "").strip()[:60],
            "frequency": str(it.get("frequency") or "").strip()[:80],
            "duration": str(it.get("duration") or "").strip()[:80],
            "indication": str(it.get("indication") or "").strip()[:200],
            "instruction": str(it.get("instruction") or "").strip()[:300],
            "control": str(it.get("control") or "").strip()[:200],
            "confidence": conf,
        })
    return out or None
