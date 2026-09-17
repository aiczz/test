"""管理员业务逻辑。

说明书里没有这一节 —— 这是本次新增的后台管理功能：
用户统计、用户列表、封禁 / 解封、登录记录。
"""

from datetime import datetime, time, timezone

from fastapi import HTTPException, status
from sqlmodel import Session, col, func, select

from app.models.user import User
from app.repositories import admin_repository
from app.schemas.admin import AdminStats, AdminUserRow, LoginLogRow


def _today_start() -> datetime:
    """今天的 00:00（UTC）。

    ⚠️ 演示项目统一按 UTC 算「今天」。真要按中国时区算，
       得先把时区配置引入进来 —— 为了几个统计数字不值得，
       但如果你介意「早上 8 点前看今天的统计是空的」，告诉我，
       我把时区做成配置项。
    """
    now = datetime.now(timezone.utc)
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


def _count_users(session: Session, condition=None) -> int:
    statement = select(func.count()).select_from(User)
    if condition is not None:
        statement = statement.where(condition)
    return int(session.exec(statement).one())


def _to_row(session: Session, user: User) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        email=user.email,
        family_size=user.family_size,
        is_admin=user.is_admin,
        is_banned=user.is_banned,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        login_count=admin_repository.count_logins_for_user(session, user.id),
    )


def stats(session: Session) -> AdminStats:
    today = _today_start()
    return AdminStats(
        total_users=_count_users(session),
        admin_users=_count_users(session, col(User.is_admin).is_(True)),
        banned_users=_count_users(session, col(User.is_banned).is_(True)),
        new_users_today=_count_users(session, User.created_at >= today),
        total_logins=admin_repository.count_logins(session),
        logins_today=admin_repository.count_logins(session, since=today),
        failed_logins_today=admin_repository.count_logins(
            session, since=today, only_failed=True
        ),
        active_users_today=admin_repository.count_active_users_since(session, today),
    )


def list_users(
    session: Session,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AdminUserRow], int]:
    total = admin_repository.count_users(session, keyword=keyword)
    rows = admin_repository.list_users(
        session,
        keyword=keyword,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return [_to_row(session, user) for user in rows], total


def set_banned(
    session: Session, *, admin: User, user_id: int, banned: bool
) -> AdminUserRow:
    target = admin_repository.get_user(session, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在"
        )

    # ★ 两个保护，缺一个都会把系统锁死：
    #   1. 不能封自己 —— 封了就没人能解封了
    #   2. 不能封别的管理员 —— 防止管理员互相封禁，最后谁也进不去
    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="不能封禁自己的账号"
        )
    if target.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="不能封禁管理员账号"
        )

    target.is_banned = banned
    return _to_row(session, admin_repository.save_user(session, target))


def list_logins(
    session: Session,
    *,
    only_failed: bool = False,
    username: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> tuple[list[LoginLogRow], int]:
    total = admin_repository.count_logins(
        session, only_failed=only_failed, username=username
    )
    rows = admin_repository.list_logins(
        session,
        only_failed=only_failed,
        username=username,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return (
        [
            LoginLogRow(
                id=row.id,
                user_id=row.user_id,
                username=row.username,
                success=row.success,
                ip=row.ip,
                user_agent=row.user_agent,
                detail=row.detail,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total,
    )
