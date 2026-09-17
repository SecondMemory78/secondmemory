"""Криптопримитивы без внешних зависимостей (stdlib).

Пароль — PBKDF2-HMAC-SHA256 с солью. В проде можно заменить на argon2/bcrypt,
интерфейс не изменится.
"""
import hashlib
import hmac
import os
import secrets


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
