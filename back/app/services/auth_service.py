"""认证业务逻辑（说明书 §12）。"""

from fastapi import HTTPException, Request, status
from sqlmodel import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.login_log import LoginLog
from app.models.user import User, UserPreference
from app.repositories import user_repository
from app.schemas.auth import (
    EmailAuthRequest,
    EmailRegisterRequest,
    LoginRequest,
    RegisterRequest,
    SmsAuthRequest,
    SmsRegisterRequest,
)
from app.services import verification_service
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


def _verify_demo_sms(payload: SmsAuthRequest) -> None:
    # 当前没有短信供应商，固定码仅用于竞赛演示；以后只需替换这里的校验。
    if payload.code != "123456":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确"
        )


def register_sms(session: Session, payload: SmsRegisterRequest) -> User:
    _verify_demo_sms(payload)
    return register(
        session,
        RegisterRequest(
            username=payload.phone,
            password=payload.password,
            nickname=f"用户{payload.phone[-4:]}",
        ),
    )


def login_sms(
    session: Session, payload: SmsAuthRequest, request: Request | None = None
) -> str:
    _verify_demo_sms(payload)
    user = user_repository.get_by_username(session, payload.phone)
    if user is None:
        _record_login(
            session,
            user=None,
            username=payload.phone,
            success=False,
            request=request,
            detail="该手机号还没有注册",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="该手机号还没有注册，请先完成注册",
        )
    if user.is_banned:
        _record_login(
            session,
            user=user,
            username=payload.phone,
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
        username=payload.phone,
        success=True,
        request=request,
    )
    return create_access_token(user.id)


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


# --------------------------------------------------------------------- 邮箱验证码
#
# 与上面 sms/* 的区别：sms/* 认的是硬编码的演示码，这两条走的是
# verification_service 的真实机制（随机码 + 过期 + 限流 + 防重放）。


def register_email(session: Session, payload: EmailRegisterRequest) -> User:
    """邮箱验证码注册：先验码，再建账号（用户名直接用邮箱）。"""
    verification_service.consume_code(
        session,
        target=payload.email,
        purpose="register",
        code=payload.code,
    )

    email = verification_service.normalize_target(payload.email)
    # 先自己拦一道，好给一句比 register() 里「用户名已被占用」更有用的提示
    if user_repository.get_by_email(session, email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已经注册过了，请直接登录",
        )

    local_part = email.split("@", 1)[0]
    return register(
        session,
        RegisterRequest(
            username=email,
            password=payload.password,
            email=email,
            nickname=f"用户{local_part[:12]}",
        ),
    )


def login_email(
    session: Session,
    payload: EmailAuthRequest,
    request: Request | None = None,
) -> str:
    """邮箱验证码登录。返回 access_token。"""
    verification_service.consume_code(
        session,
        target=payload.email,
        purpose="login",
        code=payload.code,
    )

    email = verification_service.normalize_target(payload.email)
    user = user_repository.get_by_email(session, email)
    if user is None:
        # 兼容早期账号：那时候 username 存的就是邮箱
        user = user_repository.get_by_username(session, email)

    if user is None:
        _record_login(
            session,
            user=None,
            username=email,
            success=False,
            request=request,
            detail="该邮箱还没有注册",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="该邮箱还没有注册，请先完成注册",
        )

    if user.is_banned:
        _record_login(
            session,
            user=user,
            username=email,
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
        username=email,
        success=True,
        request=request,
    )
    return create_access_token(user.id)
