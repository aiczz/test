"""收藏业务逻辑（说明书 §15）。"""

from fastapi import HTTPException, status
from sqlmodel import Session

from app.repositories import favorite_repository, recipe_repository
from app.schemas.favorite import FavoriteListResponse, FavoriteToggleResponse
from app.services import recipe_service


def list_favorites(session: Session, user_id: int) -> FavoriteListResponse:
    recipes = favorite_repository.list_recipes(session, user_id)
    return FavoriteListResponse(
        items=[recipe_service.to_brief(r) for r in recipes],
        total=len(recipes),
    )


def add_favorite(
    session: Session, user_id: int, recipe_id: int
) -> FavoriteToggleResponse:
    if recipe_repository.get(session, recipe_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="菜谱不存在"
        )
    # 说明书 §15：重复收藏不要生成重复记录。
    # 仓储层的 add() 命中已有记录时直接返回，所以这里天然幂等。
    favorite_repository.add(session, user_id, recipe_id)
    return FavoriteToggleResponse(recipe_id=recipe_id, is_favorite=True)


def remove_favorite(
    session: Session, user_id: int, recipe_id: int
) -> FavoriteToggleResponse:
    # 取消一个本来就没收藏的菜谱不报错 —— 幂等，前端重试也安全
    favorite_repository.remove(session, user_id, recipe_id)
    return FavoriteToggleResponse(recipe_id=recipe_id, is_favorite=False)
