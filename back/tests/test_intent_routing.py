"""意图路由的测试。

分两层，都要有：

  · **语义层**（`_route_semantic`）：按意思判，中文怎么说都能认。
    它依赖大模型，所以测试只验证「不可用时干净地退回规则」，
    不验证判断质量（那要靠 `scripts/check_ai.py` 那样真的调一次）。

  · **规则层**（`_route`）：关键词匹配。它不是"判得准"，而是
    **没配 AI 时助手不能变哑巴**的保证。所以它的行为要一条条钉住。

⚠️ 用户提的核心意见是「中文表达方式很多，应该按语义判断」。
   这一层的存在本身就是那个需求的产物；而规则层的每一条测试，
   都是「模型不可用时退化到哪」的说明书。
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import ai_service, need_service


@pytest.fixture(autouse=True)
def _no_ai(monkeypatch):
    """这一组全在「没配 AI」的前提下跑 —— 也就是离线部署的样子。"""
    monkeypatch.setattr(settings, "ai_api_key", "")
    monkeypatch.setattr(settings, "ai_enabled", True, raising=False)
    yield


# (用户说的一句话, 期望意图)
ROUTING_CASES = [
    # ---- 想要「食材」而不是「菜」----
    ("推荐点食材", "recommend_foods"),
    ("该买什么菜", "recommend_foods"),
    ("想补钙，吃点什么好", "recommend_foods"),
    ("补铁的食物有哪些", "recommend_foods"),
    # ---- 用我自己的库存做菜 ----
    ("用我家的食材做菜", "cook_with_my_foods"),
    ("冰箱里有什么能做的", "cook_with_my_foods"),
    # ---- 想知道吃什么菜 ----
    ("今晚吃什么", "meal_recommendation"),
    ("莲藕怎么做", "meal_recommendation"),
    ("我气血不足，想吃点补气血的", "meal_recommendation"),
    ("我不吃香菜", "meal_recommendation"),
    ("换一批呢", "meal_recommendation"),
    # ---- 闲聊 ----
    ("你好", "general"),
]


@pytest.mark.parametrize(("message", "expected"), ROUTING_CASES)
def test_keyword_router_offline(session, message, expected):
    route = ai_service._route(session=session, message=message, payload=None)
    assert route.intent == expected, f"「{message}」被判成了 {route.intent}"
    assert route.source == "rules", "规则层的结论必须标成 rules"


def test_wanting_food_beats_wanting_a_dish(session):
    """「用我的食材」是要做饭，不是要采购建议 —— 顺序不能反。

    这两句都含「食材」，但意图完全相反：
        「用我的食材做菜」→ cook_with_my_foods（做出菜来）
        「推荐点食材」    → recommend_foods（买/吃什么）
    所以 cook_with_my_foods 必须排在前面。
    """
    mine = ai_service._route(session=session, message="用我的食材做菜", payload=None)
    want = ai_service._route(session=session, message="推荐点食材", payload=None)
    assert mine.intent == "cook_with_my_foods"
    assert want.intent == "recommend_foods"


def test_semantic_router_returns_none_when_ai_unavailable(session):
    """没配 AI 时语义层必须返回 None（**不能**抛异常、也不能瞎猜一个意图）。"""
    assert ai_service._route_semantic(
        session=session, message="家里有健身的", payload=None
    ) is None


def test_smart_router_falls_back_to_rules(session):
    """`_route_smart` 在语义层不可用时，结论必须和规则层一致。"""
    for message, expected in ROUTING_CASES:
        route = ai_service._route_smart(session=session, message=message, payload=None)
        assert route.intent == expected
        assert route.source == "rules"


def test_follow_up_inherits_last_intent(session):
    """「换一批」要沿用上一轮意图，否则会掉进闲聊、卡片全没了。"""

    class Payload:
        last_intent = "recommend_foods"

    route = ai_service._route(
        session=session, message="换一批呢", payload=Payload()
    )
    assert route.intent == "recommend_foods", "追问要继承上一轮，而不是硬判成推荐菜"
    assert route.follow_up is True


def test_declared_avoid_is_extracted_and_not_used_as_recall_basis(session):
    """「我不吃鸡蛋」：既要把鸡蛋加进忌口，又**不能**拿鸡蛋去召回。"""
    route = ai_service._route(session=session, message="我不吃鸡蛋", payload=None)
    assert "鸡蛋" in route.avoid_added
    assert "鸡蛋" not in route.mentioned_names
    assert route.mentioned_ids == []


# =====================================================================
# 提示词构造函数 —— 必须**直接测**
#
# ★ 这一组是被真事故逼出来的：
#   `_classify_prompt` 里写了 `need_service.HEALTH_GOALS`，而那个属性不存在
#   （真名是 `all_goals()`）。测试全绿 —— 因为测试环境**故意关掉了 AI**
#   （免得 pytest 真去烧 token），提示词压根不会被组装，
#   接口测试也覆盖不到。只有线上配了 key 的实例一调就 500。
#
#   教训：凡是「只在 AI 开着时才执行」的代码，都得绕开开关直接测。
#   提示词构造函数恰好是纯函数，直接调最省事。
# =====================================================================


def test_classify_prompt_is_buildable():
    """意图分类的提示词要能拼出来，且把四个意图和全部诉求名都列进去。

    模型得知道有哪些选项才能选对 —— 少列一个意图，它就永远不会返回那个意图。
    """
    prompt = ai_service._classify_prompt("家里有健身的", "meal_recommendation")
    for intent in ("meal_recommendation", "recommend_foods",
                   "cook_with_my_foods", "general"):
        assert intent in prompt, f"提示词里没告诉模型有 {intent} 这个意图"
    # 诉求名要全列出来（模型只能从中选，不能自己造）
    for goal in need_service.all_goals():
        assert goal.name in prompt, f"提示词里漏了诉求「{goal.name}」"
    assert "家里有健身的" in prompt
    assert "上一轮意图" in prompt, "带了上下文时要把上一轮意图写进去"


def test_classify_prompt_without_context():
    """没有上一轮上下文时也不能出错（不能留个空括号给模型猜）。"""
    prompt = ai_service._classify_prompt("你好", None)
    assert "上一轮意图" not in prompt
    assert "你好" in prompt


def test_food_prompt_is_buildable(session):
    """推荐食材的提示词要能拼出来 —— 同上，它只在 AI 开着时才执行。"""
    from app.schemas.ai import AiChatRequest
    from app.services.ai_service import _constraints, _weather_for
    from app.services.scoring_service import HardConstraints, ScoredItem

    payload = AiChatRequest(message="想补点钙", city="杭州")
    constraints = HardConstraints(people=3, cook_minutes=45)
    candidates = [
        ScoredItem(raw=None, item_id=1, name="牛奶", score=1.0, reason="",
                   factors={"season": 80.0}, insight=None, highlights=[],
                   quality=1.0, band=80.0),
    ]
    prompt = ai_service._food_prompt(
        session=session,
        payload=payload,
        constraints=constraints,
        weather=_weather_for(payload, 10),
        month=10,
        candidates=candidates,
        health_goal=need_service.extract_goal("想补钙"),
        count=3,
    )
    assert "候选食材" in prompt
    assert "牛奶" in prompt
    assert "只能从这里挑" in prompt
    # 有诉求时必须把诉求那句话说给模型听
    assert "核心诉求" in prompt
    assert _constraints is not None  # 顺手确认那个私有 helper 还是可用的


def test_food_candidate_lines_format():
    """候选清单的格式要能被模型读懂：id 在第一个字段。"""
    from app.services.scoring_service import ScoredItem

    item = ScoredItem(raw=None, item_id=42, name="鸡胸肉", score=1.0, reason="",
                      factors={"season": 70.0}, insight=None, highlights=[],
                      quality=1.0, band=70.0)
    lines = ai_service._food_candidate_lines(None, [item])
    assert len(lines) == 1
    assert lines[0].startswith("42 | 鸡胸肉")
