"""首页聚合接口（说明书 §9）。

GET /api/home?region=杭州&month=9

本次新增（全部可选，不传就是旧行为）：
    city / lat / lon  —— 定位信息，用来取当地天气
    date              —— 指定日期，便于回放与测试（默认服务器当天）
    people / cook_minutes / low_sodium / preferences / avoid  —— 家庭硬约束
    refresh           —— 忽略当天的 AI 缓存，强制重新生成（演示/排错用）
"""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.home import HomeResponse
from app.services import home_service

router = APIRouter(tags=["首页"])


class _InlineProfile:
    """把查询参数拼成一个「长得像家庭档案」的对象。

    这样 home_service 既能接受前端的 profile JSON，也能接受 URL 参数 ——
    在 /docs 里手点调试时不用先构造一个嵌套 JSON。
    """

    __slots__ = ("people", "cook_minutes", "low_sodium", "preferences", "avoid")

    def __init__(
        self,
        people: int,
        cook_minutes: float,
        low_sodium: bool,
        preferences: list[str],
        avoid: list[str],
    ) -> None:
        self.people = people
        self.cook_minutes = cook_minutes
        self.low_sodium = low_sodium
        self.preferences = preferences
        self.avoid = avoid


@router.get("/home", response_model=HomeResponse, summary="首页聚合")
def get_home(
    region: str | None = Query(default=None, description="地区，如 杭州"),
    month: int | None = Query(
        default=None, ge=1, le=12, description="月份，留空用服务器当前月"
    ),
    city: str | None = Query(default=None, description="定位城市名，如 杭州"),
    lat: float | None = Query(default=None, description="纬度（有它就不用内置城市表）"),
    lon: float | None = Query(default=None, description="经度"),
    date: str | None = Query(
        default=None, description="日期 YYYY-MM-DD，留空用服务器当天"
    ),
    people: int = Query(default=3, ge=1, le=20, description="就餐人数"),
    cook_minutes: float = Query(default=45, ge=5, le=240, description="可用烹饪时间"),
    low_sodium: bool = Query(default=False, description="是否限钠"),
    preferences: list[str] | None = Query(default=None, description="口味偏好"),
    avoid: list[str] | None = Query(default=None, description="忌口"),
    refresh: bool = Query(default=False, description="忽略当天 AI 缓存，强制重算"),
    session: Session = Depends(get_session),
) -> HomeResponse:
    profile = _InlineProfile(
        people=people,
        cook_minutes=cook_minutes,
        low_sodium=low_sodium,
        preferences=list(preferences or []),
        avoid=list(avoid or []),
    )
    return home_service.build_home(
        session,
        region=region,
        month=month,
        city=city,
        lat=lat,
        lon=lon,
        date_str=date,
        profile=profile,
        refresh=refresh,
    )
