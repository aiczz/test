"""认证业务逻辑（说明书 §12）。"""

from fastapi import HTTPException, status
from sqlmodel import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserPreference
from app.repositories import user_repository
from app.schemas.auth import LoginRequest, RegisterRequest


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


def login(session: Session, payload: LoginRequest) -> str:
    """校验密码并签发 token。返回 access_token。"""
    user = user_repository.get_by_username(session, payload.username)

    # ⚠️ 用户名不存在和密码错误返回【同一句】提示，避免被人枚举用户名。
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码不正确",
        )
    return create_access_token(user.id)
