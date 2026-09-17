"""FastAPI 公共依赖。"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import decode_access_token
from app.models.user import User

# auto_error=False：没带 Authorization 头时返回 None 而不是直接抛 403。
# 这样「可选登录」和「必须登录」可以共用同一条解析路径。
_bearer = HTTPBearer(auto_error=False)


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User | None:
    """解析 Bearer token 并取用户。未登录 / token 无效都返回 None。"""
    if credentials is None:
        return None
    subject = decode_access_token(credentials.credentials)
    if subject is None or not subject.isdigit():
        return None

    user = session.get(User, int(subject))
    # ★ 被封禁的账号即使拿着没过期的 token 也不能再用 ——
    #   否则「封禁」只挡得住新登录，挡不住已经在线的会话。
    if user is not None and user.is_banned:
        return None
    return user


def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    """需要登录的接口用这个依赖。

    说明书 §12：收藏 / 现有食材 / 菜单 / 购物清单 / 个人偏好 需要登录，
    首页 / 食材 / 菜谱 公开。
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """管理员接口用这个依赖。

    ⚠️ 普通用户拿到的是 403 而不是 404 —— 管理员接口的存在不是秘密，
       但权限必须挡住。
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return user
