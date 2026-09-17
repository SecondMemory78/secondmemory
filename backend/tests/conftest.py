# Для тестов общий API rate-limit фактически выключаем (иначе быстрый прогон всего
import os as _os
_os.environ.setdefault("SCHEDULER_ENABLED", "0")
# набора упирается в общий счётчик). В проде значение берётся из .env (API_RATE_MAX=300).
# Точечный тест лимита сам понижает порог и чистит счётчик.
import os
os.environ.setdefault("API_RATE_MAX", "1000000")
