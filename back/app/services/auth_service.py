"""认证业务逻辑（说明书 §12）。"""

from fastapi import HTTPException, Request, status
from sqlmodel import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.login_log import LoginLog
from app.models.user import User, UserPreference
from app.repositories import user_repository
from app.schemas.auth import LoginRequest, RegisterRequest
from app.utils.time import utcnow


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    # 走反向代理时真实 IP 在 X-Forwarded-For 的第一段
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def _record_login(
    session: Session,
    *,
    user: User | None,
    username: str,
    success: bool,
    request: Request | None,
    detail: str | None = None,
) -> None:
    """记一条登录日志。

    管理员靠它「监听新账号登录」。失败也记 —— 刷密码的行为在日志里
    一眼就能看出来（同一个用户名一堆 success=False）。
    """
    session.add(
        LoginLog(
            user_id=user.id if user else None,
            username=username,
            success=success,
            ip=_client_ip(request),
            user_agent=(request.headers.get("user-agent") if request else None),
            detail=detail,
        )
    )
    session.commit()


def register(session: Session, payload: RegisterRequest) -> User:
    if user_repository.get_by_username(session, payload.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="用户名已被占用"
        )
    if payload.email and user_repository.get_by_email(session, payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="邮箱已被注册"
        )

    user = User(
        username=payload.username,
        email=payload.email,
        # ★ 只存哈希，禁止明文（说明书 §12）
        password_hash=hash_password(payload.password),
        nickname=payload.nickname or payload.username,
        family_size=payload.family_size,
    )
    user_repository.create(session, user)

    # 顺手建一条空偏好，省得后面每个接口都要判 None
    session.add(UserPreference(user_id=user.id))
    session.commit()
    return user


def login(
    session: Session,
    payload: LoginRequest,
    request: Request | None = None,
) -> str:
    """校验密码并签发 token。返回 access_token。"""
    user = user_repository.get_by_username(session, payload.username)

    # ⚠️ 用户名不存在和密码错误返回【同一句】提示，避免被人枚举用户名。
    if user is None or not verify_password(payload.password, user.password_hash):
        _record_login(
            session,
            user=user,
            username=payload.username,
            success=False,
            request=request,
            detail="用户名或密码不正确",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码不正确",
        )

    # 封禁校验放在密码校验【之后】—— 否则不看密码就能试出
    # 「这个账号存在而且被封了」，又是一个枚举入口。
    if user.is_banned:
        _record_login(
            session,
            user=user,
            username=payload.username,
            success=False,
            request=request,
            detail="账号已被封禁",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该账号已被管理员封禁",
        )

    user.last_login_at = utcnow()
    session.add(user)
    _record_login(
        session,
        user=user,
        username=payload.username,
        success=True,
        request=request,
    )
    return create_access_token(user.id)
