"""Ядро TOTP: сверка с эталонными векторами RFC 6238 (совместимость с Google
Authenticator/Aegis), окно рассинхрона, генерация секрета и otpauth-URI."""
from app import totp


def test_rfc6238_vectors_sha1():
    # RFC 6238 Appendix B: секрет "12345678901234567890" (ASCII) в base32,
    # 8-значные коды на известные метки времени. Проверяем срез до 6 цифр нашего расчёта.
    import base64
    secret_b32 = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    # эталон RFC (8 цифр) → берём последние 6 как наш DIGITS=6
    cases = {59: "94287082", 1111111109: "07081804", 1234567890: "89005924"}
    for t, expected8 in cases.items():
        got6 = totp.totp_now(secret_b32, at=t)
        assert got6 == expected8[-6:], f"t={t}: {got6} != {expected8[-6:]}"


def test_verify_accepts_current_code():
    sec = totp.generate_secret()
    code = totp.totp_now(sec)
    assert totp.verify(sec, code) is True


def test_verify_window_prev_next():
    sec = totp.generate_secret()
    now = 1000000000
    # код предыдущего окна должен приниматься при window=1
    prev = totp.totp_now(sec, at=now - totp.PERIOD)
    assert totp.verify(sec, prev, at=now, window=1) is True
    # код на 2 окна назад — не принимается при window=1
    old = totp.totp_now(sec, at=now - 3 * totp.PERIOD)
    assert totp.verify(sec, old, at=now, window=1) is False


def test_verify_rejects_garbage():
    sec = totp.generate_secret()
    assert totp.verify(sec, "000000") in (True, False)   # просто не падает
    assert totp.verify(sec, "abc") is False
    assert totp.verify(sec, "") is False


def test_secret_is_base32_and_uri():
    sec = totp.generate_secret()
    assert sec == sec.upper().rstrip("=") and sec.isalnum()
    uri = totp.provisioning_uri(sec, "doc@x.ru")
    assert uri.startswith("otpauth://totp/") and "secret=" + sec in uri
