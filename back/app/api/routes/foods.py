"""食材接口（说明书 §10）。

GET /api/foods
GET /api/foods/seasonal
GET /api/foods/{food_id}
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.common import Page
from app.schemas.food import FoodBrief, FoodDetail
from app.services import food_service

router = APIRouter(prefix="/foods", tags=["食材"])


@router.get("", response_model=Page[FoodBrief], summary="食材列表")
def list_foods(
    category: str | None = Query(
        default=None,
        description="vegetable / fruit / meat_egg / aquatic / soy / grain / seasoning",
    ),
    keyword: str | None = Query(default=None, description="按名称模糊搜"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> Page[FoodBrief]:
    items, total = food_service.list_foods(
        session,
        category=category,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return Page[FoodBrief](
        items=items, total=total, page=page, page_size=page_size
    )


# ⚠️ /seasonal 必须声明在 /{food_id} 之前，否则 "seasonal" 会被当成 food_id 匹配掉
@router.get("/seasonal", response_model=list[FoodBrief], summary="时令食材")
def list_seasonal(
    month: int | None = Query(
        default=None, ge=1, le=12, description="月份，留空用服务器当前月"
    ),
    limit: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[FoodBrief]:
    return food_service.list_seasonal(
        session, month=month or datetime.now().month, limit=limit
    )


@router.get("/{food_id}", response_model=FoodDetail, summary="食材详情")
def get_food(
    food_id: int,
    session: Session = Depends(get_session),
) -> FoodDetail:
    detail = food_service.get_detail(session, food_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="食材不存在"
        )
    return detail
