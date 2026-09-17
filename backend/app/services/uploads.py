"""Ограничение размера загружаемых файлов (защита от отказа в обслуживании по памяти)."""
import os
from fastapi import HTTPException

def max_upload_bytes() -> int:
    return int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024   # по умолчанию 15 МБ

async def read_limited(file) -> bytes:
    """Читает файл, но не больше лимита. Превышение → 413 (а не падение по памяти)."""
    if file is None:
        return b""
    limit = max_upload_bytes()
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Файл слишком большой (максимум {limit // (1024*1024)} МБ).")
    return data
