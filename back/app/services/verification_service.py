"""验证码的生成、限流与校验。

这一层不关心「怎么把码送出去」——那是 mail_sender 的事。这里只负责：

1. **生成**：`secrets` 出来的 6 位随机码，不是固定值；
2. **限流**：同一目标 60 秒内不许重发，每小时最多 5 条；
3. **过期**：默认 5 分钟；
4. **防爆破**：一条码校验失败到上限就作废，必须重新获取；
5. **防重放**：校验成功后立刻标记 consumed_at，同一条码不能用第二次。

时间一律用 naive UTC（见 verification_code.naive_utcnow 的注释）——
SQLite 存不了时区，aware 写进去读出来是 naive，直接比较会 TypeError。
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import HTTPException, status
from sqlmodel import Session, col, func, select

from app.core.config import settings
from app.models.verification_code import VerificationCode, naive_utcnow
from app.services import mail_sender

PURPOSES = ("register", "login")


def _hash(target: str, purpose: str, code: str) -> str:
    """掺 SECRET_KEY 的哈希，避免拿到库就能对着 6 位码枚举。"""
    payload = f"{target}|{purpose}|{code}".encode()
    return hmac.new(
        settings.secret_key.encode(), payload, hashlib.sha256
    ).hexdigest()


def normalize_target(target: str) -> str:
    return target.strip().lower()


def _latest(
    session: Session, target: str, purpose: str, *, unused_only: bool = False
) -> VerificationCode | None:
    statement = (
        select(VerificationCode)
        .where(VerificationCode.target == target)
        .where(VerificationCode.purpose == purpose)
        .order_by(col(VerificationCode.created_at).desc())
    )
    if unused_only:
        statement = statement.where(col(VerificationCode.consumed_at).is_(None))
    return session.exec(statement).first()


def issue_code(session: Session, *, target: str, purpose: str) -> str:
    """生成一条新验证码、落库并发送，返回实际使用的通道名。

    限流不通过或发送失败都会抛 HTTPException。
    """
    target = normalize_target(target)
    now = naive_utcnow()

    last = _latest(session, target, purpose)
    if last is not None:
        waited = (now - last.created_at).total_seconds()
        if waited < settings.code_resend_interval:
            wait = int(settings.code_resend_interval - waited) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"发送太频繁了，请 {wait} 秒后再试",
            )

    sent_recently = session.exec(
        select(func.count())
        .select_from(VerificationCode)
        .where(VerificationCode.target == target)
        .where(VerificationCode.created_at >= now - timedelta(hours=1))
    ).one()
    if int(sent_recently) >= settings.code_hourly_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="该账号一小时内获取验证码的次数过多，请稍后再试",
        )

    code = f"{secrets.randbelow(1_000_000):06d}"

    # 先把码发出去再落库：发信失败就不该留下一条「已发出」的记录，
    # 否则用户会卡在 60 秒重发间隔里，明明没收到码。
    try:
        channel = mail_sender.send_code(target=target, code=code, purpose=purpose)
    except mail_sender.MailError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    session.add(
        VerificationCode(
            target=target,
            purpose=purpose,
            channel=channel,
            code_hash=_hash(target, purpose, code),
            expires_at=now + timedelta(seconds=settings.code_ttl_seconds),
        )
    )
    session.commit()
    return channel


def consume_code(session: Session, *, target: str, purpose: str, code: str) -> None:
    """校验并消费验证码；任何不合格都抛 401。"""
    target = normalize_target(target)
    now = naive_utcnow()

    # 演示保险：只有显式打开 allow_demo_code 才认固定码。
    if settings.allow_demo_code and code == settings.demo_code:
        return

    row = _latest(session, target, purpose, unused_only=True)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先获取验证码",
        )

    if row.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码已过期，请重新获取",
        )

    if row.attempts >= settings.code_max_attempts:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码错误次数过多，请重新获取",
        )

    if not hmac.compare_digest(row.code_hash, _hash(target, purpose, code)):
        row.attempts += 1
        session.add(row)
        session.commit()
        left = settings.code_max_attempts - row.attempts
        if left <= 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="验证码错误次数过多，请重新获取",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"验证码不正确（还可以试 {left} 次）",
        )

    row.consumed_at = now
    session.add(row)
    session.commit()
