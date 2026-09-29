"""Адрес клиента — с учётом обратного прокси.

За nginx приложение видит адрес самого nginx (127.0.0.1), и все посетители
сливаются в одного: лимиты попыток входа перестают работать, а журнал доступа
пишет один и тот же адрес для всех.

Заголовку X-Forwarded-For доверяем ТОЛЬКО когда явно сказано TRUST_PROXY=1.
Иначе любой желающий подставил бы себе чужой адрес и обошёл анти-брутфорс.

Берём ПОСЛЕДНЮЮ запись списка, а не первую: nginx дописывает настоящий адрес
подключившегося в конец, а всё, что было в заголовке раньше, прислал сам
клиент и доверять этому нельзя. При нескольких прокси-слоях число хопов
задаётся TRUST_PROXY_HOPS.
"""
import os


def trust_proxy() -> bool:
    return os.getenv("TRUST_PROXY", "0").strip().lower() in ("1", "true", "yes")


def _hops() -> int:
    try:
        return max(1, int(os.getenv("TRUST_PROXY_HOPS", "1")))
    except ValueError:
        return 1


def from_headers(headers, peer: str | None) -> str:
    """headers — словарь или список пар (bytes/str), peer — адрес сокета."""
    peer = peer or "?"
    if not trust_proxy():
        return peer

    def get(name: str) -> str:
        if hasattr(headers, "get"):
            v = headers.get(name) or headers.get(name.encode())
            return v.decode() if isinstance(v, bytes) else (v or "")
        for k, v in headers or []:
            k = k.decode() if isinstance(k, bytes) else k
            if k.lower() == name:
                return v.decode() if isinstance(v, bytes) else v
        return ""

    xff = get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-_hops()] if len(parts) >= _hops() else parts[0]
    real = get("x-real-ip")
    return real.strip() if real else peer


def from_request(request) -> str:
    """Для обычных роутеров (объект Request)."""
    peer = request.client.host if request.client else None
    return from_headers(request.headers, peer)


def from_scope(scope) -> str:
    """Для ASGI-middleware, где Request ещё не собран."""
    client = scope.get("client")
    return from_headers(scope.get("headers") or [], client[0] if client else None)
