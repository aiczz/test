import pytest
from sqlmodel import select

from app.models.my_food import MyFood
from app.models.recipe import Recipe, RecipeIngredient
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


def recipe_detail(kind='ingredients', ordinal=None, *, all=False):
    return understood(
        intent='general', operation='detail', detail_kind=kind,
        reference=recipe_reference(ordinal, all=all),
    )


def ask(client, message, previous=None, headers=None):
    body = {'message': message, 'cook_minutes': 240}
    if previous:
        body.update(conversation_state=previous['conversation_state'], last_intent=previous['intent'])
    response = client.post('/api/ai/chat', json=body, headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def test_replace_second_preserves_order_other_recipes_and_constraints(client, session, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道菜，不吃花生': understood(dish_count=3, avoid_added=['花生']),
        '第二道换成不辣的，其他不变': understood(
            operation='replace', reference=recipe_reference(ordinal=2), avoid_added=['辛辣'],
        ),
        '第二道需要什么食材': recipe_detail(ordinal=2),
    })
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


def test_replacement_missing_candidates_keeps_the_original_menu(client, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '第二道换掉，其他不变': understood(operation='replace', reference=recipe_reference(ordinal=2)),
    })
    first = ask(client, '推荐三道菜')
    first['conversation_state']['cook_minutes'] = 5
    result = ask(client, '第二道换掉，其他不变', first)
    assert [r['id'] for r in result['recipes']] == [r['id'] for r in first['recipes']]
    assert '未替换' in result['answer']


def test_add_appends_to_menu_without_keeping_one_shot_count_or_soup_filter(client, session, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '再补一道汤': understood(
            operation='add', dish_count=1, selection_preferences=['只推荐汤'],
        ),
    })
    first = ask(client, '推荐三道菜')
    soup = Recipe(name='测试紫菜蛋花汤', duration_minutes=15, category='汤羹', tags=['汤羹'])
    session.add(soup)
    session.commit()
    session.refresh(soup)
    session.add(RecipeIngredient(
        recipe_id=soup.id, food_id=6, ingredient_name='鸡蛋', amount=1, unit='个',
    ))
    session.commit()

    result = ask(client, '再补一道汤', first)
    before = [r['id'] for r in first['recipes']]
    added = [r['id'] for r in result['recipes']]
    assert added == [soup.id]
    assert result['requested_count'] == result['returned_count'] == 1
    assert result['conversation_state']['last_recommended_recipe_ids'] == [*before, soup.id]
    assert result['conversation_state']['recommendation_count'] == 3
    assert result['conversation_state']['incremental_count'] is None
    assert result['conversation_state']['selection_preferences'] == []


def test_add_required_food_is_limited_to_the_added_dish(client, session, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '再补一道鸡蛋菜': understood(operation='add', dish_count=1, required_foods=['鸡蛋']),
    })
    first = ask(client, '推荐三道菜')
    recipe = Recipe(name='测试香葱蒸蛋', duration_minutes=15, tags=['清淡', '蒸'])
    session.add(recipe)
    session.commit()
    session.refresh(recipe)
    session.add(RecipeIngredient(
        recipe_id=recipe.id, food_id=6, ingredient_name='鸡蛋', amount=2, unit='个',
    ))
    session.commit()

    result = ask(client, '再补一道鸡蛋菜', first)
    before = [r['id'] for r in first['recipes']]
    added = [r['id'] for r in result['recipes']]
    assert len(added) == 1 and added[0] not in before
    detail = recipe_service.get_detail(session, added[0])
    assert any('鸡蛋' in ingredient.name for ingredient in detail.ingredients)
    assert result['effective_context']['required_foods'] == ['鸡蛋']
    assert result['conversation_state']['required_foods'] is None
    assert result['conversation_state']['last_recommended_recipe_ids'] == [*before, *added]


def test_replace_executes_once_and_does_not_keep_one_shot_selection_conditions(client, session, stub_chat_understanding):
    calls = []
    scenario = {
        '推荐三道菜': understood(dish_count=3),
        '第二道换成清淡的鸡蛋菜': understood(
            operation='replace', reference=recipe_reference(ordinal=2),
            required_foods=['鸡蛋'], selection_preferences=['清淡'],
        ),
    }

    def understand(message, payload):
        calls.append(message)
        return scenario[message]

    stub_chat_understanding(understand)
    first = ask(client, '推荐三道菜')
    recipe = Recipe(name='测试嫩滑蒸蛋', duration_minutes=15, tags=['清淡', '蒸'])
    session.add(recipe)
    session.commit()
    session.refresh(recipe)
    session.add(RecipeIngredient(
        recipe_id=recipe.id, food_id=6, ingredient_name='鸡蛋', amount=2, unit='个',
    ))
    session.commit()

    result = ask(client, '第二道换成清淡的鸡蛋菜', first)
    before = [r['id'] for r in first['recipes']]
    after = [r['id'] for r in result['recipes']]
    assert calls == ['推荐三道菜', '第二道换成清淡的鸡蛋菜']
    assert after == [before[0], recipe.id, before[2]]
    assert result['conversation_state']['recommendation_count'] == 3
    assert result['conversation_state']['incremental_count'] is None
    assert result['effective_context']['required_foods'] == ['鸡蛋']
    assert result['conversation_state']['required_foods'] is None
    assert result['conversation_state']['selection_preferences'] == []


def test_inventory_replacement_preserves_inventory_intent(client, session, stub_chat_understanding):
    from app.data.seed import DEMO_PASSWORD, DEMO_USERNAME

    stub_chat_understanding({
        '用我的食材推荐一道菜': understood(intent='cook_with_my_foods', dish_count=1),
        '这道换一道': understood(
            intent='cook_with_my_foods', operation='replace',
            reference=recipe_reference(ordinal=1),
        ),
    })
    login = client.post('/api/auth/login', json={
        'username': DEMO_USERNAME, 'password': DEMO_PASSWORD,
    }).json()
    headers = {'Authorization': 'Bearer ' + login['access_token']}
    client.post('/api/my-foods', headers=headers, json={'food_id': 1, 'amount': 2, 'unit': '节'})
    recipe = Recipe(name='测试清炒莲藕', duration_minutes=15, tags=['清淡'])
    session.add(recipe)
    session.commit()
    session.refresh(recipe)
    session.add(RecipeIngredient(
        recipe_id=recipe.id, food_id=1, ingredient_name='莲藕', amount=1, unit='节',
    ))
    session.commit()

    first = ask(client, '用我的食材推荐一道菜', headers=headers)
    result = ask(client, '这道换一道', first, headers=headers)
    assert first['intent'] == result['intent'] == 'cook_with_my_foods'
    assert result['conversation_state']['last_intent'] == 'cook_with_my_foods'
    assert len(result['recipes']) == 1
    assert result['recipes'][0]['id'] != first['recipes'][0]['id']


def test_missing_ingredients_requires_real_inventory_and_does_not_become_recommendation(client, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '只看缺少的食材': recipe_detail(kind='missing_ingredients', all=True),
    })
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


def test_missing_food_cards_exclude_sufficient_stock_and_keep_scope_on_next_display(client, session, stub_chat_understanding):
    from app.data.seed import DEMO_USERNAME, DEMO_PASSWORD
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '只看缺少的食材': recipe_detail(kind='missing_ingredients', all=True),
        '展示这些食材': recipe_detail(kind='ingredient_cards'),
        '图片呢': recipe_detail(kind='ingredient_cards'),
    })
    login = client.post('/api/auth/login', json={'username': DEMO_USERNAME, 'password': DEMO_PASSWORD}).json()
    headers = {'Authorization': 'Bearer ' + login['access_token']}
    first = ask(client, '推荐三道菜', headers=headers)
    # 本测试验证整餐库存覆盖，不依赖当天第一道是什么。
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
def test_replacement_respects_explicitly_preserved_ordinal(client, session, stub_chat_understanding, message):
    from app.services.conversation_followup import resolve_structured
    from app.schemas.ai import AiConversationState
    stub_chat_understanding(understood(dish_count=3))
    first = ask(client, '推荐三道菜')
    ids = [r['id'] for r in first['recipes']]
    followup = resolve_structured(
        session,
        AiConversationState(**first['conversation_state']),
        understood(operation='replace', reference=recipe_reference(ordinal=2)),
    )
    assert not followup.clarification and followup.ids == [ids[1]]


def test_multiple_replacement_targets_ask_for_clarification(client, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道菜': understood(dish_count=3),
        '第一道和第二道换掉': understood(operation='replace', reference=recipe_reference(all=True)),
    })
    first = ask(client, '推荐三道菜')
    result = ask(client, '第一道和第二道换掉', first)
    assert result['needs_clarification'] and not result['recipes']


def test_cancelling_mild_food_preference_does_not_reenable_the_exclusion(client, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道不辣的菜': understood(dish_count=3, avoid_added=['辛辣']),
        '取消不辣，换一批菜': understood(operation='repeat', avoid_removed=['辛辣']),
    })
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
