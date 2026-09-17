"""我的现有食材接口（说明书 §13）。

GET    /api/my-foods
POST   /api/my-foods
PUT    /api/my-foods/{item_id}
DELETE /api/my-foods/{item_id}

★ 这一组【全部需要登录】—— 说明书 §12 把「现有食材」列在需要登录的接口里。
"""

from fastapi import APIRouter, Depends, Response, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.my_food import MyFoodCreate, MyFoodPublic, MyFoodUpdate
from app.services import my_food_service

router = APIRouter(prefix="/my-foods", tags=["我的食材"])


@router.get("", response_model=list[MyFoodPublic], summary="我的食材列表")
def list_my_foods(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[MyFoodPublic]:
    return my_food_service.list_items(session, user.id)


@router.post(
    "",
    response_model=MyFoodPublic,
    status_code=201,
    summary="加入我的食材",
)
def add_my_food(
    payload: MyFoodCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MyFoodPublic:
    return my_food_service.add_item(session, user.id, payload)


@router.put("/{item_id}", response_model=MyFoodPublic, summary="修改库存")
def update_my_food(
    item_id: int,
    payload: MyFoodUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MyFoodPublic:
    return my_food_service.update_item(session, user.id, item_id, payload)


@router.delete("/{item_id}", status_code=204, summary="移出我的食材")
def remove_my_food(
    item_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    my_food_service.remove_item(session, user.id, item_id)
    return Response(status_code=204)
