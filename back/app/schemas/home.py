"""首页聚合响应（说明书 §9）。

⚠️ 兼容性红线：`HomeSeason` 的字段**不能变**。
   既有测试断言 `body["season"] == {"name": ..., "month": ..., "region": ...}`
   是「精确相等」，多加一个字段就会挂。
   所以这次的扩展一律走「新增字段 + 默认值」的方式，不动任何既有字段。
"""

from pydantic import BaseModel

from app.schemas.food import FoodBrief
from app.schemas.recipe import RecipeBrief


class HomeSeason(BaseModel):
    name: str
    month: int
    region: str | None = None


class HomeHero(BaseModel):
    title: str
    subtitle: str
    image: str | None = None


class MenuBrief(BaseModel):
    id: int
    title: str
    image: str | None = None
    servings: str
    tags: list[str] = []


# =====================================================================
# 以下是本次新增：天气、推荐理由、算法轨迹
# =====================================================================


class HomeWeather(BaseModel):
    """今天的天气上下文。取不到实时天气时会带 source=estimated。"""

    city: str | None = None
    date: str
    # cold / hot / rain / snow / dry / mild / unknown
    kind: str
    description: str
    advice: str
    temperature_c: float | None = None
    # live（实时） / estimated（按季节估算） / unknown
    source: str


class HomeFoodItem(FoodBrief):
    """首页推荐食材：在 FoodBrief 上补「为什么推荐它」。"""

    reason: str | None = None
    highlights: list[str] = []
    score: float | None = None


class HomeRecipeItem(RecipeBrief):
    """首页推荐菜品：同上。"""

    reason: str | None = None
    highlights: list[str] = []
    score: float | None = None


class HomeAlgoStep(BaseModel):
    """一步算法/模型动作，答辩时可以直接展开给评委看。"""

    step: str
    detail: str
    ms: int = 0


class HomeMeta(BaseModel):
    """这次首页结果是怎么来的 —— 如实标注，不夸大。"""

    # ai：这次真的调了大模型；cached：命中当天缓存（同地区同一天所有人共用）
    # algorithm：没配 AI / 调用失败，全部由确定性算法给出
    source: str = "algorithm"
    model: str | None = None
    ai_ms: int = 0
    cache_key: str | None = None
    shortlist_foods: int = 0
    shortlist_dishes: int = 0
    steps: list[HomeAlgoStep] = []


class HomeResponse(BaseModel):
    """说明书 §9：首页必须同时包含「食材推荐」和「菜单推荐」。

    ★ 刻意不返回价格字段（说明书 §9 明确要求）。
    """

    season: HomeSeason
    hero: HomeHero
    recommended_foods: list[HomeFoodItem]
    recommended_menus: list[MenuBrief]
    ai_tip: str

    # ---- 以下为新增，全部带默认值，老客户端不受影响 ----
    ai_tip_title: str | None = None
    recommended_recipes: list[HomeRecipeItem] = []
    weather: HomeWeather | None = None
    meta: HomeMeta | None = None
