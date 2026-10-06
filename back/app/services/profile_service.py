"""个人偏好业务逻辑（说明书 §12 里「需要登录」的个人偏好）。"""

from sqlmodel import Session

from app.models.user import User
from app.repositories import user_repository
from app.schemas.profile import PreferencePublic, PreferenceUpdate


def _to_public(user: User, preference) -> PreferencePublic:
    return PreferencePublic(
        taste=preference.taste,
        diet_style=preference.diet_style,
        avoid_foods=list(preference.avoid_foods or []),
        favorite_categories=list(preference.favorite_categories or []),
        family_size=user.family_size,
        preferences=list(preference.diet_preferences or []),
        tools=list(preference.tools or []),
        low_sodium=bool(preference.low_sodium),
        cook_minutes=int(preference.cook_minutes),
    )


def get_profile(session: Session, user: User) -> PreferencePublic:
    preference = user_repository.ensure_preference(session, user.id)
    return _to_public(user, preference)


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
    if payload.preferences is not None:
        # 去重但保序：用户勾选的顺序会被前端原样显示，排序会显得莫名其妙
        preference.diet_preferences = list(dict.fromkeys(payload.preferences))
    if payload.tools is not None:
        preference.tools = list(dict.fromkeys(payload.tools))
    if payload.low_sodium is not None:
        preference.low_sodium = payload.low_sodium
    if payload.cook_minutes is not None:
        preference.cook_minutes = payload.cook_minutes
    session.add(preference)

    # 家庭人数在 users 表上，但对前端来说和偏好是一组设置
    if payload.family_size is not None:
        user.family_size = payload.family_size
        session.add(user)

    session.commit()
    session.refresh(preference)
    session.refresh(user)
    return _to_public(user, preference)
