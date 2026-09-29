"""收藏接口（说明书 §15）。

GET    /api/favorites
POST   /api/favorites/{recipe_id}
DELETE /api/favorites/{recipe_id}

两个写接口都是【幂等】的：重复收藏不会产生重复记录，
取消一个本来就没收藏的也不报错。
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.favorite import FavoriteListResponse, FavoriteToggleResponse
from app.services import favorite_service

router = APIRouter(prefix="/favorites", tags=["收藏"])


@router.get("", response_model=FavoriteListResponse, summary="我的收藏")
def list_favorites(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FavoriteListResponse:
    return favorite_service.list_favorites(session, user.id)


@router.post(
    "/{recipe_id}",
    response_model=FavoriteToggleResponse,
    summary="收藏（幂等）",
)
def add_favorite(
    recipe_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FavoriteToggleResponse:
    return favorite_service.add_favorite(session, user.id, recipe_id)


@router.delete(
    "/{recipe_id}",
    response_model=FavoriteToggleResponse,
    summary="取消收藏（幂等）",
)
def remove_favorite(
    recipe_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> FavoriteToggleResponse:
    return favorite_service.remove_favorite(session, user.id, recipe_id)
