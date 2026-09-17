"""首页聚合接口（说明书 §9）。

GET /api/home?region=杭州&month=9
"""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.home import HomeResponse
from app.services import home_service

router = APIRouter(tags=["首页"])


@router.get("/home", response_model=HomeResponse, summary="首页聚合")
def get_home(
    region: str | None = Query(default=None, description="地区，如 杭州"),
    month: int | None = Query(
        default=None, ge=1, le=12, description="月份，留空用服务器当前月"
    ),
    session: Session = Depends(get_session),
) -> HomeResponse:
    return home_service.build_home(session, region=region, month=month)
