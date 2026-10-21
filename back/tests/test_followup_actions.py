import pytest
from sqlmodel import select

from app.models.my_food import MyFood
from app.models.recipe import Recipe, RecipeIngredient
from app.services import recipe_service


def ask(client, message, previous=None, headers=None):
    body = {'message': message, 'use_ai': False, 'cook_minutes': 240}
    if previous:
        body.update(conversation_state=previous['conversation_state'], last_intent=previous['intent'])
    response = client.post('/api/ai/chat', json=body, headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def test_replace_second_preserves_order_other_recipes_and_constraints(client, session):
    session.add(Recipe(name='蒸鸡蛋', duration_minutes=10, difficulty='简单', tags=['蒸']))
    session.commit()
    first = ask(client, '推荐三道菜，不吃花生')
    result = ask(client, '第二道换成不辣的，其他不变', first)
    before, after = [r['id'] for r in first['recipes']], [r['id'] for r in result['recipes']]
    assert len(after) == len(before) == 3
    assert after[0] == before[0] and after[2] == before[2]
    assert after[1] not in before
    assert '花生' in result['effective_context']['avoid']
    assert '辛辣' in result['effective_context']['avoid']
    assert result['conversation_state']['recommendation_count'] == 3
    details = ask(client, '第二道需要什么食材', result)
    assert details['conversation_state']['focused_recipe_ids'] == [after[1]]


def test_replacement_missing_candidates_keeps_the_original_menu(client):
    first = ask(client, '推荐三道菜')
    first['conversation_state']['cook_minutes'] = 5
    result = ask(client, '第二道换掉，其他不变', first)
    assert [r['id'] for r in result['recipes']] == [r['id'] for r in first['recipes']]
    assert '未替换' in result['answer']


def test_missing_ingredients_requires_real_inventory_and_does_not_become_recommendation(client):
    first = ask(client, '推荐三道菜')
    result = ask(client, '只看缺少的食材', first)
    assert result['needs_clarification']
    assert '登录' in result['answer']
    assert not result['foods'] and not result['recipes']


def test_recipe_detail_never_reports_zero_or_nonfood_group_headers(client, session):
    recipe = session.exec(select(Recipe)).first()
    session.add(RecipeIngredient(recipe_id=recipe.id, ingredient_name='蛋白质类', amount=0, unit='克'))
    session.add(RecipeIngredient(recipe_id=recipe.id, ingredient_name='测试香料', amount=0, unit='克'))
    session.commit()
    detail = recipe_service.get_detail(session, recipe.id)
    assert all(i.name != '蛋白质类' for i in detail.ingredients)
    spice = next(i for i in detail.ingredients if i.name == '测试香料')
    assert spice.amount is None
    assert detail.quality_notes


def test_stock_check_merges_recipes_and_does_not_assume_unknown_units_are_sufficient():
    from types import SimpleNamespace as Obj
    from app.services.ingredient_quality import stock_requirements
    details = [Obj(ingredients=[Obj(name='莲藕', food_id=1, amount='300', unit='克')]),
               Obj(ingredients=[Obj(name='莲藕', food_id=1, amount='0.3', unit='千克'),
                                Obj(name='南瓜', food_id=2, amount='200', unit='克')])]
    stock = [MyFood(user_id=1, food_id=1, amount=0.5, unit='千克'), MyFood(user_id=1, food_id=2, amount=1, unit='份')]
    result = stock_requirements(details, stock)
    assert result[0]['remaining'] == 100 and result[0]['status'] == 'missing'
    assert result[1]['status'] == 'confirm'
    assert stock[0].amount == 0.5


def test_missing_food_cards_exclude_sufficient_stock_and_keep_scope_on_next_display(client, session):
    from app.data.seed import DEMO_USERNAME, DEMO_PASSWORD
    login = client.post('/api/auth/login', json={'username': DEMO_USERNAME, 'password': DEMO_PASSWORD}).json()
    headers = {'Authorization': 'Bearer ' + login['access_token']}
    first = ask(client, '推荐三道菜', headers=headers)
    # Daily ranking can put an unlinked-ingredient recipe first. This test is
    # about inventory coverage across the menu, not the day's first recipe.
    ingredient = next(i for r in first['recipes']
                      for i in recipe_service.get_detail(session, r['id']).ingredients
                      if i.food_id and i.amount)
    client.post('/api/my-foods', headers=headers, json={'food_id': ingredient.food_id, 'amount': 99999, 'unit': ingredient.unit})
    missing = ask(client, '只看缺少的食材', first, headers=headers)
    assert missing['intent'] == 'recommend_foods'
    assert ingredient.food_id not in [f['id'] for f in missing['foods']]
    repeated = ask(client, '展示这些食材', missing, headers=headers)
    assert [f['id'] for f in repeated['foods']] == [f['id'] for f in missing['foods']]
    images = ask(client, '图片呢', repeated, headers=headers)
    assert [f['id'] for f in images['foods']] == [f['id'] for f in missing['foods']]


@pytest.mark.parametrize('message', ['第一道别换，第二道换掉', '不要换第一道，替换第二道'])
def test_replacement_respects_explicitly_preserved_ordinal(client, session, message):
    from app.services.conversation_followup import resolve
    from app.schemas.ai import AiChatRequest, AiConversationState
    first = ask(client, '推荐三道菜')
    ids = [r['id'] for r in first['recipes']]
    followup = resolve(session, AiChatRequest(message=message, conversation_state=AiConversationState(**first['conversation_state'])))
    assert not followup.clarification and followup.ids == [ids[1]]


def test_multiple_replacement_targets_ask_for_clarification(client):
    first = ask(client, '推荐三道菜')
    result = ask(client, '第一道和第二道换掉', first)
    assert result['needs_clarification'] and not result['recipes']


def test_cancelling_mild_food_preference_does_not_reenable_the_exclusion(client):
    first = ask(client, '推荐三道不辣的菜')
    result = ask(client, '取消不辣，换一批菜', first)
    assert '辛辣' not in result['effective_context']['avoid']


def test_quality_audit_is_read_only_and_exposes_missing_source_quantities(session):
    from scripts.audit_recipe_quality import audit
    recipe = session.exec(select(Recipe)).first()
    session.add(RecipeIngredient(recipe_id=recipe.id, ingredient_name='测试香料', amount=0, unit='克'))
    session.commit()
    before = len(session.exec(select(RecipeIngredient)).all())
    result = audit(session)
    assert result['recipes_with_unknown_quantities'] > 0
    assert any(r['invalid_numeric_quantity_count'] > 0 for r in result['review_queue'])
    assert len(session.exec(select(RecipeIngredient)).all()) == before


def test_linked_and_exact_name_ingredients_share_stock_only_once():
    from types import SimpleNamespace as Obj
    from app.services.ingredient_quality import stock_requirements
    details = [Obj(ingredients=[Obj(name='莲藕', food_id=1, amount='300', unit='克'),
                                Obj(name='莲藕', food_id=None, amount='300', unit='克')])]
    result = stock_requirements(details, [MyFood(user_id=1, food_id=1, amount=500, unit='克')], {1: '莲藕'})
    assert len(result) == 1 and result[0]['status'] == 'missing' and result[0]['remaining'] == 100
