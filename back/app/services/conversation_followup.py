"""Resolve recommendation follow-ups against database facts, before generic routing."""
from dataclasses import dataclass, field
import re
import math

from app.repositories import recipe_repository, food_repository
from app.repositories.catalog_insight_repository import food_insights
from app.services import recipe_service, food_service
from app.schemas.home import HomeFoodItem
from app.services.chat_context import number


@dataclass
class Followup:
    kind: str
    ids: list[int] = field(default_factory=list)
    answer: str = ''
    clarification: bool = False
    detail_kind: str | None = None
    foods: list[HomeFoodItem] = field(default_factory=list)


_GROUP_HEADERS = {'蔬菜类', '蛋白质类', '碳水主食类', '水果类', '主食类', '调料类', '调味品类'}


def positive_amount(ingredient) -> bool:
    try:
        return math.isfinite(float(ingredient.amount)) and float(ingredient.amount) > 0
    except (TypeError, ValueError):
        return False


def actual_ingredients(detail):
    return [i for i in detail.ingredients if i.name not in _GROUP_HEADERS or positive_amount(i)]


def ingredient_text(detail) -> str:
    specified, unspecified = [], []
    for i in actual_ingredients(detail):
        if positive_amount(i):
            specified.append(f'{i.name}（{i.amount}{i.unit or ""}）')
        else:
            unspecified.append(i.name + (f'（{i.unit}）' if i.unit in {'适量', '少许', '若干'} else ''))
    parts = ['、'.join(specified)] if specified else []
    if unspecified:
        parts.append('用量未注明：' + '、'.join(unspecified))
    return '\n'.join(parts) or '菜谱暂无配料记录，不能可靠列出所需食材。'


def ingredient_cards(session, recipe_ids) -> Followup:
    catalogue, _ = food_repository.list_foods(session, limit=2000)
    by_id = {food.id: food for food in catalogue}
    by_name = {food.name.strip(): food for food in catalogue}
    cards, unmatched, seen = [], [], set()
    for recipe_id in recipe_ids:
        detail = recipe_service.get_detail(session, recipe_id)
        if detail is None:
            continue
        for ingredient in actual_ingredients(detail):
            food = by_id.get(ingredient.food_id) or by_name.get(ingredient.name.strip())
            if food is None:
                if ingredient.name not in unmatched:
                    unmatched.append(ingredient.name)
                continue
            if food.id not in seen and len(cards) < 200:
                seen.add(food.id)
                cards.append(HomeFoodItem(**food_service.to_brief(food).model_dump(), reason='来自刚才菜谱的配料清单'))
    answer = f'下面是刚才配料清单中匹配到的 {len(cards)} 种食材，已去重，点击“加入我的食材”即可添加。' if cards else '刚才的配料暂未匹配到可添加的食材记录。'
    if unmatched:
        answer += '\n尚未匹配到食材卡片：' + '、'.join(unmatched) + '。'
    answer += '\n这里仅展示清单，尚未替你添加库存；实际用量以原菜谱为准。'
    return Followup('ingredient_cards', list(recipe_ids), answer, foods=cards)


def resolve(session, payload, named_food_ids=()) -> Followup | None:
    state = payload.conversation_state
    message = payload.message.strip()
    recipe_ids = list(state.last_recommended_recipe_ids)
    food_ids = list(state.last_recommended_food_ids)
    focus = 'recipes' if state.active_topic == 'recipe_ingredients' else state.last_recommendation_kind
    ordinal = re.search(r'第\s*([0-9]+|[一二两三四五六七八九十]+)\s*(道|个|种|样)', message)
    ingredient_query = bool(re.search(
        r'(?:需要|要用|要哪些|要什么|要啥|用到|用什么|准备|买|采购|还缺).*(?:食材|材料|配料)|(?:食材|材料|配料)(?:清单|有哪些|是什么|呢)|(?:第.*道|这道菜|这几道菜|这些菜).*的(?:食材|材料|配料)|要准备什么|要买(?:什么|啥)|^(?:食材|配料|材料)[呢？?。]*$', message))
    ingredient_query = ingredient_query or bool(recipe_ids and re.fullmatch(
        r'(?:这些菜|这几道菜|这道菜|它|上面的菜)?(?:都)?(?:需要|要准备|要买)(?:什么|啥|哪些)[？?。]*', message))
    steps_query = bool(re.search(r'怎么做|如何做|做法|步骤', message))
    ingredient_context = state.active_topic == 'recipe_ingredients' or (
        state.active_topic is None and state.last_recipe_detail == 'ingredients') or (
        focus == 'recipes' and bool(re.search(r'食材|配料|材料', message)))
    display = bool(re.search(r'展示|显示|列出|列出来|给我看看|看一下|查看|卡片|加入|添加|放进|存到|收进', message))
    food_reference = bool(re.search(r'这些|这几样|上述|上面的|刚才的|它们|食材|配料|材料', message))
    if ingredient_context and display and food_reference and not re.search(r'重新推荐|另外推荐|换一批|新的食材', message):
        sources = state.ingredient_recipe_ids or state.focused_recipe_ids or recipe_ids
        if sources:
            return ingredient_cards(session, sources)
    if ordinal and re.fullmatch(r'第\s*(?:[0-9]+|[一二两三四五六七八九十]+)\s*道[呢？?。]*', message):
        ingredient_query = state.last_recipe_detail == 'ingredients'
        steps_query = state.last_recipe_detail == 'steps'
    explicit_recipes = bool(re.search(r'菜谱|这几道菜|这些菜|上面的菜|刚才的菜', message)) or bool(ordinal and ordinal[2] == '道')
    known = {r.id: r for r in recipe_repository.list_by_ids(session, recipe_ids)} if recipe_ids else {}
    named_recipes = [i for i in recipe_ids if i in known and known[i].name in message]
    # Required ingredients are a recipe-detail question, never a fresh seasonal-food recommendation.
    explicit_food_cooking = bool(re.search(r'这些食材|这些配料|这些材料|这几样', message))
    if ingredient_query or (steps_query and not explicit_food_cooking and (focus == 'recipes' or explicit_recipes or named_recipes)):
        if not recipe_ids:
            return Followup('recipe_detail', answer='你想了解哪道菜的配料？请告诉我菜名，或先让我推荐菜谱。', clarification=True)
        selected = named_recipes or list(state.focused_recipe_ids or recipe_ids)
        if ordinal:
            index = int(number(ordinal[1])) - 1
            if not 0 <= index < len(recipe_ids):
                return Followup('recipe_detail', answer=f'上一轮共有 {len(recipe_ids)} 道菜，请说明要查看第几道。', clarification=True)
            selected = [recipe_ids[index]]
        elif explicit_recipes and not named_recipes:
            selected = recipe_ids
        if steps_query and not ingredient_query and len(selected) > 1:
            names = '、'.join(f'{n}.{known[i].name}' for n, i in enumerate(recipe_ids, 1) if i in known)
            return Followup('recipe_detail', answer=f'你想看哪一道的做法？{names}。可以说“第二道怎么做”。', clarification=True)
        blocks = []
        for recipe_id in selected:
            detail = recipe_service.get_detail(session, recipe_id)
            if detail is None:
                blocks.append('这道菜目前无法读取，原记录可能已变更。')
                continue
            if ingredient_query:
                blocks.append(f'{detail.name}\n' + ingredient_text(detail))
            else:
                blocks.append(f'{detail.name}\n' + ('\n'.join(f'{s.step_no}. {s.description}' for s in detail.steps) or '菜谱暂无做法记录。'))
        note = '\n\n以上按原菜谱记录列出，用量未按人数换算，也不代表这些食材已在库存。' if ingredient_query else ''
        return Followup('recipe_detail', selected, '\n\n'.join(blocks) + note, detail_kind='ingredients' if ingredient_query else 'steps')

    refers = bool(re.search(r'这些|这几个|这几种|这几样|这个|这种|上面的|刚才的|前面的|上述|以上|它', message))
    cooking = bool(re.search(r'(?:能|可以|用).*(?:做|煮|烧|搭配)|做什么菜', message))
    named = [i for i in named_food_ids if i in food_ids]
    if named_food_ids and not named:
        return None  # A newly named ingredient overrides an old reference.
    if cooking and (focus == 'foods' or refers or (ordinal and ordinal[2] in {'种', '样'})) and (
        refers or ordinal or named or re.match(r'^(?:那)?(?:能|可以|怎么做)', message)):
        selected = named or list(state.focused_food_ids or food_ids)
        if re.match(r'^(?:它(?!们)|这个|这种)', message) and not ordinal and not named and len(selected) > 1:
            return Followup('food_recipes', answer='你指的是哪一种食材？可以说食材名字，或“第二种能做什么菜”。', clarification=True)
        if ordinal:
            index = int(number(ordinal[1])) - 1
            if not 0 <= index < len(food_ids):
                return Followup('food_recipes', answer=f'上一轮共有 {len(food_ids)} 种食材，请重新说明要用哪一种。', clarification=True)
            selected = [food_ids[index]]
        foods = food_insights(session, selected) if selected else {}
        if not foods:
            return Followup('food_recipes', answer='这段会话里还没有可引用的食材，请先让我推荐食材，或直接告诉我要用哪些食材。', clarification=True)
        return Followup('food_recipes', [i for i in selected if i in foods])
    return None
