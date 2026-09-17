"""认证接口（说明书 §12）。

POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)
from app.services import auth_service

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
    session: Session = Depends(get_session),
) -> TokenResponse:
    return TokenResponse(access_token=auth_service.login(session, payload))


@router.get("/me", response_model=UserPublic, summary="当前登录用户")
def me(user: User = Depends(get_current_user)) -> User:
    return user
