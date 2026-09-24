"""Криптопримитивы без внешних зависимостей (stdlib).

Пароль — PBKDF2-HMAC-SHA256 с солью. В проде можно заменить на argon2/bcrypt,
интерфейс не изменится.
"""
import hashlib
import hmac
import os
import secrets

MIN_PASSWORD_LEN = 8


def validate_password(password: str) -> None:
    """Единая парольная политика (регистрация и сброс). Бросает ValueError при провале.

    Минимум для медприложения под 152-ФЗ: длина ≥ 8 и не из списка самых
    распространённых. Хеш — PBKDF2; интерфейс проверки один на все точки входа.
    """
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов")
    common = {"password", "12345678", "qwerty123", "11111111", "parol123", "12345678a"}
    if password.lower() in common:
        raise ValueError("Пароль слишком простой — выберите другой")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"pbkdf2$120000${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, hexdk = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), hexdk)
    except Exception:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def sha256_hex(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()
