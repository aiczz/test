"""个人偏好接口（说明书 §12 的「个人偏好」）。

GET /api/profile
PUT /api/profile
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.profile import PreferencePublic, PreferenceUpdate
from app.services import profile_service

router = APIRouter(prefix="/profile", tags=["个人偏好"])


@router.get("", response_model=PreferencePublic, summary="我的偏好")
def get_profile(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PreferencePublic:
    return profile_service.get_profile(session, user)


@router.put("", response_model=PreferencePublic, summary="更新偏好")
def update_profile(
    payload: PreferenceUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PreferencePublic:
    return profile_service.update_profile(session, user, payload)
