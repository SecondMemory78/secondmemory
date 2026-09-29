# Для тестов общий API rate-limit фактически выключаем (иначе быстрый прогон всего
import os as _os
_os.environ.setdefault("SCHEDULER_ENABLED", "0")
# набора упирается в общий счётчик). В проде значение берётся из .env (API_RATE_MAX=300).
# Точечный тест лимита сам понижает порог и чистит счётчик.
import os
os.environ.setdefault("API_RATE_MAX", "1000000")
# Антифлуд отправки кода (1 письмо/60с) выключаем в тестах: модульные хелперы
# логинятся подряд одним email на этапе импорта. В проде дефолт 60с/15 в сутки.
os.environ.setdefault("AUTH_CODE_COOLDOWN", "0")
os.environ.setdefault("AUTH_CODE_DAILY_MAX", "100000")

# ИИ в тестах — всегда заглушки: тесты не должны зависеть от локального .env
# разработчика и уж точно не должны ходить в платные API Яндекса.
os.environ["AI_PROVIDER"] = "stub"
os.environ.pop("YANDEX_API_KEY", None)
os.environ.pop("YANDEX_FOLDER_ID", None)
