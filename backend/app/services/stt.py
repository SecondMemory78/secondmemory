"""Речь-в-текст. Делегирует в слой ИИ (services/ai.py)."""
from . import ai


def transcribe(audio_bytes: bytes = b"", audio_format: str = "") -> str:
    """audio_format: "lpcm" — сырые 16-битные сэмплы 16 кГц моно (то, что
    присылает фронт). Пусто — отдаём как есть, пусть решает провайдер."""
    return ai.transcribe(audio_bytes, audio_format)
