from types import SimpleNamespace

import pytest

from app.services import meal_selection
from app.services.scoring_service import ScoredItem


def dish(i, name, ingredients, tags=()):
    return ScoredItem(raw=SimpleNamespace(tags=list(tags)), item_id=i, name=name, score=5, quality=5, reason='',
        insight=SimpleNamespace(all_ingredient_names=ingredients, main_ingredients=ingredients,
            tags=list(tags), ingredient_ids=[], duration_minutes=20, duration_source='table'))


@pytest.mark.parametrize('name,ingredients,vegetable,protein,plant', [
    ('鱼香茄子', ['茄子', '蒜', '油'], True, '', True),
    ('番茄炒蛋', ['番茄', '鸡蛋'], True, '蛋类', False),
    ('西兰花炒鸡胸', ['西兰花', '鸡胸肉'], True, '鸡肉', False),
    ('蚝油生菜', ['生菜', '蚝油'], True, '', False),
    ('蒸豆腐', ['豆腐'], False, '豆类', True),
    ('肉末茄子', ['猪肉末', '茄子'], True, '猪肉', False),
    ('清炒鸡腿菇', ['鸡腿菇'], True, '', True),
])
def test_classification_uses_ingredients_and_recognizes_mixed_dishes(name, ingredients, vegetable, protein, plant):
    f = meal_selection.features(dish(1, name, ingredients))
    assert (f.vegetable, f.protein, f.plant_only) == (vegetable, protein, plant)


def test_repair_changes_only_the_extra_soup_and_keeps_safe_ids():
    pool = [dish(1, '排骨汤', ['排骨'], ['汤']), dish(2, '鸡肉汤', ['鸡肉'], ['汤']),
            dish(3, '清炒菠菜', ['菠菜']), dish(4, '蒸豆腐', ['豆腐'])]
    result, changes = meal_selection.review(pool[:3], pool)
    assert {r.item_id for r in result} == {1, 3, 4} or {r.item_id for r in result} == {2, 3, 4}
    assert len(changes) == 1
    assert meal_selection.summary(result, set())['soup_dishes'] == 1


def test_existing_soup_is_considered_and_fixed_menu_is_never_changed():
    fixed = dish(9, '排骨汤', ['排骨'], ['汤'])
    soup = dish(1, '鸡汤', ['鸡肉'], ['汤'])
    veg = dish(2, '菠菜', ['菠菜'])
    result, changes = meal_selection.review([soup], [soup, veg], existing=[fixed])
    assert [r.item_id for r in result] == [2]
    assert fixed.item_id == 9 and len(changes) == 1


def test_valid_menu_is_preserved_and_impossible_goals_do_not_invent_candidates():
    menu = [dish(1, '蒸鸡肉', ['鸡肉']), dish(2, '炒菠菜', ['菠菜'])]
    assert meal_selection.review(menu, menu) == (menu, [])
    soups = [dish(3, '鸡汤', ['鸡肉'], ['汤']), dish(4, '排骨汤', ['排骨'], ['汤'])]
    assert meal_selection.review(soups, soups) == (soups, [])


def test_explicit_soup_only_and_vegetarian_goals_override_default_structure():
    soups = [dish(1, '鸡汤', ['鸡肉'], ['汤']), dish(2, '菠菜汤', ['菠菜'], ['汤'])]
    veg = dish(3, '炒茄子', ['茄子'])
    requirements = meal_selection.policy('只推荐汤')
    assert meal_selection.review(soups, [*soups, veg], requirements=requirements) == (soups, [])
    vegetarian = meal_selection.policy('全素')
    result = meal_selection.select_meal([*soups, veg], 3, food_ids=set(), requirements=vegetarian)
    assert {r.item_id for r in result} == {2, 3}
    assert all(meal_selection.features(r).plant_only for r in result)
    assert not meal_selection.policy('取消全素，推荐菜谱', ['全素']).vegetarian
    assert not meal_selection.policy('取消只推荐汤', ['只推荐汤']).soup_only


@pytest.mark.parametrize('mode', ['chat', 'compose'])
def test_service_repairs_extra_soup_and_discards_stale_model_description(session, monkeypatch, mode):
    from app.ai import client as ai_client
    from app.core.config import settings
    from app.models.recipe import Recipe
    from app.schemas.ai import AiChatRequest, AiRecommendRequest
    from app.services import ai_service
    pool = [dish(1, '鸡肉汤', ['鸡肉'], ['汤']), dish(2, '排骨汤', ['排骨'], ['汤']),
            dish(3, '清炒菠菜', ['菠菜']), dish(4, '蒸豆腐', ['豆腐'])]
    for item in pool:
        recipe = Recipe(name=item.name, duration_minutes=20, tags=list(item.insight.tags))
        session.add(recipe)
        session.flush()
        item.item_id, item.raw = recipe.id, recipe
    session.commit()
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    monkeypatch.setattr(ai_service.scoring_service, 'score_dishes', lambda *a, **kw: pool)
    old_description = '鸡汤搭配排骨汤和菠菜。'
    monkeypatch.setattr(ai_client, '_network_complete_json', lambda *a, **kw: ai_client.AiResult(ok=True,
        data={'answer': old_description, 'picks': [{'id': c.item_id} for c in pool[:3]]}))
    if mode == 'chat':
        result = ai_service.chat(session, None, AiChatRequest(message='推荐三道菜'))
        final_ids = [r.id for r in result.recipes]
    else:
        result = ai_service.recommend_recipes(session, None, AiRecommendRequest(message='推荐三道菜'))
        final_ids = [r.recipe.id for r in result.recommendations]
    assert pool[3].item_id in final_ids
    assert len({pool[0].item_id, pool[1].item_id} & set(final_ids)) == 1
    assert result.answer != old_description
    assert result.source == 'ai'
    assert any(t.agent == '整餐复核' and '→' in t.summary for t in result.trace)
