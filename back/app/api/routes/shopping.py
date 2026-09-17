"""购物清单接口（说明书 §19）。

POST /api/shopping-list/generate
GET  /api/shopping-list
PUT  /api/shopping-list/items/{item_id}
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.shopping import (
    GenerateShoppingListRequest,
    ShoppingItemPublic,
    ShoppingItemUpdate,
    ShoppingListResponse,
)
from app.services import shopping_service

router = APIRouter(prefix="/shopping-list", tags=["购物清单"])


@router.post(
    "/generate",
    response_model=ShoppingListResponse,
    summary="由菜单生成购物清单",
)
def generate(
    payload: GenerateShoppingListRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ShoppingListResponse:
    return shopping_service.generate(session, user.id, payload)


@router.get("", response_model=ShoppingListResponse, summary="最近的购物清单")
def get_latest(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ShoppingListResponse:
    result = shopping_service.get_latest(session, user.id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="还没有购物清单，先调 /api/shopping-list/generate",
        )
    return result


@router.put(
    "/items/{item_id}",
    response_model=ShoppingItemPublic,
    summary="勾选 / 取消勾选",
)
def update_item(
    item_id: int,
    payload: ShoppingItemUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ShoppingItemPublic:
    return shopping_service.update_item(session, user.id, item_id, payload)
