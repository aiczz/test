"""密码哈希与 JWT（说明书 §12）。

- 密码必须哈希后保存，禁止明文存储。
- 登录返回 `{access_token, token_type}`，后续请求带 `Authorization: Bearer <token>`。
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt 是行业标准，passlib 负责 salt 与算法版本管理。
# ⚠️ bcrypt 4.1+ 删掉了 passlib 依赖的 `__about__`，会刷一堆报错日志，
#    所以 requirements.txt 里把 bcrypt 钉在 4.0.1。
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt 只认前 72 字节，超长会直接抛异常，所以先按【字节】截断。
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) <= _BCRYPT_MAX_BYTES:
        return password
    # 按字节截断，且不能把一个多字节汉字切成两半
    return raw[:_BCRYPT_MAX_BYTES].decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    """哈希密码。数据库里只存这个，永远不存明文。"""
    return _pwd_context.hash(_prepare(password))


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(_prepare(plain), hashed)
    except ValueError:
        # 哈希串格式非法（比如手工改坏了库）时按验证失败处理，不要 500
        return False


def create_access_token(subject: str | int, expires_minutes: int | None = None) -> str:
    """签发 access token。`subject` 用用户 id。"""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> str | None:
    """校验 token 并返回 subject（用户 id 字符串）。无效或过期返回 None。"""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except JWTError:
        return None
    sub = payload.get("sub")
    return str(sub) if sub is not None else None
