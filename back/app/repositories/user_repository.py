"""用户数据访问层（说明书 §5.3）。"""

from sqlmodel import Session, select

from app.models.user import User, UserPreference


def get_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_by_username(session: Session, username: str) -> User | None:
    return session.exec(select(User).where(User.username == username)).first()


def get_by_email(session: Session, email: str) -> User | None:
    return session.exec(select(User).where(User.email == email)).first()


def create(session: Session, user: User) -> User:
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def save(session: Session, user: User) -> User:
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_preference(session: Session, user_id: int) -> UserPreference | None:
    return session.exec(
        select(UserPreference).where(UserPreference.user_id == user_id)
    ).first()


def ensure_preference(session: Session, user_id: int) -> UserPreference:
    """取偏好；没有就建一条空的。避免调用方到处判 None。"""
    pref = get_preference(session, user_id)
    if pref is None:
        pref = UserPreference(user_id=user_id)
        session.add(pref)
        session.commit()
        session.refresh(pref)
    return pref
