"""Отправка писем (коды входа, сброс пароля).

Честный фолбэк: если SMTP не настроен — возвращаем False и НЕ притворяемся,
что письмо ушло. По 152-ФЗ используйте почтовый сервис на территории РФ.
"""
import os
import ssl
import smtplib
from email.message import EmailMessage


def email_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def send_email(to: str, subject: str, body: str) -> bool:
    if not email_configured():
        return False
    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASSWORD")
    try:
        with smtplib.SMTP(host, port, timeout=10) as srv:
            srv.starttls(context=ssl.create_default_context())
            if user:
                srv.login(user, pw)
            srv.send_message(msg)
        return True
    except Exception:
        return False
