"""Bounded deterministic search over safe candidates, not a nutrition guarantee."""
from __future__ import annotations
from dataclasses import dataclass
from app.services.scoring_service import ScoredItem


@dataclass(frozen=True)
class Features:
    food_ids: frozenset[int]
    vegetable: bool
    protein: str
    soup: bool
    method: str
    minutes: float | None


def features(item: ScoredItem) -> Features:
    insight = item.insight
    names = list(getattr(insight, "main_ingredients", []) or [])
    tags = list(getattr(insight, "tags", []) or getattr(item.raw, "tags", []) or [])
    text = " ".join([item.name, *names])
    protein = next((name for name, words in [
        ("牛肉", ("牛肉", "牛腩")), ("猪肉", ("猪肉", "排骨", "五花肉")),
        ("鸡肉", ("鸡肉", "鸡胸", "鸡腿")), ("鱼虾", ("鱼", "虾", "蟹")),
        ("蛋豆", ("鸡蛋", "豆腐", "豆干")),
    ] if any(w in text for w in words)), "")
    vegetable = any(t in tags for t in ("素菜", "素食", "蔬菜")) or (
        not protein and any(w in text for w in ("青菜", "菠菜", "莲藕", "茄子", "白菜", "西兰花", "黄瓜", "番茄")))
    soup = "汤羹" in tags or "汤" in tags or item.name.endswith("汤")
    method = next((m for m in ("炖", "煮", "蒸", "炒", "凉拌", "烤", "炸") if m in text or any(m in t for t in tags)), "")
    reliable = insight is None or getattr(insight, "duration_source", "") in {"table", "text"}
    duration = getattr(insight, "duration_minutes", None) if insight else getattr(item.raw, "duration_minutes", None)
    return Features(frozenset(getattr(insight, "ingredient_ids", []) or []), vegetable, protein, soup, method,
                    float(duration) if reliable and duration and duration > 0 else None)


def select_meal(candidates: list[ScoredItem], count: int, *, food_ids: set[int],
                existing: list[ScoredItem] | None = None, goal: str = "balanced") -> list[ScoredItem]:
    pool = list({i.item_id: i for i in candidates}.values())[:24]
    count = min(count, len(pool))
    if count <= 0:
        return []
    facts = [features(i) for i in pool]
    fixed = [features(i) for i in (existing or [])]

    def objective(indices: tuple[int, ...]) -> float:
        selected = [facts[i] for i in indices]
        all_facts = [*fixed, *selected]
        score = sum(pool[i].quality for i in indices)
        score += 3 * bool(any(f.vegetable for f in all_facts))
        score += 2 * bool(any(f.protein for f in all_facts))
        score -= 7 * max(0, sum(f.soup for f in all_facts) - 1)
        proteins = [f.protein for f in all_facts if f.protein]
        methods = [f.method for f in all_facts if f.method]
        score -= 3 * (len(proteins) - len(set(proteins)))
        score -= 1.5 * (len(methods) - len(set(methods)))
        required = set().union(*(f.food_ids for f in selected))
        if goal == "fewer_purchases":
            score -= 2 * len(required - food_ids)
        elif goal == "pantry":
            score += 3 * len(required & food_ids)
            score -= len(required - food_ids)
        elif goal == "quick":
            score -= sum(f.minutes * .12 if f.minutes is not None else 5 for f in selected)
        return score

    beam: list[tuple[int, ...]] = [()]
    for depth in range(count):
        expanded = [(*indices, i) for indices in beam
                    for i in range(indices[-1] + 1 if indices else 0, len(pool) - (count - depth - 1))]
        beam = sorted(expanded, key=lambda ids: (-objective(ids), tuple(pool[i].item_id for i in ids)))[:64]
    return [pool[i] for i in beam[0]]


def summary(items: list[ScoredItem], food_ids: set[int]) -> dict:
    facts = [features(i) for i in items]
    known = [f.minutes for f in facts if f.minutes is not None]
    required = set().union(*(f.food_ids for f in facts)) if facts else set()
    return {"vegetable_dishes": sum(f.vegetable for f in facts), "protein_dishes": sum(bool(f.protein) for f in facts),
            "soup_dishes": sum(f.soup for f in facts), "missing_main_ingredient_types": len(required - food_ids),
            "known_dish_minutes_sum": sum(known), "unknown_duration_count": sum(f.minutes is None for f in facts),
            "note": "荤素与做法按现有标签粗分；补购仅统计已关联主料种类。时长之和是逐菜记录汇总，不是整餐完成时间。"}
