"""收藏（说明书 §15）。"""

from pydantic import BaseModel

from app.schemas.recipe import RecipeBrief


class FavoriteToggleResponse(BaseModel):
    recipe_id: int
    is_favorite: bool


class FavoriteListResponse(BaseModel):
    items: list[RecipeBrief] = []
    total: int = 0
