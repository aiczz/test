import pytest

from app.ai import client as ai_client
from app.core.config import settings
from app.schemas.ai import AiReference, AiUnderstanding, AiUnderstandingSlots
from app.services import recipe_service


def understood(intent='meal_recommendation', operation='new', *, reference=None, detail_kind=None, **slots):
    return AiUnderstanding(
        intent=intent,
        operation=operation,
        confidence=0.97,
        slots=AiUnderstandingSlots(**slots),
        reference=reference,
        detail_kind=detail_kind,
    )


def recipe_reference(ordinal=None, *, all=False):
    return AiReference(kind='recipe', ordinal=ordinal, all=all)


def food_reference(ordinal=None, *, all=False):
    return AiReference(kind='food', ordinal=ordinal, all=all)


def recipe_detail(kind='ingredients', ordinal=None, *, all=False):
    return understood(
        intent='general', operation='detail', detail_kind=kind,
        reference=recipe_reference(ordinal, all=all),
    )


def ask(client, message, previous=None, **options):
    body = {'message': message, 'cook_minutes': 240, **options}
    if previous:
        body.update(conversation_state=previous['conversation_state'], last_intent=previous['intent'])
    response = client.post('/api/ai/chat', json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('question', ['需要什么食材', '这几道菜的配料', '要买什么材料'])
def test_ingredients_come_from_recommended_recipes_not_a_new_food_recommendation(
    client, session, monkeypatch, stub_chat_understanding, question,
):
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        question: recipe_detail(all=True),
    })
    first = ask(client, '推荐三道菜')
    assert len(first['recipes']) == 3
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    monkeypatch.setattr(ai_client, '_network_complete_json', lambda *a, **kw: pytest.fail('事实追问不得二次生成'))
    result = ask(client, question, first, use_ai=True)
    assert result['intent'] == 'general'
    assert not result['foods'] and not result['recipes']
    for recipe in first['recipes']:
        detail = recipe_service.get_detail(session, recipe['id'])
        assert detail.name in result['answer']
        for ingredient in detail.ingredients:
            assert ingredient.name in result['answer']
    assert result['conversation_state']['last_recommended_recipe_ids'] == [r['id'] for r in first['recipes']]
    assert '库存' in result['answer']


def test_numbered_recipe_focus_survives_ingredient_and_step_questions(client, session, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '需要什么食材': recipe_detail(all=True),
        '第二道的配料': recipe_detail(ordinal=2),
        '怎么做': understood(
            intent='general', operation='detail', detail_kind='steps', reference=recipe_reference(),
        ),
    })
    first = ask(client, '推荐三道菜')
    second = ask(client, '需要什么食材', first)
    third = ask(client, '第二道的配料', second)
    target = first['recipes'][1]['id']
    assert third['conversation_state']['focused_recipe_ids'] == [target]
    assert third['conversation_state']['recommendation_count'] == 3
    fourth = ask(client, '怎么做', third)
    detail = recipe_service.get_detail(session, target)
    assert detail.name in fourth['answer']
    for step in detail.steps:
        assert step.description in fourth['answer']
    assert not fourth['recipes'] and not fourth['foods']


def test_ordinal_out_of_range_is_clarified_and_new_food_request_still_switches(client, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '第九道需要什么食材': recipe_detail(ordinal=9),
        '另外推荐一些食材': understood(intent='recommend_foods'),
    })
    first = ask(client, '推荐三道菜')
    result = ask(client, '第九道需要什么食材', first)
    assert result['needs_clarification'] and '3' in result['answer']
    assert result['conversation_state']['recommendation_count'] == 3
    switched = ask(client, '另外推荐一些食材', first)
    assert switched['intent'] == 'recommend_foods' and switched['foods']


@pytest.mark.parametrize('question', ['这些食材能做什么菜', '能做什么菜', '这些可以怎么做'])
def test_food_to_recipe_question_reuses_food_ids_and_constraints(client, session, stub_chat_understanding, question):
    stub_chat_understanding({
        '推荐一些食材，不吃花生': understood(intent='recommend_foods', avoid_added=['花生']),
        question: understood(
            operation='detail', detail_kind='food_recipes', reference=food_reference(all=True),
        ),
        '需要什么食材': recipe_detail(all=True),
    })
    first = ask(client, '推荐一些食材，不吃花生')
    result = ask(client, question, first)
    assert result['intent'] == 'meal_recommendation' and result['recipes']
    selected = {f['id'] for f in first['foods']}
    for recipe in result['recipes']:
        detail = recipe_service.get_detail(session, recipe['id'])
        assert selected.intersection(i.food_id for i in detail.ingredients)
    assert '花生' in result['effective_context']['avoid']
    ingredients = ask(client, '需要什么食材', result)
    assert all(r['name'] in ingredients['answer'] for r in result['recipes'])
    assert not ingredients['foods']


def test_missing_recipe_reference_asks_for_the_dish(client, stub_chat_understanding):
    stub_chat_understanding(recipe_detail(all=True))
    result = ask(client, '需要什么食材')
    assert result['needs_clarification']
    assert not result['foods'] and not result['recipes']


def test_visible_old_conversation_can_supply_recipe_reference(client, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '需要什么食材': recipe_detail(all=True),
    })
    first = ask(client, '推荐三道菜')
    result = ask(client, '需要什么食材', context_recipe_ids=[r['id'] for r in first['recipes']], context_kind='recipes')
    assert all(r['name'] in result['answer'] for r in first['recipes'])


@pytest.mark.parametrize('message', ['给我展示这些食材便于加入到食材', '把这些配料展示成卡片', '这些加入我的食材', '列出上面的食材'])
def test_ingredient_list_becomes_exact_deduplicated_food_cards(
    client, session, monkeypatch, stub_chat_understanding, message,
):
    from app.repositories import food_repository
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '需要什么食材': recipe_detail(all=True),
        message: recipe_detail(kind='ingredient_cards'),
        '这些食材还能做什么菜': understood(
            operation='detail', detail_kind='food_recipes', reference=food_reference(all=True),
        ),
    })
    first = ask(client, '推荐三道菜')
    ingredients = ask(client, '需要什么食材', first)
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    monkeypatch.setattr(ai_client, '_network_complete_json', lambda *a, **kw: pytest.fail('展示已知配料不得二次生成'))
    cards = ask(client, message, ingredients, use_ai=True)
    expected = {i.food_id for r in first['recipes'] for i in recipe_service.get_detail(session, r['id']).ingredients
                if i.food_id is not None and food_repository.get(session, i.food_id) is not None}
    actual = [f['id'] for f in cards['foods']]
    assert set(actual) == expected and len(actual) == len(set(actual))
    assert cards['intent'] == 'recommend_foods'
    assert cards['returned_count'] == len(actual)
    assert cards['requested_count'] is None
    assert cards['conversation_state']['last_recommended_recipe_ids'] == [r['id'] for r in first['recipes']]
    assert cards['conversation_state']['active_topic'] == 'recipe_ingredients'
    assert '尚未替你添加库存' in cards['answer']
    # “禁止二次生成”只约束配料卡片事实工具；后续菜谱推荐是另一条链路。
    monkeypatch.setattr(settings, 'ai_enabled', False)
    next_result = ask(client, '这些食材还能做什么菜', cards)
    assert next_result['recipes']


def test_unknown_amounts_and_headers_are_cleaned_without_inventing_food_cards(client, session, stub_chat_understanding):
    from app.models.recipe import RecipeIngredient
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '第一道需要什么食材': recipe_detail(ordinal=1),
        '展示这些食材': recipe_detail(kind='ingredient_cards'),
    })
    first = ask(client, '推荐三道菜')
    target = first['recipes'][0]['id']
    session.add(RecipeIngredient(recipe_id=target, ingredient_name='测试未建档的香料', amount=0, unit='克'))
    session.add(RecipeIngredient(recipe_id=target, ingredient_name='蛋白质类', amount=0, unit='克'))
    session.commit()
    ingredients = ask(client, '第一道需要什么食材', first)
    assert '测试未建档的香料' in ingredients['answer']
    assert '用量未注明' in ingredients['answer']
    assert '（0克）' not in ingredients['answer'] and '蛋白质类' not in ingredients['answer']
    cards = ask(client, '展示这些食材', ingredients)
    assert '测试未建档的香料' in cards['answer']
    assert all(f['name'] != '测试未建档的香料' for f in cards['foods'])
    assert cards['conversation_state']['ingredient_recipe_ids'] == [target]


def test_old_ingredient_conversation_and_more_than_twenty_cards_are_supported(client, stub_chat_understanding):
    from app.schemas.ai import AiChatRequest
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '需要什么食材': recipe_detail(all=True),
        '展示这些食材': recipe_detail(kind='ingredient_cards', all=True),
    })
    first = ask(client, '推荐三道菜')
    ingredients = ask(client, '需要什么食材', first)
    old_state = ingredients['conversation_state']
    old_state.pop('active_topic')
    old_state.pop('ingredient_recipe_ids')
    result = ask(client, '展示这些食材', {'intent': 'general', 'conversation_state': old_state})
    assert result['foods']
    request = AiChatRequest(message='这些能做什么菜', context_food_ids=list(range(1, 42)), conversation_state={
        'last_recommended_food_ids': list(range(1, 42)), 'focused_food_ids': list(range(1, 42))})
    assert len(request.context_food_ids) == 41


@pytest.mark.parametrize('message', ['图片呢', '给我看看图片', '有图吗', '这些食材的图片', '能预览这些食材吗'])
def test_short_image_followup_displays_the_focused_ingredients_without_model(
    client, session, monkeypatch, stub_chat_understanding, message,
):
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '第二道需要什么食材': recipe_detail(ordinal=2),
        message: recipe_detail(kind='ingredient_cards'),
    })
    first = ask(client, '推荐三道菜')
    ingredients = ask(client, '第二道需要什么食材', first)
    target = first['recipes'][1]['id']
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    monkeypatch.setattr(ai_client, '_network_complete_json', lambda *a, **kw: pytest.fail('食材图片预览不得二次生成'))
    cards = ask(client, message, ingredients, use_ai=True)
    assert cards['intent'] == 'recommend_foods' and cards['foods']
    assert not cards['recipes']
    detail = recipe_service.get_detail(session, target)
    names = {i.name for i in detail.ingredients}
    assert all(f['name'] in names for f in cards['foods'])
    assert cards['conversation_state']['ingredient_recipe_ids'] == [target]


def test_image_question_without_a_reference_asks_which_content(client, stub_chat_understanding):
    stub_chat_understanding(recipe_detail(kind='ingredient_cards'))
    result = ask(client, '图片呢')
    assert result['needs_clarification'] and not result['foods'] and not result['recipes']


@pytest.mark.parametrize('message,intent', [
    ('怎么生成图片', 'general'), ('为什么图片打不开', 'general'), ('另外推荐一些食材', 'recommend_foods'),
])
def test_unrelated_image_questions_or_new_requests_do_not_reuse_ingredient_cards(session, message, intent):
    from app.schemas.ai import AiConversationState
    from app.services.conversation_followup import resolve_structured
    state = AiConversationState(
        last_recommended_recipe_ids=[1], focused_recipe_ids=[1],
        active_topic='recipe_ingredients', ingredient_recipe_ids=[1],
    )
    result = resolve_structured(session, state, understood(intent=intent))
    assert result is None
