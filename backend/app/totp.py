"""TOTP (RFC 6238) на stdlib — без внешних зависимостей (в духе crypto.py).

Одноразовые коды из приложения-аутентификатора (Google Authenticator, Aegis и т.п.)
как альтернатива коду по почте. Секрет — base32; код — 6 цифр, шаг 30 c, HMAC-SHA1.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30            # секунд на код
ISSUER = "Вторая память"


def generate_secret(length: int = 20) -> str:
    """Случайный секрет в base32 (без '=' в конце) — то, что вводится/сканируется в приложении."""
    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = DIGITS) -> str:
    """HOTP (RFC 4226) — код для конкретного счётчика."""
    pad = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    msg = struct.pack(">Q", counter)
    dig = hmac.new(key, msg, hashlib.sha1).digest()
    offset = dig[-1] & 0x0F
    code = (struct.unpack(">I", dig[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp_now(secret_b32: str, at: float | None = None, period: int = PERIOD) -> str:
    """Текущий TOTP-код."""
    counter = int((at if at is not None else time.time()) // period)
    return _hotp(secret_b32, counter)


def verify(secret_b32: str, code: str, at: float | None = None, window: int = 1) -> bool:
    """Проверка кода с окном ±window шагов (компенсация рассинхрона часов).
    window=1 → принимаются коды текущего, прошлого и следующего 30-секундного окна."""
    if not code or not code.strip().isdigit():
        return False
    code = code.strip()
    now = at if at is not None else time.time()
    counter = int(now // PERIOD)
    for w in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, counter + w), code):
            return True
    return False


def provisioning_uri(secret_b32: str, account: str, issuer: str = ISSUER) -> str:
    """otpauth://-ссылка для QR-кода в приложении-аутентификаторе."""
    label = quote(f"{issuer}:{account}")
    params = f"secret={secret_b32}&issuer={quote(issuer)}&digits={DIGITS}&period={PERIOD}&algorithm=SHA1"
    return f"otpauth://totp/{label}?{params}"


def generate_backup_codes(n: int = 10) -> list[str]:
    """Читаемые одноразовые резервные коды вида 'a1b2-c3d4' (без похожих символов)."""
    alphabet = "23456789abcdefghjkmnpqrstuvwxyz"    # без 0/o/1/l/i
    def one():
        raw = "".join(secrets.choice(alphabet) for _ in range(8))
        return raw[:4] + "-" + raw[4:]
    return [one() for _ in range(n)]
