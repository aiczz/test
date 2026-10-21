"""Explicit ingredient restrictions outrank quantity and meal variety."""
import pytest

from app.models.recipe import Recipe, RecipeIngredient
from app.schemas.ai import AiChatRequest, AiConversationState, AiRecommendRequest
from app.services import ai_service, chat_context
from app.services import required_ingredients, scoring_service
from app.ai import client as ai_client
from app.core.config import settings


@pytest.fixture
def fish_catalog(session):
    ids = {}
    for name, ingredients in [
        ('清蒸鲈鱼', ['鲈鱼', '姜']),
        ('番茄鳕鱼豆腐锅', ['鳕鱼', '豆腐', '番茄']),
        ('鱼香茄子', ['茄子', '猪肉']),
        ('鱼露拌黄瓜', ['黄瓜', '鱼露']),
        ('牛肉鱼片锅', ['牛肉', '鱼片']),
        ('蒜香鱿鱼', ['鱿鱼', '蒜']),
        ('清炒鸡腿菇', ['鸡腿菇']),
        ('清蒸鸡肉', ['鸡胸肉', '姜']),
    ]:
        row = Recipe(name=name, duration_minutes=15)
        session.add(row)
        session.flush()
        ids[name] = row.id
        for ingredient in ingredients:
            session.add(RecipeIngredient(recipe_id=row.id, ingredient_name=ingredient))
    session.commit()
    return ids


def ask(session, message, previous=None, **kwargs):
    return ai_service.chat(session, None, AiChatRequest(
        message=message, use_ai=False, cook_minutes=240,
        conversation_state=previous.conversation_state if previous else None,
        last_intent=previous.intent if previous else None, **kwargs))


def test_only_fish_persists_without_filling_with_other_meats(session, fish_catalog):
    first = ask(session, '推荐8道菜')
    result = ask(session, '只要鱼', first)
    expected = {fish_catalog['清蒸鲈鱼'], fish_catalog['番茄鳕鱼豆腐锅']}
    assert {r.id for r in result.recipes} == expected
    assert result.requested_count == 8
    assert result.conversation_state.required_foods == ['鱼']
    assert result.effective_context.required_foods == ['鱼']
    assert '只找到 2 道' in result.answer
    again = ask(session, '换一批', result)
    assert all(r.id in expected for r in again.recipes)
    assert again.conversation_state.required_foods == ['鱼']


@pytest.mark.parametrize('mode', ['chat', 'compose'])
def test_restriction_applies_to_both_entrypoints(session, fish_catalog, mode):
    if mode == 'chat':
        result = ask(session, '只推荐鸡肉，推荐5道菜')
        recipes = result.recipes
    else:
        result = ai_service.recommend_recipes(session, None, AiRecommendRequest(
            message='只推荐鸡肉', count=5, cook_minutes=240))
        recipes = [r.recipe for r in result.recommendations]
    assert fish_catalog['清蒸鸡肉'] in {r.id for r in recipes}
    assert all('鸡' in r.name and '菇' not in r.name.replace('香菇', '') for r in recipes)


def test_cancel_and_replace_required_foods_preserve_other_conditions(session, fish_catalog):
    first = ask(session, '推荐8道菜，只要鱼，不吃花生')
    chicken = ask(session, '只要鸡肉', first)
    assert chicken.conversation_state.required_foods == ['鸡肉']
    assert fish_catalog['清蒸鸡肉'] in {r.id for r in chicken.recipes}
    assert all('鸡' in r.name and r.name != '清炒鸡腿菇' for r in chicken.recipes)
    cancelled = ask(session, '取消食材限制', chicken)
    assert cancelled.conversation_state.required_foods == []
    assert cancelled.requested_count == 8
    assert '花生' in cancelled.effective_context.avoid
    assert len(cancelled.recipes) > 1


def test_no_matching_ingredient_does_not_relax_to_unrelated_foods(session):
    result = ask(session, '只要鳗鱼，推荐8道菜')
    assert not result.recipes


@pytest.mark.parametrize('message', ['只要鱼是什么意思', '不要只推荐鱼', '不只要鱼', '只要两个', '只要三道菜', '只推荐汤', '只要素菜', '只要不辣'])
def test_negated_or_explanatory_phrases_are_not_positive_filters(message):
    state = chat_context.edits(message, AiConversationState(), ['鱼'])
    assert not state.required_foods


def test_switch_and_exclude_ingredient_in_same_conversation(session, fish_catalog):
    first = ask(session, '只要鱼')
    chicken = ask(session, '换成鸡肉，不要鱼', first)
    assert chicken.conversation_state.required_foods == ['鸡肉']
    assert '鱼' in chicken.effective_context.avoid
    assert fish_catalog['清蒸鸡肉'] in {r.id for r in chicken.recipes}
    assert all('鱼' not in r.name for r in chicken.recipes)


def test_explicit_empty_request_overrides_persisted_restriction(session, fish_catalog):
    state = AiConversationState(required_foods=[], recommendation_count=8)
    result = ai_service.chat(session, None, AiChatRequest(message='换一批', use_ai=False,
        last_intent='meal_recommendation', required_foods=['鱼'], conversation_state=state))
    assert not result.effective_context.required_foods
    assert len(result.recipes) > 2


@pytest.mark.parametrize('mode', ['chat', 'compose'])
@pytest.mark.parametrize('invalid', [False, True])
def test_model_pool_and_invalid_selection_cannot_reintroduce_other_meats(session, fish_catalog, monkeypatch, mode, invalid):
    import re
    expected = {fish_catalog['清蒸鲈鱼'], fish_catalog['番茄鳕鱼豆腐锅']}
    calls = []
    def network(messages, **kwargs):
        prompt = messages[-1]['content']
        pool = set(map(int, re.findall(r'^(\d+) \|', prompt, re.M)))
        assert pool == expected
        assert '限定食材 鱼' in prompt
        calls.append(pool)
        picks = [fish_catalog['牛肉鱼片锅']] if invalid else list(pool)
        return ai_client.AiResult(ok=True, model='test', data={
            'answer': '其他几道是牛肉和鸡肉补充',
            'picks': [{'id': i, 'reason': '牛肉补充'} for i in picks]})
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    if mode == 'chat':
        result = ai_service.chat(session, None, AiChatRequest(message='只要鱼，推荐8道菜', use_ai=True, cook_minutes=240))
        recipes = result.recipes
    else:
        result = ai_service.recommend_recipes(session, None, AiRecommendRequest(message='只要鱼', count=6, cook_minutes=240))
        recipes = [r.recipe for r in result.recommendations]
    assert {r.id for r in recipes} == expected
    assert len(calls) == 1
    assert '牛肉' not in result.answer
    assert result.source == ('algorithm' if invalid else 'ai')
    assert all('牛肉补充' not in (r.description or '') for r in recipes)


def test_strict_recall_does_not_depend_on_seasonal_shortlist(session, fish_catalog, monkeypatch):
    monkeypatch.setattr(scoring_service, '_dish_candidate_ids',
                        lambda *a, **kw: pytest.fail('Strict ingredient recall must precede seasonal truncation'))
    result = ask(session, '只要鱼，推荐8道菜')
    assert {r.id for r in result.recipes} == {fish_catalog['清蒸鲈鱼'], fish_catalog['番茄鳕鱼豆腐锅']}


@pytest.mark.parametrize('names,required,expected', [
    (['鲈鱼', '豆腐'], ['鱼'], True),
    (['鱼香茄子', '猪肉'], ['鱼'], False),
    (['鱼露', '黄瓜'], ['鱼'], False),
    (['鲍鱼'], ['鱼'], False),
    (['鱿鱼'], ['鱼'], False),
    (['鳕鱼', '牛肉'], ['鱼'], False),
    (['鳕鱼', '虾仁'], ['鱼'], False),
    (['鳕鱼', '蟹肉'], ['鱼'], False),
    (['鸡爪', '螃蟹'], ['鸡肉'], False),
    (['鸡肉', '鲍鱼'], ['鸡肉'], False),
    (['鸡肉', '肉类'], ['鸡肉'], False),
    (['鸡翅', '万威克黑椒肠', '亚太鱼豆腐'], ['鸡肉'], False),
    (['鸡肉', '肠粉'], ['鸡肉'], True),
    (['鱼片', '干贝'], ['鱼'], False),
    (['鱼片', '鱿鱼'], ['鱼'], False),
    (['鱼片', '鸡精'], ['鱼'], True),
    (['鸡腿菇', '鸡蛋'], ['鸡肉'], False),
    (['鸡胸肉'], ['鸡肉'], True),
    (['牛奶', '牛油果'], ['牛肉'], False),
    (['羊肚菌'], ['羊肉'], False),
    (['鱼片', '鸡肉'], ['鱼', '鸡肉'], True),
    ([], ['鱼'], False),
])
def test_ingredient_evidence_and_animal_lookalikes(names, required, expected):
    assert required_ingredients.matches(names, required) == expected


def test_conflicting_avoid_and_requirement_never_relaxes(session, fish_catalog):
    result = ask(session, '只要鱼，不吃鱼')
    assert not result.recipes
    assert '鱼' in result.effective_context.avoid
    assert result.effective_context.required_foods == ['鱼']


def test_inclusion_cancellation_does_not_cancel_independent_avoid():
    state = AiConversationState(required_foods=['鱼'], avoid_added=['鱼', '花生'])
    changed = chat_context.edits('取消只要鱼', state, ['鱼', '花生'])
    assert changed.required_foods == []
    assert changed.avoid_added == ['鱼', '花生']
    assert not changed.avoid_removed


@pytest.mark.parametrize('message,expected', [
    ('只要白菜', ['白菜']), ('只要油麦菜', ['油麦菜']),
    ('只要鱼的菜谱', ['鱼']), ('只要鱼菜', ['鱼']),
    ('只要鱼的就行', ['鱼']), ('只要三文鱼', ['三文鱼']), ('只要四季豆', ['四季豆']),
    ('全部换成鸡肉', ['鸡肉']), ('只要鱼和鸡肉', ['鱼', '鸡肉']),
])
def test_food_names_keep_their_last_character(message, expected):
    assert required_ingredients.edit(message, None, ['白菜', '油麦菜', '三文鱼', '四季豆']) == expected


def test_new_filter_can_keep_matching_previously_shown_dishes(session, fish_catalog):
    first = ask(session, '推荐8道菜')
    # The app sends all recently shown IDs, including fish the user wants to keep.
    first.conversation_state.last_recommended_recipe_ids = list(fish_catalog.values())
    result = ask(session, '只要鱼', first, recent_recipe_ids=list(fish_catalog.values()))
    assert {r.id for r in result.recipes} == {fish_catalog['清蒸鲈鱼'], fish_catalog['番茄鳕鱼豆腐锅']}
    again = ask(session, '换一批', result, recent_recipe_ids=[r.id for r in result.recipes])
    assert not again.recipes  # Exhaustion is honest; no beef or chicken fallback.


def test_restriction_keeps_explicit_new_food_or_recipe_target(session, fish_catalog):
    from app.models.food import Food
    session.add(Food(name='鲈鱼', category='aquatic'))
    session.commit()
    recipes = ask(session, '推荐8道菜')
    foods = ask(session, '推荐食材，只要鱼', recipes)
    assert foods.intent == 'recommend_foods'
    assert [f.name for f in foods.foods] == ['鲈鱼']
    back = ask(session, '推荐菜谱，只要鱼', foods)
    assert back.intent == 'meal_recommendation'
    assert {r.id for r in back.recipes} == {fish_catalog['清蒸鲈鱼'], fish_catalog['番茄鳕鱼豆腐锅']}
