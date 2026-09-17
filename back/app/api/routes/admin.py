"""管理员接口（本次新增，说明书里没有这一节）。

GET  /api/admin/stats              用户统计
GET  /api/admin/users              用户列表（分页 / 搜索）
POST /api/admin/users/{id}/ban     封禁
POST /api/admin/users/{id}/unban   解封
GET  /api/admin/logins             登录记录（分页 / 只看失败）

★ 全部需要【管理员】身份。普通用户拿到的是 403。
"""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_admin
from app.models.user import User
from app.schemas.admin import AdminStats, AdminUserRow, LoginLogRow
from app.schemas.common import Page
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["管理员"])


@router.get("/stats", response_model=AdminStats, summary="用户统计")
def get_stats(
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> AdminStats:
    return admin_service.stats(session)


@router.get("/users", response_model=Page[AdminUserRow], summary="用户列表")
def list_users(
    keyword: str | None = Query(default=None, description="按用户名 / 昵称搜"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> Page[AdminUserRow]:
    items, total = admin_service.list_users(
        session, keyword=keyword, page=page, page_size=page_size
    )
    return Page[AdminUserRow](
        items=items, total=total, page=page, page_size=page_size
    )


@router.post(
    "/users/{user_id}/ban", response_model=AdminUserRow, summary="封禁用户"
)
def ban_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> AdminUserRow:
    return admin_service.set_banned(
        session, admin=admin, user_id=user_id, banned=True
    )


@router.post(
    "/users/{user_id}/unban", response_model=AdminUserRow, summary="解封用户"
)
def unban_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> AdminUserRow:
    return admin_service.set_banned(
        session, admin=admin, user_id=user_id, banned=False
    )


@router.get("/logins", response_model=Page[LoginLogRow], summary="登录记录")
def list_logins(
    only_failed: bool = Query(default=False, description="只看失败的尝试"),
    username: str | None = Query(default=None, description="按用户名模糊搜"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> Page[LoginLogRow]:
    items, total = admin_service.list_logins(
        session,
        only_failed=only_failed,
        username=username,
        page=page,
        page_size=page_size,
    )
    return Page[LoginLogRow](
        items=items, total=total, page=page, page_size=page_size
    )
