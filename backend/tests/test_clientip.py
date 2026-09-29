"""Адрес клиента за обратным прокси (nginx).

Главное, что проверяем: без TRUST_PROXY=1 заголовку X-Forwarded-For не верим —
иначе кто угодно подставит чужой адрес и обойдёт лимит попыток входа.
"""
import os
import pytest
from app.services import clientip


@pytest.fixture(autouse=True)
def _clean_env():
    saved = {k: os.environ.get(k) for k in ("TRUST_PROXY", "TRUST_PROXY_HOPS")}
    for k in saved:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v


def _headers(**kw):
    return {k.replace("_", "-"): v for k, v in kw.items()}


def test_без_доверия_проксy_заголовок_игнорируется():
    ip = clientip.from_headers(_headers(x_forwarded_for="1.2.3.4"), "127.0.0.1")
    assert ip == "127.0.0.1"


def test_подделка_заголовка_не_проходит_даже_при_доверии():
    """Клиент прислал свой X-Forwarded-For, nginx дописал настоящий адрес в конец.
    Берём последний — подставленный клиентом адрес игнорируется."""
    os.environ["TRUST_PROXY"] = "1"
    ip = clientip.from_headers(_headers(x_forwarded_for="6.6.6.6, 203.0.113.9"), "127.0.0.1")
    assert ip == "203.0.113.9"


def test_доверенный_прокси_отдаёт_адрес_клиента():
    os.environ["TRUST_PROXY"] = "1"
    ip = clientip.from_headers(_headers(x_forwarded_for="203.0.113.9"), "127.0.0.1")
    assert ip == "203.0.113.9"


def test_x_real_ip_как_запасной_вариант():
    os.environ["TRUST_PROXY"] = "1"
    ip = clientip.from_headers(_headers(x_real_ip="198.51.100.7"), "127.0.0.1")
    assert ip == "198.51.100.7"


def test_без_заголовков_остаётся_адрес_сокета():
    os.environ["TRUST_PROXY"] = "1"
    assert clientip.from_headers({}, "10.0.0.5") == "10.0.0.5"
    assert clientip.from_headers({}, None) == "?"


def test_два_слоя_прокси():
    os.environ["TRUST_PROXY"] = "1"
    os.environ["TRUST_PROXY_HOPS"] = "2"
    ip = clientip.from_headers(_headers(x_forwarded_for="6.6.6.6, 203.0.113.9, 10.0.0.1"), "127.0.0.1")
    assert ip == "203.0.113.9"


def test_заголовки_в_виде_списка_пар_байтов():
    """ASGI-scope отдаёт заголовки именно так."""
    os.environ["TRUST_PROXY"] = "1"
    scope = {"client": ("127.0.0.1", 50000),
             "headers": [(b"host", b"example.ru"), (b"x-forwarded-for", b"203.0.113.9")]}
    assert clientip.from_scope(scope) == "203.0.113.9"
