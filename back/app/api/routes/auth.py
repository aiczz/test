"""认证接口（说明书 §12）。

POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
DELETE /api/auth/me     注销账号（真删，管理员/演示账号 403）

POST /api/auth/sms/*    手机号 + 固定演示码（仅演示，见 auth_service._verify_demo_sms）
POST /api/auth/email/*  邮箱 + 真实验证码（随机码、有过期与限流，见 verification_service）
"""

from fastapi import APIRouter, Depends, Request, Response
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    CodeSentResponse,
    EmailAuthRequest,
    EmailCodeRequest,
    EmailRegisterRequest,
    LoginRequest,
    RegisterRequest,
    SmsAuthRequest,
    SmsRegisterRequest,
    TokenResponse,
    UserPublic,
)
from app.services import auth_service, verification_service

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=201,
    summary="注册",
)
def register(
    payload: RegisterRequest,
    session: Session = Depends(get_session),
) -> User:
    return auth_service.register(session, payload)


@router.post("/login", response_model=TokenResponse, summary="登录")
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TokenResponse:
    # 传 Request 下去是为了记登录日志（IP / User-Agent）——
    # 管理员页面靠它「监听」谁在什么时候登录了
    return TokenResponse(
        access_token=auth_service.login(session, payload, request)
    )


@router.post(
    "/sms/register",
    response_model=UserPublic,
    status_code=201,
    summary="手机号验证码注册（演示码）",
)
def register_sms(
    payload: SmsRegisterRequest,
    session: Session = Depends(get_session),
) -> User:
    return auth_service.register_sms(session, payload)


@router.post("/sms/login", response_model=TokenResponse, summary="手机号验证码登录")
def login_sms(
    payload: SmsAuthRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TokenResponse:
    return TokenResponse(
        access_token=auth_service.login_sms(session, payload, request)
    )


@router.get("/me", response_model=UserPublic, summary="当前登录用户")
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.delete("/me", status_code=204, summary="注销账号（真正删除）")
def delete_me(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """★ 真删，不是停用：账号和它名下的收藏 / 菜单 / 购物清单 / 口味偏好
    一并从库里消失，不可恢复。

    ★ 管理员与演示账号会被 403 拒绝 —— 演示账号删掉，评委就进不来了。
    具体顺序与理由见 auth_service.delete_account。
    """
    auth_service.delete_account(session, user)
    return Response(status_code=204)


# ---------------------------------------------------------------- 邮箱验证码


@router.post(
    "/email/send-code",
    response_model=CodeSentResponse,
    summary="发送邮箱验证码",
)
def send_email_code(
    payload: EmailCodeRequest,
    session: Session = Depends(get_session),
) -> CodeSentResponse:
    """给邮箱发一条 6 位验证码。

    限流：同一邮箱 60 秒内不能重发、每小时最多 5 条。
    响应里【不含】验证码本身 —— 只能从邮箱里拿到。
    """
    channel = verification_service.issue_code(
        session,
        target=payload.email,
        purpose=payload.purpose,
    )
    minutes = max(settings.code_ttl_seconds // 60, 1)
    return CodeSentResponse(
        channel=channel,
        expires_in=settings.code_ttl_seconds,
        message=(
            f"验证码已发送，{minutes} 分钟内有效"
            if channel == "smtp"
            else f"服务端未配置邮件通道，验证码只打在了服务日志里（{minutes} 分钟内有效）"
        ),
    )


@router.post(
    "/email/register",
    response_model=UserPublic,
    status_code=201,
    summary="邮箱验证码注册",
)
def register_email(
    payload: EmailRegisterRequest,
    session: Session = Depends(get_session),
) -> User:
    return auth_service.register_email(session, payload)


@router.post(
    "/email/login",
    response_model=TokenResponse,
    summary="邮箱验证码登录",
)
def login_email(
    payload: EmailAuthRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TokenResponse:
    return TokenResponse(
        access_token=auth_service.login_email(session, payload, request)
    )
