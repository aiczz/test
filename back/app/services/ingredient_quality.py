"""Normalize uncertain source quantities without inventing recipe measurements."""
import math


GROUP_HEADERS = {'蔬菜类', '蛋白质类', '碳水主食类', '水果类', '主食类', '调料类', '调味品类'}
UNCERTAIN_UNITS = {'份', '适量', '少许', '少量', '若干', ''}


def positive_amount(value) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (ValueError, TypeError, OverflowError):
        return False


def is_ingredient(name, amount) -> bool:
    return bool((name or '').strip()) and (name.strip() not in GROUP_HEADERS or positive_amount(amount))


def normalize_unit(unit: str) -> tuple[str, float]:
    units = {'g': ('克', 1), '克': ('克', 1), 'kg': ('克', 1000), '千克': ('克', 1000),
             '公斤': ('克', 1000), '斤': ('克', 500), '毫升': ('毫升', 1), 'ml': ('毫升', 1),
             '升': ('毫升', 1000), 'l': ('毫升', 1000)}
    value = (unit or '').strip().lower()
    return units.get(value, (value or '份', 1))


def stock_requirements(details, inventory, food_names=None):
    """Merge recipe demand, then classify against actual stock; never write stock."""
    food_names = food_names or {}
    name_ids = {}
    for food_id, name in food_names.items():
        name_ids.setdefault(name.strip(), set()).add(food_id)
    requirements = {}
    for detail in details:
        for i in detail.ingredients:
            if not is_ingredient(i.name, i.amount):
                continue
            food_id = i.food_id
            canonical = name_ids.get(i.name.strip(), set())
            if food_id is None and len(canonical) == 1:
                food_id = next(iter(canonical))
            identity = ('id', food_id) if food_id is not None else ('name', i.name.strip())
            unit, scale = normalize_unit(i.unit)
            key = (identity, unit)
            amount = float(i.amount) * scale if positive_amount(i.amount) and unit not in UNCERTAIN_UNITS else None
            if key not in requirements:
                requirements[key] = {'name': i.name, 'food_id': food_id, 'amount': amount, 'unit': unit}
            else:
                prior = requirements[key]['amount']
                requirements[key]['amount'] = prior + amount if prior is not None and amount is not None else None
    result = []
    for (identity, unit), need in requirements.items():
        matching = [s for s in inventory if (
            (need['food_id'] is not None and s.food_id == need['food_id']) or
            ((need['food_id'] is None or s.food_id is None) and
             (food_names.get(s.food_id) or s.custom_name or '').strip() == need['name'].strip())) and positive_amount(s.amount)]
        same_unit = [(s, normalize_unit(s.unit)[1]) for s in matching
                     if normalize_unit(s.unit)[0] == unit and unit not in UNCERTAIN_UNITS]
        available = sum(s.amount * scale for s, scale in same_unit)
        if not matching:
            status = 'missing'
        elif need['amount'] is None or not same_unit:
            status = 'confirm'
        elif available >= need['amount']:
            status = 'available'
        else:
            status = 'missing'
        result.append({**need, 'status': status,
                       'remaining': max(0, need['amount'] - available) if need['amount'] is not None else None})
    return result
