"""AI 助手（说明书 §20）。

★ 这一版是【规则生成】，不是真的调用大模型 ——
  说明书 §18「第一版不要把全部逻辑交给 LLM」和 §14「第一版可以先用规则匹配」
  都明确允许这么做。响应结构和真接口完全一致，将来换成 LLM 时前端不用改。
"""

from pydantic import BaseModel, Field

from app.schemas.recipe import RecipeBrief


class AiChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    conversation_id: int | None = None


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
