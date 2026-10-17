"""Deterministic edits to the explicit constraints carried by a chat session."""
from __future__ import annotations

import re
from app.schemas.ai import AiConversationState

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


def edits(message: str, state: AiConversationState, terms: list[str]) -> AiConversationState:
    state = state.model_copy(deep=True)
    state.selection_preferences = selection_preferences(message, state.selection_preferences)
    count = requested_count(message)
    if count is not None:
        state.recommendation_count = count
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
        for term in terms:
            if not term or term not in clause:
                continue
            removed = bool(re.search(r"(?:取消|撤销|解除).*" + re.escape(term), clause)) or bool(
                re.search(re.escape(term) + r"(?:可以吃|能吃了|不再忌口)", clause)
            )
            if removed:
                state.avoid_added = [a for a in state.avoid_added if a != term]
                state.avoid_removed = list(dict.fromkeys([*state.avoid_removed, term]))
            elif any(t in clause for t in ("不吃", "不能吃", "过敏", "忌口", "别放", "不要放")):
                state.avoid_added = list(dict.fromkeys([*state.avoid_added, term]))
                state.avoid_removed = [a for a in state.avoid_removed if a != term]
    return state
