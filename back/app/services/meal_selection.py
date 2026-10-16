"""Bounded deterministic search over safe candidates, not a nutrition guarantee."""
from __future__ import annotations
from dataclasses import dataclass
import re
from app.services.scoring_service import ScoredItem


@dataclass(frozen=True)
class Features:
    food_ids: frozenset[int]
    vegetable: bool
    protein: str
    soup: bool
    method: str
    minutes: float | None
    plant_only: bool = False


@dataclass(frozen=True)
class MealPolicy:
    vegetarian: bool = False
    soup_only: bool = False


def policy(message: str = '', preferences=()) -> MealPolicy:
    from app.services.chat_context import selection_preferences
    text = ' '.join(selection_preferences(message, list(preferences)))
    return MealPolicy(vegetarian=bool(re.search(r'全素|纯素|只要素菜|只吃素|不要荤菜', text)),
                      soup_only=bool(re.search(r'只要汤|只喝汤|只推荐汤|全是汤', text)))


def features(item: ScoredItem) -> Features:
    insight = item.insight
    names = list(getattr(insight, "all_ingredient_names", []) or getattr(insight, "main_ingredients", []) or [])
    tags = list(getattr(insight, "tags", []) or getattr(item.raw, "tags", []) or [])
    # Prefer ingredient records; dish names such as 鱼香茄子 do not prove fish content.
    text = ' '.join(names) if names else item.name
    text = text.replace('鸡腿菇', '蘑菇').replace('羊肚菌', '蘑菇')
    text = re.sub(r'鱼香|鱼露|蚝油|鸡精|鸡粉|牛肉粉|猪油味', '', text)
    protein = next((name for name, words in [
        ("牛肉", ("牛肉", "牛腩", "牛里脊")), ("猪肉", ("猪肉", "排骨", "五花肉", "肉末", "肉馅", "肉丝", "里脊")),
        ("羊肉", ("羊肉", "羊排", "羊腿")),
        ("鸡肉", ("鸡肉", "鸡胸", "鸡腿", "鸡翅", "鸡块", "鸭肉", "鸭腿")), ("鱼虾", ("鱼", "虾", "蟹", "蛤", "贝肉")),
        ("蛋类", ("鸡蛋", "鸭蛋", "鹌鹑蛋", "蛋液", "蛋黄", "蛋清", "皮蛋", "炒蛋", "蛋花", "蒸蛋")), ("豆类", ("豆腐", "豆干", "黄豆", "毛豆")),
    ] if any(w in text for w in words)), "")
    vegetable = any(w in text for w in (
        "青菜", "菠菜", "莲藕", "茄子", "白菜", "西兰花", "黄瓜", "番茄", "西红柿", "胡萝卜", "白萝卜",
        "南瓜", "冬瓜", "丝瓜", "莴笋", "芦笋", "芹菜", "生菜", "菜心", "油麦菜", "荷兰豆", "四季豆",
        "豇豆", "花菜", "土豆", "山药", "木耳", "香菇", "蘑菇", "金针菇", "娃娃菜", "平菇")) or (not names and any(t in tags for t in ("素菜", "素食", "蔬菜")))
    animal = any(w in text for w in ('牛肉', '牛腩', '猪肉', '排骨', '五花肉', '羊肉', '鸡肉', '鸡胸', '鸡腿',
                                    '鸡翅', '鸭肉', '鱼', '虾', '蟹', '蛤', '鸡蛋', '蛋液', '鸭蛋', '牛奶', '奶油', '黄油', '猪油', '肉汤'))
    # Condiments removed for protein classification still rule out a pure plant dish.
    if not protein and re.search(r'(?:^|\s)蛋(?:$|\s)', text):
        protein = '蛋类'
    animal = animal or protein in {'牛肉', '猪肉', '羊肉', '鸡肉', '鱼虾', '蛋类'} or any(w in text for w in ('肉', '奶', '蛋', '骨汤'))
    animal = animal or any(w in ' '.join(names) for w in ('蚝油', '鱼露', '鸡精', '猪油', '鸡汤', '骨汤'))
    soup = "汤羹" in tags or "汤" in tags or item.name.endswith("汤")
    method = next((m for m in ("炖", "煮", "蒸", "炒", "凉拌", "烤", "炸") if m in text or any(m in t for t in tags)), "")
    reliable = insight is None or getattr(insight, "duration_source", "") in {"table", "text"}
    duration = getattr(insight, "duration_minutes", None) if insight else getattr(item.raw, "duration_minutes", None)
    return Features(frozenset(getattr(insight, "ingredient_ids", []) or []), vegetable, protein, soup, method,
                    float(duration) if reliable and duration and duration > 0 else None,
                    plant_only=not animal and (vegetable or protein == '豆类'))


def eligible(candidates: list[ScoredItem], requirements: MealPolicy) -> list[ScoredItem]:
    return [c for c in candidates if (not requirements.vegetarian or features(c).plant_only)
            and (not requirements.soup_only or features(c).soup)]


def _issues(selected: list[Features], available: list[Features], fixed: list[Features], requirements: MealPolicy) -> tuple[int, ...]:
    all_facts = [*fixed, *selected]
    need_variety = len(all_facts) >= 2 and not requirements.soup_only
    proteins = [f.protein for f in all_facts if f.protein and not f.soup]
    return (0 if requirements.soup_only else max(0, sum(f.soup for f in all_facts) - 1),
            int(need_variety and any(f.vegetable for f in [*available, *fixed]) and not any(f.vegetable for f in all_facts)),
            int(need_variety and not requirements.vegetarian and any(f.protein for f in [*available, *fixed]) and not any(f.protein for f in all_facts)),
            max(0, len(proteins) - len(set(proteins))))


def review(selected: list[ScoredItem], candidates: list[ScoredItem], *, existing=None,
           requirements: MealPolicy | None = None) -> tuple[list[ScoredItem], list[str]]:
    """Strictly improving single-dish substitutions, only within the safe pool."""
    requirements = requirements or MealPolicy()
    pool = eligible(candidates, requirements)
    facts = {c.item_id: features(c) for c in pool}
    available = list(facts.values())
    fixed = [features(c) for c in (existing or [])]
    result = list(selected)
    changes = []
    for _ in range(len(result)):
        current = _issues([features(c) for c in result], available, fixed, requirements)
        if not any(current):
            break
        best = None
        used = {c.item_id for c in result}
        for pos, old in enumerate(result):
            for candidate in pool:
                if candidate.item_id in used:
                    continue
                trial = [*result[:pos], candidate, *result[pos+1:]]
                issues = _issues([facts[c.item_id] for c in trial], available, fixed, requirements)
                rank = (issues, -candidate.quality, candidate.item_id, pos)
                if issues < current and (best is None or rank < best[0]):
                    best = (rank, pos, old, candidate)
        if best is None:
            break
        _, pos, old, new = best
        result[pos] = new
        changes.append(f'{old.name} → {new.name}')
    return result, changes


def remaining_issues(selected, candidates, *, existing=None, requirements=None) -> list[str]:
    requirements = requirements or MealPolicy()
    issues = _issues([features(c) for c in selected], [features(c) for c in eligible(candidates, requirements)],
                     [features(c) for c in (existing or [])], requirements)
    return [label for label, amount in zip(('汤菜重复', '缺少蔬菜搭配', '缺少蛋白类', '蛋白来源重复'), issues) if amount]


def select_meal(candidates: list[ScoredItem], count: int, *, food_ids: set[int],
                existing: list[ScoredItem] | None = None, goal: str = "balanced",
                requirements: MealPolicy | None = None) -> list[ScoredItem]:
    requirements = requirements or MealPolicy()
    pool = eligible(list({i.item_id: i for i in candidates}.values())[:24], requirements)
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
        if not requirements.soup_only:
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
    chosen = [pool[i] for i in beam[0]]
    return review(chosen, pool, existing=existing, requirements=requirements)[0]


def summary(items: list[ScoredItem], food_ids: set[int]) -> dict:
    facts = [features(i) for i in items]
    known = [f.minutes for f in facts if f.minutes is not None]
    required = set().union(*(f.food_ids for f in facts)) if facts else set()
    return {"vegetable_dishes": sum(f.vegetable for f in facts), "protein_dishes": sum(bool(f.protein) for f in facts),
            "plant_only_dishes": sum(f.plant_only for f in facts),
            "mixed_dishes": sum(f.vegetable and bool(f.protein) for f in facts),
            "soup_dishes": sum(f.soup for f in facts), "missing_main_ingredient_types": len(required - food_ids),
            "known_dish_minutes_sum": sum(known), "unknown_duration_count": sum(f.minutes is None for f in facts),
            "note": "蔬菜与蛋白类依据配料及标签粗分，混合菜可同时计入两类；不是营养均衡认证。补购仅统计已关联食材；时长之和不是整餐完成时间。"}
