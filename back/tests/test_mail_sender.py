"""邮件发信器的单元测试。

不真连 SMTP：把 smtplib.SMTP_SSL 换成一个假的，抓下真正构造出来的邮件，
再断言收件人看到的东西（发件人显示名、主题、正文里的码）。
"""

from email.header import decode_header, make_header

import pytest

from app.core.config import settings
from app.services import mail_sender


class FakeSMTP:
    """够用的 smtplib.SMTP_SSL 替身。"""

    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.user = user

    def send_message(self, message):
        FakeSMTP.sent.append(message)


@pytest.fixture(name="smtp_settings")
def smtp_settings_fixture(monkeypatch):
    """把配置切成 smtp 模式，并拦下真正的发信动作。"""
    FakeSMTP.sent = []
    monkeypatch.setattr(settings, "mail_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.qq.com")
    monkeypatch.setattr(settings, "smtp_port", 465)
    monkeypatch.setattr(settings, "smtp_ssl", True)
    monkeypatch.setattr(settings, "smtp_user", "1218817158@qq.com")
    monkeypatch.setattr(settings, "smtp_password", "fake-auth-code")
    monkeypatch.setattr(settings, "smtp_from", "1218817158@qq.com")
    monkeypatch.setattr(settings, "smtp_from_name", "食时")
    monkeypatch.setattr(mail_sender.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def _decoded(value: str) -> str:
    """把 =?utf-8?b?...?= 这种 MIME 编码还原成可读文本。"""
    return str(make_header(decode_header(value)))


def test_from_header_carries_the_display_name(smtp_settings):
    """收件人必须看到「食时」，而不是一串 QQ 号。"""
    channel = mail_sender.send_code(
        target="someone@example.com", code="123456", purpose="login"
    )
    assert channel == "smtp"

    message = smtp_settings.sent[0]
    sender = _decoded(message["From"])

    assert "食时" in sender
    assert "1218817158@qq.com" in sender


def test_subject_and_body_carry_the_code(smtp_settings):
    mail_sender.send_code(
        target="someone@example.com", code="654321", purpose="register"
    )
    message = smtp_settings.sent[0]

    assert "654321" in _decoded(message["Subject"])
    assert "注册" in _decoded(message["Subject"])
    assert "654321" in message.get_content()
    assert message["To"] == "someone@example.com"


def test_blank_from_name_falls_back_to_shishi(smtp_settings, monkeypatch):
    monkeypatch.setattr(settings, "smtp_from_name", "")
    mail_sender.send_code(target="a@b.com", code="111111", purpose="login")
    assert "食时" in _decoded(smtp_settings.sent[0]["From"])


def test_missing_credentials_raise_mail_error(smtp_settings, monkeypatch):
    monkeypatch.setattr(settings, "smtp_password", "")
    with pytest.raises(mail_sender.MailError):
        mail_sender.send_code(target="a@b.com", code="111111", purpose="login")


def test_console_backend_does_not_touch_smtp(monkeypatch):
    """默认通道不该去连 SMTP —— 没配邮箱也必须能跑。"""
    monkeypatch.setattr(settings, "mail_backend", "console")
    channel = mail_sender.send_code(
        target="a@b.com", code="222222", purpose="login"
    )
    assert channel == "console"
