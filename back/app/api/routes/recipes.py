"""菜谱接口（说明书 §11）。

GET /api/recipes
GET /api/recipes/search?q=莲藕
GET /api/recipes/{recipe_id}
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user_optional
from app.models.user import User
from app.schemas.common import Page
from app.schemas.my_food import (
    RecommendByFoodsRequest,
    RecommendByFoodsResponse,
)
from app.schemas.recipe import RecipeBrief, RecipeDetail
from app.services import my_food_service, recipe_service

router = APIRouter(prefix="/recipes", tags=["菜谱"])


@router.get("", response_model=Page[RecipeBrief], summary="菜谱列表")
def list_recipes(
    category: str | None = Query(default=None),
    season: str | None = Query(default=None, description="如 秋季"),
    difficulty: str | None = Query(default=None, description="简单 / 中等"),
    max_duration: int | None = Query(
        default=None,
        ge=1,
        description="最长烹饪时间（分钟）—— 前端「每日可用烹饪时间」用它做硬筛",
    ),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> Page[RecipeBrief]:
    items, total = recipe_service.list_recipes(
        session,
        category=category,
        season=season,
        difficulty=difficulty,
        max_duration=max_duration,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return Page[RecipeBrief](
        items=items, total=total, page=page, page_size=page_size
    )


# ⚠️ /search 必须声明在 /{recipe_id} 之前
@router.get("/search", response_model=Page[RecipeBrief], summary="菜谱搜索")
def search_recipes(
    q: str = Query(min_length=1, description="菜名或食材名"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> Page[RecipeBrief]:
    items, total = recipe_service.search(
        session, q, page=page, page_size=page_size
    )
    return Page[RecipeBrief](
        items=items, total=total, page=page, page_size=page_size
    )


@router.post(
    "/recommend-by-foods",
    response_model=RecommendByFoodsResponse,
    summary="按现有食材推荐菜谱",
)
def recommend_by_foods(
    payload: RecommendByFoodsRequest,
    # 不传 food_ids 时用当前用户的库存，所以带 token 才有意义；
    # 但接口保持公开 —— 没登录且没传 food_ids 就返回空结果。
    user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> RecommendByFoodsResponse:
    return my_food_service.recommend_by_foods(
        session, user.id if user else None, payload
    )


@router.get("/{recipe_id}", response_model=RecipeDetail, summary="菜谱详情")
def get_recipe(
    recipe_id: int,
    # 详情页是公开的；带了 token 就顺便告诉前端这道菜有没有被当前用户收藏
    user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> RecipeDetail:
    detail = recipe_service.get_detail(
        session, recipe_id, user_id=user.id if user else None
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="菜谱不存在"
        )
    return detail
