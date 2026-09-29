"""个人偏好业务逻辑（说明书 §12 里「需要登录」的个人偏好）。"""

from sqlmodel import Session

from app.models.user import User
from app.repositories import user_repository
from app.schemas.profile import PreferencePublic, PreferenceUpdate


def get_profile(session: Session, user: User) -> PreferencePublic:
    preference = user_repository.ensure_preference(session, user.id)
    return PreferencePublic(
        taste=preference.taste,
        diet_style=preference.diet_style,
        avoid_foods=list(preference.avoid_foods or []),
        favorite_categories=list(preference.favorite_categories or []),
        family_size=user.family_size,
    )


def update_profile(
    session: Session, user: User, payload: PreferenceUpdate
) -> PreferencePublic:
    preference = user_repository.ensure_preference(session, user.id)

    # 只改传上来的字段 —— 没传的保持原值，避免 PUT 把别的字段清空
    if payload.taste is not None:
        preference.taste = payload.taste
    if payload.diet_style is not None:
        preference.diet_style = payload.diet_style
    if payload.avoid_foods is not None:
        preference.avoid_foods = payload.avoid_foods
    if payload.favorite_categories is not None:
        preference.favorite_categories = payload.favorite_categories
    session.add(preference)

    # 家庭人数在 users 表上，但对前端来说和偏好是一组设置
    if payload.family_size is not None:
        user.family_size = payload.family_size
        session.add(user)

    session.commit()
    return get_profile(session, user)
