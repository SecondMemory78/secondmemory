"""Шифрование чувствительных полей на уровне приложения (защита от утечки дампа БД).

Прозрачно: в Python — открытый текст, в БД — шифротекст (AES через Fernet).
Ключ берётся из окружения FIELD_KEY и хранится ВНЕ базы (в проде — в секрет-хранилище/KMS).
Потеря ключа = потеря данных, поэтому ключ обязательно бэкапить отдельно от БД.

Совместимость: если поле уже содержит открытый текст (старые записи) и не
расшифровывается — возвращаем как есть, чтобы миграция была плавной.
"""
import os
import base64
import hashlib
from sqlalchemy.types import TypeDecorator, Text
from cryptography.fernet import Fernet, InvalidToken


def _key() -> bytes:
    k = os.getenv("FIELD_KEY")
    if k:
        return k.encode()
    # DEV-ключ (детерминированный). В ПРОДЕ ОБЯЗАТЕЛЬНО задать FIELD_KEY!
    seed = os.getenv("SECRET_SEED", "second-memory-dev-key")
    return base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest())


_f = Fernet(_key())


def enc(v):
    if v is None or v == "":
        return v
    return _f.encrypt(str(v).encode()).decode()


def dec(v):
    if v is None or v == "":
        return v
    try:
        return _f.decrypt(str(v).encode()).decode()
    except (InvalidToken, ValueError):
        return v      # старый открытый текст или чужой формат — отдаём как есть


def key_fingerprint() -> str:
    """Необратимый отпечаток текущего ключа (не секрет) — для самопроверки при старте.
    Если данные были зашифрованы другим ключом, отпечаток не совпадёт."""
    return hashlib.sha256(_key()).hexdigest()[:16]


def _index_key() -> bytes:
    """Отдельный ключ для слепого индекса (HMAC). НЕ равен FIELD_KEY: утечка одного
    ключа не должна раскрывать другой механизм. В проде задать BLIND_INDEX_KEY."""
    k = os.getenv("BLIND_INDEX_KEY")
    if k:
        return k.encode()
    seed = os.getenv("SECRET_SEED", "second-memory-dev-key") + ":blind-index"
    return hashlib.sha256(seed.encode()).digest()


def blind_index(v: str) -> str:
    """Детерминированный HMAC значения — для ТОЧНОГО сравнения без расшифровки.
    Нормализуем: трим, нижний регистр, ё→е. Пусто → пустая строка."""
    import hmac
    n = (v or "").strip().lower().replace("ё", "е")
    if not n:
        return ""
    return hmac.new(_index_key(), n.encode(), hashlib.sha256).hexdigest()


class EncryptedStr(TypeDecorator):
    """Строковый столбец, шифруемый на запись и расшифровываемый на чтение."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return enc(value)

    def process_result_value(self, value, dialect):
        return dec(value)
