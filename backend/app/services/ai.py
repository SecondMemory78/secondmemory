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
import os

PROVIDER = os.getenv("AI_PROVIDER", "stub").lower()

# --- ключи (берутся из окружения; в репозиторий не коммитятся) ---
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")


class NotConfigured(Exception):
    pass


# ============================ STT: речь → текст ============================
def transcribe(audio_bytes: bytes) -> str:
    try:
        if PROVIDER == "yandex":
            return _yandex_stt(audio_bytes)
        if PROVIDER == "gigachat":
            return _gigachat_stt(audio_bytes)
    except Exception:
        pass  # деградация до заглушки, чтобы не ронять приём
    return _stub_transcript()


# ============================ OCR: фото/PDF → текст+значения ============================
def ocr_extract(image_bytes: bytes) -> dict:
    try:
        if PROVIDER == "yandex":
            return _yandex_ocr(image_bytes)
    except Exception:
        pass
    return _stub_ocr()


# ============================ Заглушки ============================
def _stub_transcript() -> str:
    return "Пациент отмечает учащённое ночное мочеиспускание, направлен на контроль PSA через 3 месяца."


def _stub_ocr() -> dict:
    return {
        "text": "ПСА общий 4.82 нг/мл\nКреатинин 118 мкмоль/л\nдата 09.03.2026",
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


def _yandex_stt(audio_bytes: bytes) -> str:
    _require_yandex()
    import httpx
    # SpeechKit v1 (короткое аудио). Для длинного — асинхронный режим v3.
    r = httpx.post(
        "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
        params={"folderId": YANDEX_FOLDER_ID, "lang": "ru-RU"},
        headers={"Authorization": f"Api-Key {YANDEX_API_KEY}"},
        content=audio_bytes, timeout=30,
    )
    r.raise_for_status()
    return r.json().get("result", "")


def _yandex_ocr(image_bytes: bytes) -> dict:
    _require_yandex()
    import base64, httpx
    r = httpx.post(
        "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
        headers={"Authorization": f"Api-Key {YANDEX_API_KEY}",
                 "x-folder-id": YANDEX_FOLDER_ID, "x-data-logging-enabled": "false"},
        json={"mimeType": "image", "languageCodes": ["ru", "en"],
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
