"""菜单接口（说明书 §16 / §17）。

GET  /api/menu/today
POST /api/menu/today/generate
POST /api/menu/plan

★ 全部需要登录（说明书 §12 把「菜单」列在需要登录的接口里）。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.menu import (
    MenuPlanRequest,
    MenuPlanResponse,
    TodayMenuGenerateRequest,
    TodayMenuResponse,
)
from app.services import menu_service

router = APIRouter(prefix="/menu", tags=["菜单"])


@router.get("/today", response_model=TodayMenuResponse, summary="今日菜单")
def get_today(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TodayMenuResponse:
    result = menu_service.get_today(session, user.id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="还没有生成今日菜单，先调 /api/menu/today/generate",
        )
    return result


@router.post(
    "/today/generate",
    response_model=TodayMenuResponse,
    summary="生成今日菜单",
)
def generate_today(
    payload: TodayMenuGenerateRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TodayMenuResponse:
    return menu_service.generate_today(session, user.id, payload)


@router.post("/plan", response_model=MenuPlanResponse, summary="生成多日菜单")
def generate_plan(
    payload: MenuPlanRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MenuPlanResponse:
    return menu_service.generate_plan(session, user.id, payload)
