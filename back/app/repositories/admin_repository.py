"""管理员数据访问。"""

from datetime import datetime

from sqlmodel import Session, col, func, select

from app.models.login_log import LoginLog
from app.models.user import User


# ---------------------------------------------------------------- 用户


def _user_conditions(keyword: str | None) -> list:
    if not keyword:
        return []
    like = f"%{keyword}%"
    return [col(User.username).like(like) | col(User.nickname).like(like)]


def count_users(session: Session, *, keyword: str | None = None) -> int:
    return int(
        session.exec(
            select(func.count())
            .select_from(User)
            .where(*_user_conditions(keyword))
        ).one()
    )


def list_users(
    session: Session, *, keyword: str | None = None, offset: int = 0, limit: int = 20
) -> list[User]:
    return list(
        session.exec(
            select(User)
            .where(*_user_conditions(keyword))
            .order_by(col(User.id))
            .offset(offset)
            .limit(limit)
        ).all()
    )


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def save_user(session: Session, user: User) -> User:
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def count_users_since(session: Session, since: datetime) -> int:
    return int(
        session.exec(
            select(func.count()).select_from(User).where(User.created_at >= since)
        ).one()
    )


# ---------------------------------------------------------------- 登录日志


def _log_conditions(
    *, only_failed: bool = False, since: datetime | None = None, username: str | None = None
) -> list:
    conditions: list = []
    if only_failed:
        conditions.append(col(LoginLog.success).is_(False))
    if since is not None:
        conditions.append(LoginLog.created_at >= since)
    if username:
        conditions.append(col(LoginLog.username).like(f"%{username}%"))
    return conditions


def count_logins(
    session: Session,
    *,
    only_failed: bool = False,
    since: datetime | None = None,
    username: str | None = None,
) -> int:
    return int(
        session.exec(
            select(func.count())
            .select_from(LoginLog)
            .where(
                *_log_conditions(
                    only_failed=only_failed, since=since, username=username
                )
            )
        ).one()
    )


def list_logins(
    session: Session,
    *,
    only_failed: bool = False,
    since: datetime | None = None,
    username: str | None = None,
    offset: int = 0,
    limit: int = 30,
) -> list[LoginLog]:
    return list(
        session.exec(
            select(LoginLog)
            .where(
                *_log_conditions(
                    only_failed=only_failed, since=since, username=username
                )
            )
            # 最新的在前 —— 管理员最关心刚刚发生了什么
            .order_by(col(LoginLog.id).desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )


def count_logins_for_user(session: Session, user_id: int) -> int:
    """该用户成功登录过多少次。"""
    return int(
        session.exec(
            select(func.count())
            .select_from(LoginLog)
            .where(
                LoginLog.user_id == user_id,
                col(LoginLog.success).is_(True),
            )
        ).one()
    )


def count_active_users_since(session: Session, since: datetime) -> int:
    """某时间之后登录成功过的【去重用户数】。"""
    return int(
        session.exec(
            select(func.count(func.distinct(LoginLog.user_id))).where(
                LoginLog.created_at >= since,
                col(LoginLog.success).is_(True),
                col(LoginLog.user_id).is_not(None),
            )
        ).one()
    )
