import pytest

from app.ai import client as ai_client
from app.core.config import settings
from app.services import recipe_service


def ask(client, message, previous=None, **options):
    body = {'message': message, 'use_ai': False, 'cook_minutes': 240, **options}
    if previous:
        body.update(conversation_state=previous['conversation_state'], last_intent=previous['intent'])
    response = client.post('/api/ai/chat', json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('question', ['需要什么食材', '这几道菜的配料', '要买什么材料'])
def test_ingredients_come_from_recommended_recipes_not_a_new_food_recommendation(client, session, monkeypatch, question):
    first = ask(client, '推荐三道菜')
    assert len(first['recipes']) == 3
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    monkeypatch.setattr(ai_client, '_network_complete_json', lambda *a, **kw: pytest.fail('A factual follow-up must not call the model'))
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


def test_numbered_recipe_focus_survives_ingredient_and_step_questions(client, session):
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


def test_ordinal_out_of_range_is_clarified_and_new_food_request_still_switches(client):
    first = ask(client, '推荐三道菜')
    result = ask(client, '第九道需要什么食材', first)
    assert result['needs_clarification'] and '3' in result['answer']
    assert result['conversation_state']['recommendation_count'] == 3
    switched = ask(client, '另外推荐一些食材', first)
    assert switched['intent'] == 'recommend_foods' and switched['foods']


@pytest.mark.parametrize('question', ['这些食材能做什么菜', '能做什么菜', '这些可以怎么做'])
def test_food_to_recipe_question_reuses_food_ids_and_constraints(client, session, question):
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


def test_missing_recipe_reference_asks_for_the_dish(client):
    result = ask(client, '需要什么食材')
    assert result['needs_clarification']
    assert not result['foods'] and not result['recipes']


def test_visible_old_conversation_can_supply_recipe_reference(client):
    first = ask(client, '推荐三道菜')
    result = ask(client, '需要什么食材', context_recipe_ids=[r['id'] for r in first['recipes']], context_kind='recipes')
    assert all(r['name'] in result['answer'] for r in first['recipes'])


@pytest.mark.parametrize('message', ['给我展示这些食材便于加入到食材', '把这些配料展示成卡片', '这些加入我的食材', '列出上面的食材'])
def test_ingredient_list_becomes_exact_deduplicated_food_cards(client, session, monkeypatch, message):
    from app.repositories import food_repository
    first = ask(client, '推荐三道菜')
    ingredients = ask(client, '需要什么食材', first)
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    monkeypatch.setattr(ai_client, '_network_complete_json', lambda *a, **kw: pytest.fail('Displaying known ingredients must not invoke AI'))
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
    next_result = ask(client, '这些食材还能做什么菜', cards)
    assert next_result['recipes']


def test_unknown_amounts_and_headers_are_cleaned_without_inventing_food_cards(client, session):
    from app.models.recipe import RecipeIngredient
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


def test_old_ingredient_conversation_and_more_than_twenty_cards_are_supported(client):
    from app.schemas.ai import AiChatRequest
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
