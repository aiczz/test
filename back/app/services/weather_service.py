"""天气上下文 —— 首页推荐要考虑「今天什么天气」。

【为什么用 Open-Meteo】
它免费、**不需要申请 key**（自托管的服务器上最省事），一个 GET 就拿到
当前温度/降水/天气码。接别的付费天气 API 只会给部署加一道申请手续。

【为什么天气挂了首页也必须能用】
天气是「加分项」，不是「必需项」。所以这里有三档：
    live      —— 真的拿到了今天的天气
    estimated —— 拿不到，按月份的时令气候给一个合理估计（比如 9 月按「秋燥」）
    unknown   —— 连月份都判断不了（理论上不会发生）
三档都会返回一个可用的 WeatherContext，调用方不需要写 if。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date as date_cls
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 内置城市坐标，和前端 lib/services/city.dart 的 kCities 保持一致。
# 有了它，`/api/home?city=杭州` 不传经纬度也能取到天气（curl / /docs 里好调试）。
CITY_COORDS: dict[str, tuple[float, float]] = {
    "北京": (39.90, 116.41),
    "上海": (31.23, 121.47),
    "广州": (23.13, 113.26),
    "深圳": (22.54, 114.06),
    "杭州": (30.27, 120.16),
    "南京": (32.06, 118.80),
    "苏州": (31.30, 120.58),
    "成都": (30.57, 104.07),
    "重庆": (29.56, 106.55),
    "武汉": (30.59, 114.31),
    "西安": (34.34, 108.94),
    "长沙": (28.23, 112.94),
    "青岛": (36.07, 120.38),
    "天津": (39.08, 117.20),
    "郑州": (34.75, 113.63),
    "沈阳": (41.81, 123.43),
}

# WMO 天气码 → 人话
_WMO_TEXT: list[tuple[tuple[int, ...], str]] = [
    ((0,), "晴"),
    ((1,), "晴间多云"),
    ((2,), "多云"),
    ((3,), "阴"),
    ((45, 48), "有雾"),
    ((51, 53, 55, 56, 57), "毛毛雨"),
    ((61, 63, 65, 66, 67), "下雨"),
    ((71, 73, 75, 77), "下雪"),
    ((80, 81, 82), "阵雨"),
    ((85, 86), "阵雪"),
    ((95, 96, 99), "雷阵雨"),
]

_RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
_SNOW_CODES = {71, 73, 75, 77, 85, 86}


@dataclass(slots=True)
class WeatherContext:
    """首页打分要用的天气上下文。三个 data source 都返回它。"""

    city: str | None
    date: str
    kind: str  # cold / hot / rain / snow / dry / mild / unknown
    description: str
    temperature_c: float | None = None
    source: str = "unknown"  # live / estimated / unknown
    # 确定性饮食建议。AI 在线时会被改写得更自然，AI 不可用时直接用这条。
    advice: str = ""

    def as_prompt_line(self) -> str:
        return f"{self.date} {self.city or '未指定地区'} 天气：{self.description}（{self.advice}）"


def _wmo_text(code: int | None) -> str:
    if code is None:
        return "天气未知"
    for codes, label in _WMO_TEXT:
        if code in codes:
            return label
    return "天气未知"


def _kind_from(
    *, temperature: float | None, code: int | None, month: int
) -> str:
    """把温度/天气码/月份归成一个「饮食意图」。"""
    if code in _SNOW_CODES:
        return "snow"
    if code is not None and code in _RAIN_CODES:
        return "rain"
    if temperature is not None:
        if temperature <= 10:
            return "cold"
        if temperature >= 30:
            return "hot"
    # 没有实时温度时，用月份给一个季节性的默认意图。
    # 9-11 月是「秋燥」，这是本项目的时令知识库（seasonal_calendar）里写着的。
    if month in (9, 10, 11):
        return "dry"
    if month in (6, 7, 8):
        return "hot"
    if month in (12, 1, 2):
        return "cold"
    return "mild"


_ADVICE: dict[str, str] = {
    "cold": "天冷，适合热汤热炖，暖身又好消化",
    "hot": "天热，优先清爽少油的菜，别让灶台再加热",
    "rain": "湿气重，来点祛湿暖胃的汤水",
    "snow": "寒潮天，热乎的炖菜最合适",
    "dry": "秋燥当令，润肺生津的食材优先",
    "mild": "天气平和，按当季时令正常搭配就好",
    "unknown": "按当季时令搭配",
}


def _estimated(city: str | None, month: int, today: str) -> WeatherContext:
    kind = _kind_from(temperature=None, code=None, month=month)
    season_hint = {
        9: "初秋",
        10: "仲秋",
        11: "深秋",
        6: "初夏",
        7: "盛夏",
        8: "夏末",
        12: "初冬",
        1: "深冬",
        2: "冬末",
    }.get(month, f"{month} 月")
    return WeatherContext(
        city=city,
        date=today,
        kind=kind,
        description=f"{season_hint}（未取到实时天气，按季节估算）",
        source="estimated",
        advice=_ADVICE[kind],
    )


# 同一天同一地点只请求一次 —— 首页是热点接口，不能每次刷新都打外部 API。
_cache: dict[str, WeatherContext] = {}
_cache_lock = threading.Lock()


def _coords_for(city: str | None, lat: float | None, lon: float | None):
    if lat is not None and lon is not None:
        return lat, lon
    if city:
        hit = CITY_COORDS.get(city.strip())
        if hit:
            return hit
    return None, None


def current_weather(
    *,
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    today: str | None = None,
    month: int | None = None,
) -> WeatherContext:
    """取天气。永远返回可用的上下文，绝不抛异常。"""
    today = today or date_cls.today().isoformat()
    month = month or date_cls.today().month

    if not settings.weather_enabled:
        return _estimated(city, month, today)

    latitude, longitude = _coords_for(city, lat, lon)
    if latitude is None or longitude is None:
        # 不知道在哪，就别瞎猜天气 —— 按季节估算
        return _estimated(city, month, today)

    cache_key = f"{round(latitude, 2)},{round(longitude, 2)}:{today}"
    with _cache_lock:
        cached = _cache.get(cache_key)
    if cached is not None:
        # 缓存命中也要带上这次请求的城市名，否则换个城市会显示上一个名字
        cached.city = city
        return cached

    context = _fetch(latitude, longitude, city=city, today=today, month=month)
    with _cache_lock:
        _cache[cache_key] = context
        # 缓存不做复杂淘汰：一天一个 key，量级是「城市数」，不会涨。
        if len(_cache) > 512:
            _cache.clear()
            _cache[cache_key] = context
    return context


def _fetch(
    latitude: float, longitude: float, *, city: str | None, today: str, month: int
) -> WeatherContext:
    try:
        with httpx.Client(timeout=settings.weather_timeout_seconds) as client:
            response = client.get(
                settings.weather_base_url,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,precipitation,weather_code",
                    "timezone": "Asia/Shanghai",
                },
            )
        if response.status_code != 200:
            logger.warning("天气接口返回 %s", response.status_code)
            return _estimated(city, month, today)

        current: dict[str, Any] = response.json().get("current") or {}
        temperature = current.get("temperature_2m")
        code = current.get("weather_code")
        temperature = float(temperature) if temperature is not None else None
        code = int(code) if code is not None else None

        kind = _kind_from(temperature=temperature, code=code, month=month)
        label = _wmo_text(code)
        temp_text = f"{round(temperature)}°C" if temperature is not None else "气温未知"

        return WeatherContext(
            city=city,
            date=today,
            kind=kind,
            description=f"{label} {temp_text}",
            temperature_c=temperature,
            source="live",
            advice=_ADVICE[kind],
        )
    except Exception as exc:  # noqa: BLE001 —— 外部接口，任何错都退回估算
        logger.warning("天气查询失败，改用季节估算：%s", exc)
        return _estimated(city, month, today)


def reset_cache() -> None:
    """测试用：清掉进程内缓存。"""
    with _cache_lock:
        _cache.clear()
