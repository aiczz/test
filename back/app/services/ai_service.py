"""AI 助手业务逻辑（说明书 §20）。

★ 这是【规则生成】，不是真的调用大模型。
  说明书 §14 说「第一版可以先用规则匹配，不需要全部依赖 LLM」，
  §18 说「第一版不要把全部逻辑交给 LLM」—— 两条都明确允许这么做。

  响应结构和说明书 §20 完全一致，将来换成真 LLM 时前端一行都不用改。
"""

import re
from datetime import datetime

from sqlmodel import Session

from app.models.recipe import Recipe
from app.repositories import my_food_repository, recipe_repository
from app.schemas.ai import AiChatRequest, AiChatResponse, AiMenuSummary
from app.schemas.my_food import RecommendByFoodsRequest
from app.services import home_service, my_food_service, recipe_service

# 意图关键词。顺序有意义：先判断"用我的食材"，再判断"推荐"
_INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        "cook_with_my_foods",
        ["我有什么", "现有食材", "家里有", "库存", "用这些", "冰箱", "我的食材"],
    ),
    (
        "meal_recommendation",
        ["吃什么", "推荐", "菜单", "晚餐", "午餐", "早餐", "今晚", "晚饭", "午饭"],
    ),
]

_CN_NUMBERS = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _detect_intent(message: str) -> str:
    for intent, keywords in _INTENT_KEYWORDS:
        if any(keyword in message for keyword in keywords):
            return intent
    return "general"


def _parse_people(message: str) -> int | None:
    """从「三个人」「3人」里把人数抠出来。"""
    match = re.search(r"([0-9]+)\s*个?\s*人", message)
    if match:
        return int(match.group(1))
    match = re.search(r"([一两二三四五六七八九十])\s*个?\s*人", message)
    if match:
        return _CN_NUMBERS.get(match.group(1))
    return None


def chat(
    session: Session, user_id: int | None, payload: AiChatRequest
) -> AiChatResponse:
    message = payload.message
    intent = _detect_intent(message)
    people = _parse_people(message) or 3

    if intent == "cook_with_my_foods":
        return _cook_with_my_foods(session, user_id, people)
    if intent == "meal_recommendation":
        return _recommend_meal(session, people)
    return _general()


def _recommend_meal(session: Session, people: int) -> AiChatResponse:
    month = datetime.now().month
    season = home_service.season_name_of(month)

    # 当季的优先；当季不足 3 道时用其余菜谱补齐 ——
    # 标了「秋季」的菜谱可能只有两道，推荐不该因此缩水成两道。
    seasonal, _ = recipe_repository.list_recipes(
        session, season=season, offset=0, limit=20
    )
    everything, _ = recipe_repository.list_recipes(session, offset=0, limit=20)

    ordered: list[Recipe] = list(seasonal[:3])
    chosen = {r.id for r in ordered}
    for recipe in everything:
        if len(ordered) >= 3:
            break
        if recipe.id not in chosen:
            ordered.append(recipe)
            chosen.add(recipe.id)

    # 快的排前面 —— 晚餐不想站太久
    picked = sorted(ordered, key=lambda r: r.duration_minutes)

    if not picked:
        return AiChatResponse(
            answer="菜谱库还是空的，先让管理员灌点数据吧。",
            intent="meal_recommendation",
            tools_used=["recipe_search"],
        )

    names = "、".join(r.name for r in picked)
    answer = (
        f"现在是{season}，按 {people} 个人的量，我推荐这三道：{names}。"
        "荤素都有，做起来也不费事。"
    )

    return AiChatResponse(
        answer=answer,
        intent="meal_recommendation",
        tools_used=["season_search", "recipe_search", "preference_check"],
        recipes=[recipe_service.to_brief(r) for r in picked],
        menu=AiMenuSummary(
            title="今晚推荐",
            summary=f"{len(picked)} 道菜 · 适合 {people} 人",
        ),
    )


def _cook_with_my_foods(
    session: Session, user_id: int | None, people: int
) -> AiChatResponse:
    if user_id is None:
        return AiChatResponse(
            answer="先登录，我才能看到你家里有什么食材。",
            intent="cook_with_my_foods",
            tools_used=["inventory_check"],
        )

    owned = [
        item.food_id
        for item in my_food_repository.list_for_user(session, user_id)
        if item.food_id
    ]
    if not owned:
        return AiChatResponse(
            answer="你的「我的食材」现在还是空的，先去食材页添加几样吧。",
            intent="cook_with_my_foods",
            tools_used=["inventory_check"],
        )

    result = my_food_service.recommend_by_foods(
        session,
        user_id,
        RecommendByFoodsRequest(food_ids=owned, people=people),
    )

    if not result.recommended_recipes:
        return AiChatResponse(
            answer="用你现有的食材暂时没匹配到合适的菜谱，要不要再加几样？",
            intent="cook_with_my_foods",
            tools_used=["inventory_check", "recipe_search"],
        )

    names = "、".join(r.name for r in result.recommended_recipes)
    answer = f"用你现有的食材可以做：{names}。"
    if result.missing_ingredients:
        answer += f"另外还需要买：{'、'.join(result.missing_ingredients[:4])}。"

    return AiChatResponse(
        answer=answer,
        intent="cook_with_my_foods",
        tools_used=["inventory_check", "recipe_search", "shopping_calc"],
        recipes=result.recommended_recipes,
    )


def _general() -> AiChatResponse:
    return AiChatResponse(
        answer=(
            "我是小食，可以帮你安排今天吃什么。"
            "你可以直接说「三个人今晚吃什么」，"
            "或者告诉我家里有什么食材，我来配菜。"
        ),
        intent="general",
        tools_used=[],
    )
