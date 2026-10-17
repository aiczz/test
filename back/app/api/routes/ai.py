"""AI 助手接口（说明书 §20 + 本次的配菜接口）。

POST /api/ai/chat       对话（登录可选：没登录也能聊，问到「我的食材」时会提示登录）
POST /api/ai/recommend  配菜（把已选食材 + 今日菜单已有菜 + 硬约束交给算法筛候选，
                        再由大模型在候选内挑选与解释）

⚠️ 两个接口都**不依赖**大模型可用：未配置 AI_API_KEY、超时、返回垃圾，
   都会退回确定性算法，行为与改造前一致（响应结构只增不改）。
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user_optional, get_current_user
from app.models.user import User
from app.schemas.ai import (
    AiChatRequest,
    AiChatResponse,
    AiRecommendRequest,
    AiRecommendResponse,
    RecipeFeedbackRequest, RecipeFeedbackPublic,
)
from app.services import ai_service, recipe_feedback_service

router = APIRouter(prefix="/ai", tags=["AI 助手"])


@router.get('/feedback', response_model=list[RecipeFeedbackPublic])
def get_feedback(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return [RecipeFeedbackPublic(recipe_id=r.recipe_id, value='like' if r.rating > 0 else 'dislike', reason=r.reason)
            for r in recipe_feedback_service.list_items(session, user.id)]


@router.put('/feedback/{recipe_id}', response_model=RecipeFeedbackPublic)
def set_feedback(recipe_id: int, payload: RecipeFeedbackRequest,
                 user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return recipe_feedback_service.set_feedback(session, user.id, recipe_id, payload)


@router.post("/chat", response_model=AiChatResponse, summary="AI 对话")
def chat(
    payload: AiChatRequest,
    user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> AiChatResponse:
    return ai_service.chat(session, user.id if user else None, payload)


@router.post(
    "/recommend",
    response_model=AiRecommendResponse,
    summary="AI 配菜：按已选食材 + 今日菜单 + 硬约束推荐",
)
def recommend(
    payload: AiRecommendRequest,
    user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> AiRecommendResponse:
    """导航栏 AI 模块的配菜接口。

    登录可选：
      · 登录了 → 没传 food_ids 时会自动用「我的食材」当输入；
      · 没登录 → 用请求里带的 food_ids，或退回按时令推荐。
    """
    return ai_service.recommend_recipes(session, user.id if user else None, payload)
