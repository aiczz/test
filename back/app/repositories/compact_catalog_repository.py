"""对清洗后六张业务表的只读访问。

这里只执行 SELECT。用户收藏、菜单等写操作仍落在各自业务表中。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from app.data.catalog_types import (
    FoodRecord,
    FoodSeasonRecord,
    RecipeIngredientRecord,
    RecipeRecord,
    RecipeStepRecord,
)


_CATEGORY_MAP = {
    "蔬菜": "vegetable",
    "薯芋": "vegetable",
    "菌菇": "vegetable",
    "菌菇藻类": "vegetable",
    "水果": "fruit",
    "畜肉": "meat_egg",
    "禽肉": "meat_egg",
    "蛋类": "meat_egg",
    "肉蛋": "meat_egg",
    "水产": "aquatic",
    "豆类": "soy",
    "豆制品": "soy",
    "谷物": "grain",
    "坚果": "grain",
    "调味": "seasoning",
    "调味料": "seasoning",
}


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "")]


def _category(value: str | None) -> str:
    return _CATEGORY_MAP.get(value or "", "other")


def _food(row: Mapping[str, Any]) -> FoodRecord:
    nutrition = []
    for label, key, unit in (
        ("能量", "energy_kcal", "kcal"),
        ("蛋白质", "protein", "g"),
        ("脂肪", "fat", "g"),
        ("碳水", "cho", "g"),
    ):
        if row.get(key) is not None:
            nutrition.append(f"{label}{float(row[key]):g}{unit}")
    return FoodRecord(
        id=int(row["id"]),
        name=str(row["name"]),
        category=_category(row.get("category")),
        description=row.get("reason"),
        nutrition_summary="、".join(nutrition) or None,
        tags=_json_list(row.get("effects_json")),
        is_active=bool(row.get("is_edible", 1)),
    )


def list_foods(
    session: Session,
    *,
    category: str | None,
    keyword: str | None,
    offset: int,
    limit: int,
) -> tuple[list[FoodRecord], int]:
    clauses = ["is_edible = 1"]
    params: dict[str, Any] = {"offset": offset, "limit": limit}
    if keyword:
        clauses.append("name LIKE :keyword")
        params["keyword"] = f"%{keyword}%"
    if category:
        source_categories = [k for k, v in _CATEGORY_MAP.items() if v == category]
        if source_categories:
            placeholders = []
            for index, value in enumerate(source_categories):
                key = f"category_{index}"
                placeholders.append(f":{key}")
                params[key] = value
            clauses.append(f"category IN ({', '.join(placeholders)})")
        elif category == "other":
            known = []
            for index, value in enumerate(_CATEGORY_MAP):
                key = f"known_{index}"
                known.append(f":{key}")
                params[key] = value
            clauses.append(f"category NOT IN ({', '.join(known)})")
        else:
            clauses.append("1 = 0")
    where = " AND ".join(clauses)
    total = session.execute(
        text(f"SELECT COUNT(*) FROM ingredients WHERE {where}"), params
    ).scalar_one()
    rows = session.execute(
        text(
            "SELECT id, name, category, is_edible, reason, effects_json, "
            "energy_kcal, protein, fat, cho FROM ingredients "
            f"WHERE {where} ORDER BY id LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings()
    return [_food(row) for row in rows], int(total)


def get_food(session: Session, food_id: int) -> FoodRecord | None:
    row = session.execute(
        text(
            "SELECT id, name, category, is_edible, reason, effects_json, "
            "energy_kcal, protein, fat, cho FROM ingredients WHERE id = :id"
        ),
        {"id": food_id},
    ).mappings().first()
    return _food(row) if row else None


_SEASON_MONTHS = {
    "春": (3, 5),
    "夏": (6, 8),
    "秋": (9, 11),
    "冬": (12, 2),
}


def _season(row: Mapping[str, Any], *, score: int | None = None) -> FoodSeasonRecord:
    season_name = str(row.get("season") or "")
    start, end = _SEASON_MONTHS.get(season_name, (1, 12))
    if row.get("level") == "月份":
        match = re.search(r"(\d+)", str(row.get("time_name") or row.get("name") or ""))
        if match:
            start = end = int(match.group(1))
    return FoodSeasonRecord(
        food_id=int(row["ingredient_id"]),
        start_month=start,
        end_month=end,
        season_name=season_name or row.get("time_name"),
        season_score=score if score is not None else (100 if row.get("level") == "月份" else 85),
        description=row.get("recommendation_reason") or row.get("note"),
    )


def get_food_season(session: Session, food_id: int) -> FoodSeasonRecord | None:
    row = session.execute(
        text(
            "SELECT sf.ingredient_id, sf.level, sf.time_name, sf.season, "
            "sf.note, sf.recommendation_reason "
            "FROM seasonal_food sf WHERE sf.ingredient_id = :id "
            "ORDER BY CASE WHEN sf.level = '月份' THEN 0 ELSE 1 END, sf.id LIMIT 1"
        ),
        {"id": food_id},
    ).mappings().first()
    return _season(row) if row else None


def list_seasonal(
    session: Session, *, month: int, limit: int
) -> list[tuple[FoodRecord, FoodSeasonRecord]]:
    month_name = f"{month}月"
    season_name = "春" if 3 <= month <= 5 else "夏" if 6 <= month <= 8 else "秋" if 9 <= month <= 11 else "冬"
    rows = session.execute(
        text(
            "SELECT i.id, i.name, i.category, i.is_edible, i.reason, i.effects_json, "
            "i.energy_kcal, i.protein, i.fat, i.cho, sf.ingredient_id, sf.level, "
            "sf.time_name, sf.season, sf.note, sf.recommendation_reason "
            "FROM seasonal_food sf "
            "JOIN ingredients i ON i.id = sf.ingredient_id "
            "JOIN seasonal_calendar sc ON sc.id = sf.calendar_id "
            "WHERE i.is_edible = 1 AND sf.ingredient_id IS NOT NULL "
            "AND ((sc.level = '月份' AND sc.name = :month_name) "
            "OR (sc.level = '季节' AND sc.season = :season_name)) "
            "ORDER BY CASE WHEN sc.level = '月份' THEN 0 ELSE 1 END, i.usage_count DESC, i.id"
        ),
        {"month_name": month_name, "season_name": season_name},
    ).mappings()
    result: list[tuple[FoodRecord, FoodSeasonRecord]] = []
    seen: set[int] = set()
    for row in rows:
        food = _food(row)
        if food.id in seen:
            continue
        seen.add(food.id)
        result.append((food, _season(row)))
        if len(result) >= limit:
            break
    return result


def list_all_foods(session: Session) -> list[FoodRecord]:
    rows, _ = list_foods(
        session, category=None, keyword=None, offset=0, limit=1_000_000
    )
    return rows


def _recipe(row: Mapping[str, Any]) -> RecipeRecord:
    return RecipeRecord(
        id=int(row["id"]),
        name=str(row["dish_name"]),
        description=row.get("description"),
        category=row.get("cuisine"),
        season_recommendation=row.get("season_recommendation"),
        tags=_json_list(row.get("tags_json")),
        instruction_text=row.get("instruction_text"),
    )


def _recipe_where(
    *,
    category: str | None,
    season: str | None,
    difficulty: str | None,
    max_duration: int | None,
    keyword: str | None,
) -> tuple[str, dict[str, Any]]:
    clauses = ["1 = 1"]
    params: dict[str, Any] = {}
    if category:
        clauses.append("d.cuisine = :category")
        params["category"] = category
    if difficulty and difficulty != "简单":
        clauses.append("1 = 0")
    if max_duration is not None and max_duration < 30:
        clauses.append("1 = 0")
    if keyword:
        clauses.append("d.dish_name LIKE :keyword")
        params["keyword"] = f"%{keyword}%"
    if season:
        params["season"] = season[0]
        clauses.append(
            "EXISTS (SELECT 1 FROM seasonal_dish_links sdl "
            "JOIN seasonal_food sf ON sf.id = sdl.seasonal_food_id "
            "WHERE sdl.dish_id = d.id AND sf.season = :season)"
        )
    return " AND ".join(clauses), params


def list_recipes(
    session: Session,
    *,
    category: str | None,
    season: str | None,
    difficulty: str | None,
    max_duration: int | None,
    keyword: str | None,
    offset: int,
    limit: int,
) -> tuple[list[RecipeRecord], int]:
    where, params = _recipe_where(
        category=category,
        season=season,
        difficulty=difficulty,
        max_duration=max_duration,
        keyword=keyword,
    )
    total = session.execute(
        text(f"SELECT COUNT(*) FROM dishes d WHERE {where}"), params
    ).scalar_one()
    params.update({"offset": offset, "limit": limit})
    rows = session.execute(
        text(
            "SELECT d.id, d.dish_name, d.description, d.cuisine, d.tags_json, "
            "d.instruction_text, NULL AS season_recommendation "
            f"FROM dishes d WHERE {where} ORDER BY d.id LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings()
    return [_recipe(row) for row in rows], int(total)


def search_recipes(
    session: Session, keyword: str, *, offset: int, limit: int
) -> tuple[list[RecipeRecord], int]:
    where = (
        "d.dish_name LIKE :keyword OR EXISTS ("
        "SELECT 1 FROM dish_ingredients di WHERE di.dish_id = d.id "
        "AND (di.raw_name LIKE :keyword OR di.raw_text LIKE :keyword))"
    )
    params: dict[str, Any] = {"keyword": f"%{keyword}%"}
    total = session.execute(
        text(f"SELECT COUNT(*) FROM dishes d WHERE {where}"), params
    ).scalar_one()
    params.update({"offset": offset, "limit": limit})
    rows = session.execute(
        text(
            "SELECT d.id, d.dish_name, d.description, d.cuisine, d.tags_json, "
            "d.instruction_text, NULL AS season_recommendation "
            f"FROM dishes d WHERE {where} ORDER BY d.id LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings()
    return [_recipe(row) for row in rows], int(total)


def get_recipe(session: Session, recipe_id: int) -> RecipeRecord | None:
    row = session.execute(
        text(
            "SELECT d.id, d.dish_name, d.description, d.cuisine, d.tags_json, "
            "d.instruction_text, NULL AS season_recommendation "
            "FROM dishes d WHERE d.id = :id"
        ),
        {"id": recipe_id},
    ).mappings().first()
    return _recipe(row) if row else None


def list_recipe_ingredients(
    session: Session, recipe_id: int
) -> list[RecipeIngredientRecord]:
    rows = session.execute(
        text(
            "SELECT di.id, di.dish_id, di.ingredient_id, di.raw_name, di.quantity, "
            "di.role, di.grams, i.category FROM dish_ingredients di "
            "LEFT JOIN ingredients i ON i.id = di.ingredient_id "
            "WHERE di.dish_id = :id ORDER BY di.id"
        ),
        {"id": recipe_id},
    ).mappings()
    return [
        RecipeIngredientRecord(
            id=int(row["id"]),
            recipe_id=int(row["dish_id"]),
            food_id=int(row["ingredient_id"]) if row["ingredient_id"] is not None else None,
            ingredient_name=str(row["raw_name"]),
            amount=float(row["grams"]) if row["grams"] is not None else None,
            unit="克" if row["grams"] is not None else (row["quantity"] or None),
            is_required=row["role"] != "optional",
            category=_category(row["category"]),
        )
        for row in rows
    ]


_STEP_SPLIT = re.compile(r"(?:\r?\n)+|(?=第?[一二三四五六七八九十\d]+[、.．步：:])")


def list_recipe_steps(session: Session, recipe_id: int) -> list[RecipeStepRecord]:
    instruction = session.execute(
        text("SELECT instruction_text FROM dishes WHERE id = :id"), {"id": recipe_id}
    ).scalar_one_or_none()
    if not instruction:
        return []
    parts = [part.strip() for part in _STEP_SPLIT.split(str(instruction)) if part.strip()]
    return [
        RecipeStepRecord(
            id=recipe_id * 1000 + index,
            recipe_id=recipe_id,
            step_no=index,
            title=f"第 {index} 步",
            description=part,
        )
        for index, part in enumerate(parts, start=1)
    ]


def list_recipes_by_food(
    session: Session, food_id: int, *, limit: int
) -> list[RecipeRecord]:
    # 除精确食材外，同时匹配其核心食材和直接子类，例如“鸡肉”可推出鸡胸/鸡腿菜谱。
    rows = session.execute(
        text(
            "SELECT DISTINCT d.id, d.dish_name, d.description, d.cuisine, d.tags_json, "
            "d.instruction_text, NULL AS season_recommendation "
            "FROM dishes d JOIN dish_ingredients di ON di.dish_id = d.id "
            "LEFT JOIN ingredients child ON child.id = di.ingredient_id "
            "WHERE di.ingredient_id = :food_id OR di.core_ingredient_id = :food_id "
            "OR child.core_ingredient_id = :food_id "
            "ORDER BY d.id LIMIT :limit"
        ),
        {"food_id": food_id, "limit": limit},
    ).mappings()
    return [_recipe(row) for row in rows]


def list_recipes_by_ids(session: Session, recipe_ids: list[int]) -> list[RecipeRecord]:
    if not recipe_ids:
        return []
    placeholders = []
    params: dict[str, Any] = {}
    for index, recipe_id in enumerate(recipe_ids):
        key = f"id_{index}"
        placeholders.append(f":{key}")
        params[key] = recipe_id
    rows = session.execute(
        text(
            "SELECT d.id, d.dish_name, d.description, d.cuisine, d.tags_json, "
            "d.instruction_text, NULL AS season_recommendation FROM dishes d "
            f"WHERE d.id IN ({', '.join(placeholders)})"
        ),
        params,
    ).mappings()
    by_id = {int(row["id"]): _recipe(row) for row in rows}
    return [by_id[item] for item in recipe_ids if item in by_id]
