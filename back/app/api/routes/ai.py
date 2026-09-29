"""AI 助手接口（说明书 §20）。

POST /api/ai/chat

登录是【可选】的：没登录也能聊，只是问到「用我的食材」这类需要库存的问题时，
会提示先登录。

⚠️ 当前实现是规则生成，不是真的调用大模型（说明书 §14/§18 明确允许）。
   响应结构与说明书一致，将来换成真 LLM 时前端不用改。
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.dependencies import get_current_user_optional
from app.models.user import User
from app.schemas.ai import AiChatRequest, AiChatResponse
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["AI 助手"])


@router.post("/chat", response_model=AiChatResponse, summary="AI 对话")
def chat(
    payload: AiChatRequest,
    user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> AiChatResponse:
    return ai_service.chat(session, user.id if user else None, payload)
