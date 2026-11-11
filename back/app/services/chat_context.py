"""Deterministic edits to the explicit constraints carried by a chat session."""
from __future__ import annotations

import re
from app.schemas.ai import AiConversationState, AiPendingAction, AiUnderstanding
from app.services import required_ingredients

DIGITS = dict(zip("零一二三四五六七八九", range(10)))
DIGITS["两"] = 2


def selection_preferences(message: str, previous: list[str] | None = None) -> list[str]:
    """Soft selection goals, separate from ingredient exclusions and time filters."""
    result = list(previous or [])
    groups = {
        '少洗锅': ('少洗锅', '少洗几个锅', '一锅出', '一锅搞定'),
        '省事': ('省事', '简单点', '简单一点', '操作简单'),
        '少油': ('少油', '别太油', '不要太油', '不油腻'),
        '清淡': ('清淡',),
        '高蛋白': ('高蛋白', '补充蛋白质', '补足蛋白质'),
        '全素': ('全素', '纯素', '只要素菜', '只吃素', '不要荤菜'),
        '只推荐汤': ('只推荐汤', '只要汤', '只喝汤', '全是汤'),
    }
    for goal, phrases in groups.items():
        if any(re.search(r'(?:取消|不用|不要求)' + re.escape(p), message) for p in phrases):
            result = [p for p in result if p not in {goal, *phrases}]
        elif any(p in message for p in phrases) and goal not in result:
            result.append(goal)
    return result


def number(text: str) -> float:
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
        return float(text)
    if "十" in text:
        a, b = text.split("十", 1)
        return float(DIGITS.get(a, 1) * 10 + DIGITS.get(b, 0))
    return float(DIGITS[text])


def requested_count(message: str) -> int | None:
    """Extract result quantity independently of diners, time and ingredient weight."""
    token = r"([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十百千]+)"
    unit = r"(?:道|到(?=\s*菜)|款(?=\s*菜)|个(?=\s*(?:菜|食材|蔬菜|水果))|种(?=\s*(?:食材|蔬菜|水果|原料|菜|$))|样(?=\s*(?:食材|蔬菜|水果|原料|菜|$)))"
    matches = list(re.finditer(r"(?<![0-9.零一二两三四五六七八九十百千])" + token + r"\s*" + unit, message))
    if not matches:
        structure = meal_structure(message)
        if structure is not None:
            return structure[0] + structure[1]
        # 纯解析层保留「再来/再推荐/再给我」；是否要写进会话整餐数量，由 edits() 按增量语义判断。
        match = re.fullmatch(r"\s*(?:改成|改为|只要|再来|再推荐|再给我)\s*" + token + r"\s*个?[吧呢。！!]?\s*", message)
        matches = [match] if match else []
    if not matches:
        return None
    selected = matches[0]
    for match in matches[1:]:
        if re.search(r"(?:改成|改为|换成|只要|要)\s*$", message[:match.start()]):
            selected = match
    try:
        value = number(selected[1])
    except (KeyError, ValueError):
        raise ValueError("每次可推荐1至10道菜或种食材，请重新说明数量。") from None
    if not value.is_integer() or not 1 <= value <= 10:
        raise ValueError("每次可推荐1至10道菜或种食材，请重新说明数量。")
    return int(value)


_STRUCT_NUM = r"([0-9]+|[零一二两三四五六七八九十]+)"


def meal_structure(message: str) -> tuple[int, int] | None:
    """解析整餐荤素结构，如「一荤两素」「2荤1素」。

    返回 (荤, 素)。只在用户明确说出 X荤Y素 时生效；
    「全素」由 selection_preferences / MealPolicy.vegetarian 单独处理。
    """
    match = re.search(_STRUCT_NUM + r"\s*荤\s*" + _STRUCT_NUM + r"\s*素", message)
    swapped = False
    if not match:
        match = re.search(_STRUCT_NUM + r"\s*素\s*" + _STRUCT_NUM + r"\s*荤", message)
        swapped = True
    if not match:
        return None
    try:
        first, second = number(match[1]), number(match[2])
    except (KeyError, ValueError):
        return None
    if not first.is_integer() or not second.is_integer():
        return None
    meat, veg = (int(first), int(second)) if not swapped else (int(second), int(first))
    if not (0 <= meat <= 10 and 0 <= veg <= 10 and 1 <= meat + veg <= 10):
        raise ValueError("每次可推荐1至10道菜，请重新说明荤素数量。")
    return meat, veg


_INCREMENTAL = r"(?:再来|再加|再添|再补|再要|追加|另外加|多来|多给|添|补|加)"


def incremental_count(message: str) -> int | None:
    """「再来一道汤」「再加两个菜」——增量请求只作用于本轮，不能改写整餐数量。"""
    token = r"([0-9]+(?:\.[0-9]+)?|[零一二两三四五六七八九十]+)"
    # 量词必须明确指向菜品：「加2勺盐」「加2个鸡蛋」不能算成要 2 道菜。
    unit = r"(?:道|款|个\s*(?:菜|汤|素|荤))"
    match = re.search(_INCREMENTAL + r"\s*" + token + r"\s*" + unit, message)
    if not match:
        return None
    try:
        value = number(match[1])
    except (KeyError, ValueError):
        return None
    if not value.is_integer() or not 1 <= value <= 10:
        raise ValueError("每次可推荐1至10道菜或种食材，请重新说明数量。")
    return int(value)


_FRESH_MEAL = re.compile(
    r"(?:推荐|配|搭配|安排|来|做|准备|整)[^，。；！？]{0,10}"
    r"(?:一餐|一顿饭|一桌|整餐|午餐|晚餐|午饭|晚饭|中饭|早饭|菜)"
)


def is_fresh_meal_request(message: str) -> bool:
    """新一轮整餐推荐 —— 未重申数量时应回到默认，而不是沿用上一次的单菜数量。

    「换一批 / 换一道 / 重新推荐」是对**当前这一餐**的追问，必须保留原数量，
    所以这里明确排除；只有「推荐三个人的一餐」这类重新描述整餐的句子才算新一餐。
    """
    if incremental_count(message) is not None:
        return False
    if re.search(r"换一批|换一桌|换几个|换一道|换一换|重新推荐|重新搭配|再来", message):
        return False
    return bool(_FRESH_MEAL.search(message))


def edits(message: str, state: AiConversationState, terms: list[str]) -> AiConversationState:
    state = state.model_copy(deep=True)
    required = required_ingredients.edit(message, state.required_foods, terms)
    if required is not None:
        state.required_foods = required
    state.selection_preferences = selection_preferences(message, state.selection_preferences)
    # ---- 整餐结构：X荤Y素 ----
    structure = meal_structure(message)
    if structure is not None:
        state.meal_meat_count, state.meal_veg_count = structure
        state.recommendation_count = structure[0] + structure[1]
    elif re.search(r"取消(?:荤素|荤素搭配|搭配要求)|不限荤素|随便(?:搭配|配)", message):
        state.meal_meat_count = None
        state.meal_veg_count = None
    # ---- 增量请求：只作用于本轮，下一轮自动失效 ----
    state.incremental_count = incremental_count(message)
    if state.incremental_count is None and structure is None:
        count = requested_count(message)
        if count is not None:
            state.recommendation_count = count
        elif is_fresh_meal_request(message):
            # 新一轮整餐推荐且没重申数量 → 回到默认，避免被上一轮「再来一道汤」的 1 锁死。
            state.recommendation_count = None
    token = r"([0-9]+(?:\.[0-9]+)?|[一二两三四五六七八九]?十[一二三四五六七八九]?|[一二两三四五六七八九])"
    people = re.search(token + r"\s*个?\s*人", message)
    if people:
        value = number(people[1])
        if not value.is_integer() or not 1 <= value <= 20:
            raise ValueError("用餐人数应为1至20人，请重新说明人数。")
        state.people = int(value)
    minutes = None
    # Prefer compound hour expressions to the simpler minute form.
    if "一个半小时" in message or "一小时半" in message:
        minutes = 90.0
    elif "半小时" in message or "半个小时" in message:
        minutes = 30.0
    elif "一刻钟" in message:
        minutes = 15.0
    else:
        match = re.search(token + r"\s*(分钟|小时|刻钟)", message)
        if match:
            minutes = number(match[1]) * {"分钟": 1, "小时": 60, "刻钟": 15}[match[2]]
    if minutes is not None:
        if not 5 <= minutes <= 240:
            raise ValueError("当前支持5至240分钟的烹饪时间，请重新说明时间。")
        state.cook_minutes = minutes
    if any(t in message for t in ("不用限钠", "取消低钠", "取消限钠", "不限钠")):
        state.low_sodium = False
    elif any(t in message for t in ("低钠", "限钠", "少盐")):
        state.low_sodium = True
    if "取消清淡" in message or "不用清淡" in message:
        state.preferences = [p for p in (state.preferences or []) if p != "清淡"]
    elif "清淡" in message:
        state.preferences = list(dict.fromkeys([*(state.preferences or []), "清淡"]))
    if re.search(r'取消不辣|取消不吃辣|可以吃辣|恢复辣味', message):
        state.avoid_added = [a for a in state.avoid_added if a not in {'辛辣', '辣'}]
        state.avoid_removed = list(dict.fromkeys([*state.avoid_removed, '辛辣', '辣']))
    elif re.search(r'不辣|不要辣|别放辣|不能吃辣|不吃辣', message):
        state.avoid_added = list(dict.fromkeys([*state.avoid_added, '辛辣']))
        state.avoid_removed = [a for a in state.avoid_removed if a != '辛辣']
    soup_removed = any(t in message for t in ("取消不喝汤", "取消不要汤", "可以喝汤", "汤可以", "恢复汤"))
    if soup_removed:
        state.excluded_categories = [c for c in state.excluded_categories if c != "汤羹"]
    elif any(t in message for t in ("不喝汤", "不要汤", "别推荐汤", "不想喝汤", "排除汤")):
        state.excluded_categories = list(dict.fromkeys([*state.excluded_categories, "汤羹"]))
    for clause in re.split(r"[，,。；;！!？?]|但是|不过|但", message):
        if re.search(r'取消只(?:要|吃|推荐)|不要只(?:要|吃|推荐)|不只(?:要|吃)', clause):
            continue  # Cancelling inclusion must not cancel an independent allergy/avoid.
        for term in dict.fromkeys([*terms, *required_ingredients.ANIMALS]):
            if not term or term not in clause:
                continue
            removed = bool(re.search(r"(?:取消|撤销|解除).*" + re.escape(term), clause)) or bool(
                re.search(re.escape(term) + r"(?:可以吃|能吃了|不再忌口)", clause)
            )
            if removed:
                state.avoid_added = [a for a in state.avoid_added if a != term]
                state.avoid_removed = list(dict.fromkeys([*state.avoid_removed, term]))
            elif any(t in clause for t in ("不吃", "不能吃", "过敏", "忌口", "别放", "不要放")) or re.search(
                r'(?:不要|别推荐|排除)\s*' + re.escape(term), clause
            ):
                state.avoid_added = list(dict.fromkeys([*state.avoid_added, term]))
                state.avoid_removed = [a for a in state.avoid_removed if a != term]
    return state


def fill_pending(
    state: AiConversationState, understanding: AiUnderstanding
) -> AiUnderstanding:
    """把对澄清问题的回答填回原动作；新话题和事实读取不触发回填。"""
    pending = state.pending
    if pending is None or understanding.intent == 'unknown':
        return understanding
    answering = understanding.intent == pending.intent and understanding.operation in {
        pending.operation, 'refine', 'answer'
    }
    if not answering:
        return understanding

    # None 和空数组表示本轮未提及；False/0 这类显式值必须保留。
    merged = pending.slots.model_dump()
    for field, value in understanding.slots.model_dump().items():
        if value is not None and value != []:
            merged[field] = value
    return understanding.model_copy(update={
        'operation': pending.operation,
        'slots': understanding.slots.model_copy(update=merged),
        'reset': list(dict.fromkeys([*pending.reset, *understanding.reset])),
        'reference': understanding.reference or pending.reference,
        'detail_kind': understanding.detail_kind or pending.detail_kind,
    })


def apply_understanding(
    state: AiConversationState, understanding: AiUnderstanding
) -> AiConversationState:
    """唯一状态归并入口：只执行通过校验的结构化理解，不再阅读原句猜条件。"""
    state = state.model_copy(deep=True)
    slots = understanding.slots

    if understanding.history_summary is not None:
        state.history_summary = understanding.history_summary[:2000] or None

    state.pending = AiPendingAction(
        intent=understanding.intent,
        operation=understanding.operation,
        slots=slots,
        reset=list(understanding.reset),
        reference=understanding.reference,
        detail_kind=understanding.detail_kind,
        question=understanding.clarification,
    ) if understanding.clarification else None

    # 普通问答与事实读取是只读操作，不能重置或追加任何推荐条件。
    if understanding.intent == 'general' or understanding.operation in {'detail', 'answer'}:
        state.incremental_count = None
        return state

    # 用户明确要求取消的条件先清除；未提及的字段保持原样。
    for field in set(understanding.reset):
        if field == 'recommendation_count':
            state.recommendation_count = None
        elif field in {'meal_structure', 'meal_meat_count', 'meal_veg_count'}:
            state.meal_meat_count = None
            state.meal_veg_count = None
        elif field == 'required_foods':
            state.required_foods = None
        elif field == 'people':
            state.people = None
        elif field == 'cook_minutes':
            state.cook_minutes = None
        elif field == 'low_sodium':
            state.low_sodium = None
        elif field == 'selection_preferences':
            state.selection_preferences = []
        elif field == 'preferences':
            state.preferences = None
        elif field == 'health_goal':
            state.health_goal = None
        elif field == 'avoid':
            state.avoid_added = []
            state.avoid_removed = []
        elif field == 'excluded_categories':
            state.excluded_categories = []

    state.incremental_count = None
    if understanding.operation == 'new':
        # 新一餐不沿用上一餐的道数；长期忌口、人数等仍由「未提及保留」保护。
        state.recommendation_count = None

    simple_fields = (
        'people', 'cook_minutes', 'low_sodium', 'health_goal',
        'required_foods',
    )
    for field in simple_fields:
        value = getattr(slots, field)
        if value is not None:
            setattr(state, field, list(value) if isinstance(value, list) else value)

    if slots.dish_count is not None:
        if understanding.operation in {'add', 'replace'}:
            state.incremental_count = slots.dish_count
        else:
            state.recommendation_count = slots.dish_count
    if slots.meat_count is not None:
        state.meal_meat_count = slots.meat_count
    if slots.veg_count is not None:
        state.meal_veg_count = slots.veg_count
    if state.meal_meat_count is not None and state.meal_veg_count is not None:
        total = state.meal_meat_count + state.meal_veg_count
        if not 1 <= total <= 10:
            raise ValueError('荤素总数应为1至10道，请重新说明。')
        state.recommendation_count = total

    for field in ('selection_preferences', 'preferences', 'excluded_categories'):
        value = getattr(slots, field)
        if value is None:
            continue
        previous = getattr(state, field) or []
        setattr(state, field, list(dict.fromkeys([*previous, *value])))

    for term in slots.avoid_removed:
        state.avoid_added = [item for item in state.avoid_added if item != term]
        state.avoid_removed = list(dict.fromkeys([*state.avoid_removed, term]))
    for term in slots.avoid_added:
        state.avoid_removed = [item for item in state.avoid_removed if item != term]
        state.avoid_added = list(dict.fromkeys([*state.avoid_added, term]))

    return state
