"""AI 助手（说明书 §20 + 本次的真·大模型接入）。

【和之前那版的区别】
之前是纯规则（关键词意图 + 菜谱检索），响应结构对齐说明书 §20。
现在接上了 DeepSeek，但**规则那套原样保留做兜底** —— 没配 API Key、
网络不通、模型返回垃圾时，行为退化成和以前一模一样。

新增的 `trace` 是**真的**协作轨迹：每一步都来自后端实际做了什么
（召回了多少候选、过滤掉多少、模型耗时多少），不是前端写死的文案。
"""

from pydantic import BaseModel, Field

from app.schemas.recipe import RecipeBrief


class AiTraceStep(BaseModel):
    """一步真实的协作动作。"""

    agent: str
    summary: str
    # ok = 正常；veto = 否决（确定性规则拦下了不合适的候选）；info = 只读信息
    status: str = "ok"
    ms: int = 0


class AiContext(BaseModel):
    """聊天/配菜共用的家庭硬约束上下文。"""

    people: int = Field(default=3, ge=1, le=20)
    cook_minutes: float = Field(default=45, ge=5, le=240)
    low_sodium: bool = False
    preferences: list[str] = []
    avoid: list[str] = []
    city: str | None = None


class AiChatRequest(AiContext):
    message: str = Field(min_length=1, max_length=500)
    conversation_id: int | None = None

    # ---- 会话上下文（本次新增）----
    # 【为什么需要】
    # 意图识别是**逐句独立**的关键词匹配。用户接着问「换一批呢」「还有别的吗」，
    # 句子里没有任何「吃什么 / 推荐 / 菜单」，于是被判成闲聊，
    # 后端压根不去推荐 —— 表现就是「第一问有卡片，后面再问就没了」。
    #
    # 所以让前端把上一轮的信息带上来：
    #   · last_intent       —— 追问时继承它（配合下面的追问词判断）
    #   · recent_recipe_ids —— 已经展示过的菜，「换一批」要避开它们，
    #                         否则每天轮换因子是固定的，重问一次还是那三道
    last_intent: str | None = None
    recent_recipe_ids: list[int] = []


class AiMenuSummary(BaseModel):
    title: str
    summary: str


class AiChatResponse(BaseModel):
    answer: str
    intent: str
    # 说明书 §20：前端靠这个展示"多智能体用了哪些工具"
    tools_used: list[str] = []
    recipes: list[RecipeBrief] = []
    menu: AiMenuSummary | None = None

    # ---- 本次新增（都带默认值，老前端不受影响）----
    trace: list[AiTraceStep] = []
    # ai = 真的调了模型；algorithm = 规则兜底
    source: str = "algorithm"
    model: str | None = None


# =====================================================================
# 导航栏 AI 配菜（根据已选食材 + 今日菜单已选菜 + 硬约束推荐）
# =====================================================================


class AiRecommendRequest(AiContext):
    """配菜请求。

    前端把「用户选好的食材」和「今日菜单里已有的菜」一起传上来，
    后端负责补齐候选、过滤、并让模型在候选内挑选与解释。
    """

    # 用户选好的食材（我的食材里勾选的）。留空时会退回登录用户的库存。
    food_ids: list[int] = []
    # 今日菜单里已有的菜 —— 必须排除，不能重复推荐已经定下来的菜
    menu_recipe_ids: list[int] = []
    # 想配哪一餐，只影响文案措辞
    meal: str = "dinner"
    # 用户自由输入的一句话（可空），如「想吃点热乎的」
    message: str | None = Field(default=None, max_length=200)
    # 要几道
    count: int = Field(default=3, ge=1, le=6)


class AiRecipePick(BaseModel):
    """一条配菜推荐。"""

    recipe: RecipeBrief
    reason: str
    highlights: list[str] = []
    score: float | None = None
    # 这道菜用到了你已有的哪几样食材
    matched_foods: list[str] = []


class AiRecommendResponse(BaseModel):
    answer: str
    recommendations: list[AiRecipePick] = []
    trace: list[AiTraceStep] = []
    source: str = "algorithm"
    model: str | None = None
    # 这次实际用到的食材名（前端可以回显，让用户知道推荐是基于什么的）
    used_foods: list[str] = []
    # 被硬约束排除掉的菜名，如实说明「为什么没推它」
    filtered_out: list[str] = []
