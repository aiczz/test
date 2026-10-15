"""Extract explicit step timings, preserving long waits and original evidence."""
import math
import re

_NUMBER = r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千零两]+|半)"
_TIME = re.compile(rf"(?P<a>{_NUMBER})(?:\s*[-~～—至到]\s*(?P<b>{_NUMBER}))?\s*(?:个)?\s*(?P<preshalf>半)?\s*(?P<unit>小时|分钟|分(?=[，。；、\s]|即可|后|左右|再|取出|关火|$)|刻钟)(?P<half>半)?(?:\s*(?P<extra>{_NUMBER})\s*分钟)?")


def number(value: str) -> float:
    if value == '半':
        return .5
    try:
        return float(value)
    except ValueError:
        digits = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
                  '六': 6, '七': 7, '八': 8, '九': 9}
        if value in digits:
            return digits[value]
        digits['零'] = 0
        total = current = 0
        for char in value:
            if char in digits:
                current = digits[char]
            elif char in {'十', '百', '千'}:
                total += (current or 1) * {'十': 10, '百': 100, '千': 1000}[char]
                current = 0
            else:
                raise ValueError(value)
        if total or current:
            return total + current
        raise ValueError(value)


def duration_evidence(text: str | None) -> list[tuple[str, int]]:
    evidence = []
    for match in _TIME.finditer(text or ''):
        try:
            value = max(number(match['a']), number(match['b'] or match['a']))
            value *= 60 if match['unit'] == '小时' else 15 if match['unit'] == '刻钟' else 1
            if (match['half'] or match['preshalf']) and match['unit'] == '小时':
                value += 30
            if match['extra'] and match['unit'] == '小时':
                value += number(match['extra'])
            if value > 0:
                evidence.append((match[0], math.ceil(value)))
        except ValueError:
            continue
    return evidence


def duration_from_text(text: str | None) -> int | None:
    values = duration_evidence(text)
    return max((value for _, value in values), default=None)
