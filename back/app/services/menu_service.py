"""菜单生成业务逻辑（说明书 §16 / §17 / §18）。

★ 第一版用规则生成，不调用大模型 —— 说明书 §18 明确要求
  「第一版不要把全部逻辑交给 LLM」。

规则：
  · 早餐要快（≤15 分钟）、午餐适中（≤40）、晚餐可以从容（不限）
  · 口味偏好命中标签的菜优先
  · 同一天内不重复上同一道菜
"""

from sqlmodel import Session

from app.models.menu import MenuPlan, MenuPlanItem
from app.models.recipe import Recipe
from app.repositories import menu_repository, recipe_repository
from app.schemas.menu import (
    MenuDay,
    MenuMeals,
    MenuPlanRequest,
    MenuPlanResponse,
    TodayMenuGenerateRequest,
    TodayMenuResponse,
)
from app.services import recipe_service

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 三餐各自的时间上限（分钟）
_MEAL_MAX_MINUTES = {
    "breakfast": 15,
    "lunch": 40,
    "dinner": 999,
}

# 每餐上几道
_MEAL_DISH_COUNT = {
    "breakfast": 1,
    "lunch": 2,
    "dinner": 2,
}


def _pick(
    session: Session,
    preferences: set[str],
    max_minutes: int,
    count: int,
    exclude: set[int],
) -> list[Recipe]:
    """挑菜：口味偏好命中优先，其次按烹饪时间从短到长。"""
    recipes, _ = recipe_repository.list_recipes(
        session, max_duration=max_minutes, offset=0, limit=50
    )
    # 排除今天已经上过的；全被排掉时退回完整列表（宁可重复也不上空白菜单）
    pool = [r for r in recipes if r.id not in exclude] or recipes

    def score(recipe: Recipe) -> int:
        return sum(1 for tag in (recipe.tags or []) if tag in preferences)

    ordered = sorted(pool, key=lambda r: (-score(r), r.duration_minutes))
    return ordered[:count]


def _persist_items(
    session: Session,
    plan_id: int,
    groups: list[tuple[int, str, list]],
) -> None:
    items: list[MenuPlanItem] = []
    sort_order = 0
    for day_index, meal_type, briefs in groups:
        for brief in briefs:
            items.append(
                MenuPlanItem(
                    menu_plan_id=plan_id,
                    day_index=day_index,
                    meal_type=meal_type,
                    recipe_id=brief.id,
                    sort_order=sort_order,
                )
            )
            sort_order += 1
    menu_repository.add_items(session, items)


# ---------------------------------------------------------------------
# §16 今日菜单
# ---------------------------------------------------------------------


def generate_today(
    session: Session, user_id: int, payload: TodayMenuGenerateRequest
) -> TodayMenuResponse:
    preferences = set(payload.preferences)
    used: set[int] = set()
    meals: dict[str, list] = {}

    for meal_type in payload.meal_types:
        if meal_type not in _MEAL_MAX_MINUTES:
            continue
        picked = _pick(
            session,
            preferences,
            _MEAL_MAX_MINUTES[meal_type],
            _MEAL_DISH_COUNT[meal_type],
            used,
        )
        used.update(r.id for r in picked)
        meals[meal_type] = [recipe_service.to_brief(r) for r in picked]

    plan = menu_repository.create_plan(
        session,
        MenuPlan(
            user_id=user_id,
            title="今日菜单",
            plan_type="today",
            people=payload.people,
            days=1,
            source="ai",
        ),
    )
    _persist_items(
        session, plan.id, [(0, meal_type, briefs) for meal_type, briefs in meals.items()]
    )

    return TodayMenuResponse(
        id=plan.id,
        title=plan.title,
        people=plan.people,
        meals=MenuMeals(
            breakfast=meals.get("breakfast", []),
            lunch=meals.get("lunch", []),
            dinner=meals.get("dinner", []),
        ),
    )


def get_today(session: Session, user_id: int) -> TodayMenuResponse | None:
    """取最近一次生成的今日菜单。没生成过返回 None（路由层转 404）。"""
    plan = menu_repository.get_latest(session, user_id, "today")
    if plan is None:
        return None

    items = menu_repository.get_items(session, plan.id)
    by_id = {
        recipe.id: recipe
        for recipe in recipe_repository.list_by_ids(
            session, [item.recipe_id for item in items]
        )
    }

    meals: dict[str, list] = {"breakfast": [], "lunch": [], "dinner": []}
    for item in items:
        recipe = by_id.get(item.recipe_id)
        if recipe is not None and item.meal_type in meals:
            meals[item.meal_type].append(recipe_service.to_brief(recipe))

    return TodayMenuResponse(
        id=plan.id,
        title=plan.title,
        people=plan.people,
        meals=MenuMeals(**meals),
    )


# ---------------------------------------------------------------------
# §17 多日菜单
# ---------------------------------------------------------------------


def generate_plan(
    session: Session, user_id: int, payload: MenuPlanRequest
) -> MenuPlanResponse:
    preferences = set(payload.preferences)
    used: set[int] = set()
    groups: list[tuple[int, str, list]] = []
    days: list[MenuDay] = []

    for day in range(payload.days):
        picked = _pick(session, preferences, 999, 3, used)
        used.update(r.id for r in picked)
        briefs = [recipe_service.to_brief(r) for r in picked]
        groups.append((day, "dinner", briefs))
        days.append(
            MenuDay(
                day_index=day + 1,
                label=_WEEKDAYS[day % len(_WEEKDAYS)],
                recipes=briefs,
            )
        )

    plan = menu_repository.create_plan(
        session,
        MenuPlan(
            user_id=user_id,
            title=f"{payload.days} 日菜单",
            plan_type="three_day" if payload.days == 3 else "custom",
            people=payload.people,
            days=payload.days,
            source="ai",
        ),
    )
    _persist_items(session, plan.id, groups)

    return MenuPlanResponse(
        id=plan.id,
        title=plan.title,
        people=plan.people,
        days=days,
    )
