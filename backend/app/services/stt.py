"""Речь-в-текст. Делегирует в слой ИИ (services/ai.py)."""
from . import ai


def transcribe(audio_bytes: bytes = b"") -> str:
    return ai.transcribe(audio_bytes)
