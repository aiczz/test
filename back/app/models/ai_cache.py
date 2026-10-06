"""AI 结果缓存表。

【为什么需要它】
首页推荐要满足三条同时成立的要求：
  1. 同一地区、同一天，所有用户看到的一样；
  2. 不同天不一样；
  3. 不能每个用户、每次刷新都去问一次大模型 —— 那是白烧 token。

所以把「首页那一次 AI 调用」的结果按 (地区, 日期) 落库：
一个地区一天只会真正调用一次模型，之后全部命中缓存。
这既保证了 1、2 两条的确定性，也把 token 成本压到每天每地区一次。

【为什么键里还要带天气和季节】
天气会变（同一地区同一天里如果天气数据源换了口径），季节跨月会变。
把它们并进键里，缓存就只在「真正相同的推荐前提」下复用。
"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class AiDailyCache(SQLModel, table=True):
    """按业务键缓存 AI 生成结果。"""

    __tablename__ = "ai_daily_cache"

    # 业务键，如 home:杭州:2026-10-05:秋:rain
    key: str = Field(primary_key=True)
    # AI 返回的结构化结果（JSON 字符串）。存原文，方便排错与回放。
    payload: str
    # 用的是哪个模型 —— 换模型后旧缓存不该继续命中
    model: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
