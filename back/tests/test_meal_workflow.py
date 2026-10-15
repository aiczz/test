from types import SimpleNamespace
from sqlmodel import select
from app.models.recipe import RecipeIngredient
from app.models.menu import MenuPlan, MenuPlanItem
from app.services import meal_selection
from app.services.scoring_service import ScoredItem
from tests.test_business import _auth, _register


def dish(i, name, tags, foods, minutes=20, quality=5):
    insight = SimpleNamespace(name=name, tags=tags, main_ingredients=[name], ingredient_ids=foods,
                              duration_source="table", duration_minutes=minutes)
    return ScoredItem(raw=SimpleNamespace(tags=tags), item_id=i, name=name, score=quality,
                      quality=quality, reason="", insight=insight)


def test_balanced_meal_avoids_repeated_soup_and_protein():
    pool = [dish(1,"排骨汤",["汤"],[1]), dish(2,"牛肉汤",["汤"],[2]),
            dish(3,"鸡肉汤",["汤"],[3]), dish(4,"清炒菠菜",["素菜"],[4]),
            dish(5,"番茄炒蛋",[],[5])]
    selected = meal_selection.select_meal(pool, 3, food_ids=set())
    report = meal_selection.summary(selected, set())
    assert report["soup_dishes"] <= 1
    assert report["vegetable_dishes"] >= 1
    assert len({d.item_id for d in selected}) == 3


def test_modes_and_existing_menu_affect_choice():
    pool = [dish(1,"牛肉炒菜",[],[1,2],minutes=50), dish(2,"清炒菠菜",["素菜"],[3],minutes=10)]
    existing = [dish(9,"牛肉炖菜",[],[1])]
    assert meal_selection.select_meal(pool,1,food_ids={3},goal="pantry")[0].item_id == 2
    assert meal_selection.select_meal(pool,1,food_ids={3},goal="fewer_purchases")[0].item_id == 2
    assert meal_selection.select_meal(pool,1,food_ids=set(),goal="quick")[0].item_id == 2
    assert meal_selection.select_meal(pool,1,food_ids=set(),existing=existing)[0].item_id == 2


def test_date_menu_save_replace_and_owner_isolation(client, session):
    headers = _auth(client)
    data = {"recipe_ids": [1,2,1], "people": 2, "menu_date": "2026-10-14"}
    first = client.put('/api/menu/today',json=data,headers=headers)
    assert first.status_code == 200, first.text
    assert [r['id'] for r in first.json()['meals']['dinner']] == [1,2]
    second = client.put('/api/menu/today',json={**data,"recipe_ids":[2,3]},headers=headers).json()
    assert second['id'] == first.json()['id']
    assert [r['id'] for r in second['meals']['dinner']] == [2,3]
    assert len(session.exec(select(MenuPlanItem).where(MenuPlanItem.menu_plan_id==second['id'])).all()) == 2
    assert client.get('/api/menu/today?menu_date=2026-10-15',headers=headers).status_code == 404
    other = _register(client,'meal_other')
    assert client.get('/api/menu/today?menu_date=2026-10-14',headers=other).status_code == 404
    assert client.post('/api/shopping-list/generate',json={'menu_plan_id':second['id']},headers=other).status_code == 404
    invalid = client.put('/api/menu/today',json={**data,'recipe_ids':[999999]},headers=headers)
    assert invalid.status_code == 422
    assert [r['id'] for r in client.get('/api/menu/today?menu_date=2026-10-14',headers=headers).json()['meals']['dinner']] == [2,3]


def test_shopping_merges_units_and_subtracts_exact_stock(client, session):
    headers = _auth(client)
    session.add(RecipeIngredient(recipe_id=1,food_id=1,ingredient_name='莲藕',amount=200,unit='克',category='蔬菜'))
    session.add(RecipeIngredient(recipe_id=2,food_id=1,ingredient_name='藕',amount=.3,unit='kg',category='蔬菜'))
    session.commit()
    client.post('/api/my-foods',json={'food_id':1,'amount':.1,'unit':'公斤'},headers=headers)
    plan = client.put('/api/menu/today',json={'recipe_ids':[1,2]},headers=headers).json()
    result = client.post('/api/shopping-list/generate',json={'menu_plan_id':plan['id'],'subtract_my_foods':True},headers=headers).json()
    flat = [i for g in result['categories'] for i in g['items']]
    grams = [i for i in flat if i['food_id']==1 and i['unit']=='克']
    assert len(grams) == 1
    assert grams[0]['amount'] == 400
    assert any(i['food_id']==1 and i['unit']=='节' for i in flat) # Cannot convert a segment to grams.
    assert any(i['needs_confirmation'] for i in flat)
    assert client.get('/api/my-foods',headers=headers).json()[0]['amount'] == .1
    checked = client.put(f"/api/shopping-list/items/{grams[0]['id']}",json={'checked':True},headers=headers)
    assert checked.json()['checked']


def test_unknown_quantity_and_name_only_stock_keep_requirements(client, session):
    headers = _auth(client)
    session.add(RecipeIngredient(recipe_id=1,food_id=1,ingredient_name='莲藕',amount=None,unit='克'))
    session.add(RecipeIngredient(recipe_id=2,food_id=1,ingredient_name='莲藕',amount=300,unit='克'))
    session.commit()
    client.post('/api/my-foods',json={'food_id':1},headers=headers)
    plan = client.put('/api/menu/today',json={'recipe_ids':[1,2]},headers=headers).json()
    result = client.post('/api/shopping-list/generate',json={'menu_plan_id':plan['id'],'subtract_my_foods':True},headers=headers).json()
    entries=[i for g in result['categories'] for i in g['items'] if i['food_id']==1]
    assert entries
    assert any(i['unit']=='克' and i['needs_confirmation'] for i in entries)


def test_recommendation_excludes_selected_menu_and_reports_combination(client):
    result=client.post('/api/ai/recommend',json={'menu_recipe_ids':[1], 'cook_minutes':240, 'meal_goal':'balanced'}).json()
    assert result['recommendations']
    assert all(r['recipe']['id'] != 1 for r in result['recommendations'])
    assert 'soup_dishes' in result['meal_summary']
