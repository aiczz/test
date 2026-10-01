"""验证码机制测试。

重点不是「接口能不能通」，而是只有真机制才有的那些行为：
随机码、过期、重发间隔、每小时上限、失败次数上限、防重放。
"""

from datetime import timedelta

import pytest
from sqlmodel import select

from app.core.config import settings
from app.models.verification_code import VerificationCode
from app.services import mail_sender

EMAIL = "cook@example.com"
PASSWORD = "12345678"


@pytest.fixture(name="outbox")
def outbox_fixture(monkeypatch):
    """把发信拦下来：测试既不真发邮件，又能拿到那条随机码。"""
    sent: list[dict] = []

    def fake_send_code(*, target: str, code: str, purpose: str) -> str:
        sent.append({"target": target, "code": code, "purpose": purpose})
        return "console"

    monkeypatch.setattr(mail_sender, "send_code", fake_send_code)
    return sent


def _send(client, purpose="login"):
    return client.post(
        "/api/auth/email/send-code",
        json={"email": EMAIL, "purpose": purpose},
    )


def _shift_codes(session, seconds: int) -> None:
    """把库里已有的验证码记录整体往前挪，用来绕过 60 秒间隔或制造过期。"""
    delta = timedelta(seconds=seconds)
    for row in session.exec(select(VerificationCode)).all():
        row.created_at = row.created_at - delta
        row.expires_at = row.expires_at - delta
        session.add(row)
    session.commit()


# ------------------------------------------------------------------ 基本流程


def test_send_code_never_leaks_the_code(client, outbox):
    resp = _send(client)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["channel"] == "console"
    assert body["expires_in"] == settings.code_ttl_seconds

    # 码只能出现在"邮件"里，绝不能出现在 HTTP 响应里
    assert len(outbox) == 1
    code = outbox[0]["code"]
    assert len(code) == 6 and code.isdigit()
    assert code not in resp.text


def test_code_is_random_not_fixed(client, session, outbox):
    """两条码必须不一样，否则又退化成固定码了。"""
    assert _send(client).status_code == 200
    _shift_codes(session, settings.code_resend_interval + 1)
    assert _send(client).status_code == 200

    assert outbox[0]["code"] != outbox[1]["code"]


def test_register_then_login_with_email_code(client, session, outbox):
    assert _send(client, purpose="register").status_code == 200
    code = outbox[-1]["code"]

    resp = client.post(
        "/api/auth/email/register",
        json={"email": EMAIL, "code": code, "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == EMAIL
    assert "password_hash" not in resp.json()

    # 注册那条码已经消费掉了，登录得重新发
    _shift_codes(session, settings.code_resend_interval + 1)
    assert _send(client).status_code == 200

    resp = client.post(
        "/api/auth/email/login",
        json={"email": EMAIL, "code": outbox[-1]["code"]},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == EMAIL


# ------------------------------------------------------------------ 真实机制


def test_wrong_code_is_rejected_and_counts_down(client, outbox):
    _send(client)
    real = outbox[-1]["code"]
    wrong = "000000" if real != "000000" else "111111"

    resp = client.post("/api/auth/email/login", json={"email": EMAIL, "code": wrong})
    assert resp.status_code == 401
    assert "还可以试" in resp.json()["detail"]


def test_code_cannot_be_used_twice(client, outbox):
    """防重放：同一条码用掉之后再拿它来一次必须失败。"""
    _send(client, purpose="register")
    code = outbox[-1]["code"]

    first = client.post(
        "/api/auth/email/register",
        json={"email": EMAIL, "code": code, "password": PASSWORD},
    )
    assert first.status_code == 201, first.text

    again = client.post(
        "/api/auth/email/register",
        json={"email": EMAIL, "code": code, "password": PASSWORD},
    )
    assert again.status_code == 401
    assert "请先获取验证码" in again.json()["detail"]


def test_resend_interval_is_enforced(client, outbox):
    assert _send(client).status_code == 200

    resp = _send(client)
    assert resp.status_code == 429
    assert "太频繁" in resp.json()["detail"]
    # 被挡下来的那次不该真的发出去
    assert len(outbox) == 1


def test_expired_code_is_rejected(client, session, outbox):
    _send(client)
    code = outbox[-1]["code"]

    _shift_codes(session, settings.code_ttl_seconds + 1)

    resp = client.post("/api/auth/email/login", json={"email": EMAIL, "code": code})
    assert resp.status_code == 401
    assert "已过期" in resp.json()["detail"]


def test_attempts_limit_invalidates_the_code(client, outbox):
    _send(client)
    real = outbox[-1]["code"]
    wrong = "000000" if real != "000000" else "111111"

    for _ in range(settings.code_max_attempts):
        client.post("/api/auth/email/login", json={"email": EMAIL, "code": wrong})

    # 次数用尽后连正确的码也不认了，必须重新获取
    resp = client.post("/api/auth/email/login", json={"email": EMAIL, "code": real})
    assert resp.status_code == 401
    assert "次数过多" in resp.json()["detail"]


def test_hourly_limit(client, outbox, monkeypatch):
    monkeypatch.setattr(settings, "code_hourly_limit", 2)
    monkeypatch.setattr(settings, "code_resend_interval", 0)

    assert _send(client).status_code == 200
    assert _send(client).status_code == 200

    resp = _send(client)
    assert resp.status_code == 429
    assert "次数过多" in resp.json()["detail"]


def test_demo_code_is_off_by_default(client, outbox):
    """默认必须不认固定码，否则等于没做验证码。"""
    assert settings.allow_demo_code is False
    _send(client)

    resp = client.post(
        "/api/auth/email/login",
        json={"email": EMAIL, "code": settings.demo_code},
    )
    assert resp.status_code == 401
