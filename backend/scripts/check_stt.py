"""Проверка распознавания речи на сервере — без телефона и без браузера.

    cd ~/secondmemory/backend
    source ../.venv/bin/activate      # или .venv/bin/activate — где у вас окружение
    python scripts/check_stt.py

Зачем. Когда голос не работает, непонятно, где обрыв: браузер записал не то,
сеть не пустила, ключ не тот или у сервисного аккаунта нет прав на распознавание
речи. Этот скрипт убирает из цепочки браузер целиком: он сам делает заведомо
правильное аудио (тишина в нужном формате) и отправляет его тем же кодом, что и
приложение. Что ответит Яндекс — то и увидим.

Важно: пустой ответ распознавания на тишине — это НОРМА и признак успеха.
Значит формат принят, ключ рабочий, права есть.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app  # подхватывает .env  # noqa: E402
from app.services import ai  # noqa: E402


def silence_lpcm(seconds: float = 1.0, rate: int = 16000) -> bytes:
    """Сырые 16-битные сэмплы, 16 кГц, моно — ровно то, что шлёт приложение."""
    return struct.pack("<%dh" % int(rate * seconds), *([0] * int(rate * seconds)))


def main() -> int:
    print("Провайдер:", ai.PROVIDER)
    print("Ключ задан:", "да" if ai.YANDEX_API_KEY else "НЕТ")
    print("Каталог задан:", ai.YANDEX_FOLDER_ID or "НЕТ")
    if ai.PROVIDER != "yandex" or not ai.YANDEX_API_KEY:
        print("\nБоевой режим не включён — проверять нечего.")
        return 1

    audio = silence_lpcm()
    print(f"\nОтправляем {len(audio)} байт (1 секунда тишины, lpcm 16 кГц моно)…")

    import httpx
    r = httpx.post(
        "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
        params={"folderId": ai.YANDEX_FOLDER_ID, "lang": "ru-RU",
                "format": "lpcm", "sampleRateHertz": "16000"},
        headers={"Authorization": f"Api-Key {ai.YANDEX_API_KEY}"},
        content=audio, timeout=30,
    )

    print("Ответ:", r.status_code)
    print("Тело: ", r.text[:400])

    if r.status_code == 200:
        print("\nРАСПОЗНАВАНИЕ РЕЧИ РАБОТАЕТ. Формат, ключ и права в порядке.")
        print("Значит обрыв в браузере — смотреть, что уходит с устройства.")
        return 0

    print("\nРАСПОЗНАВАНИЕ РЕЧИ НЕ РАБОТАЕТ на стороне сервера. Подсказка по коду:")
    if r.status_code in (401, 403):
        print("  401/403 — у сервисного аккаунта нет роли ai.speechkit-stt.user")
        print("  (роль на языковые модели даётся отдельно — поэтому текстовые")
        print("   команды ассистента могут работать, а голос нет).")
    elif r.status_code == 400:
        print("  400 — Яндекс не принял запрос: смотрите текст выше.")
        print("  «audio should be not empty» означает, что аудио до него не дошло.")
    elif r.status_code == 404:
        print("  404 — неверный каталог (folderId).")
    else:
        print("  Смотрите текст ответа выше.")

    print("\nДля сравнения — проверяем языковую модель тем же ключом:")
    try:
        out = ai.parse_protocol("жалобы никтурия три раза")
        print("  Языковая модель ответила:", "да" if out else "пусто (но без ошибки)")
    except Exception as e:  # noqa: BLE001
        print("  Языковая модель тоже не отвечает:", str(e)[:200])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
