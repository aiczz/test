"""Normalize source numbering without splitting quantities or decimal numbers."""
import re

_NUM = r"[0-9０-９一二三四五六七八九十百零〇两]+"
_MARKER = re.compile(
    rf"(?<![0-9０-９一二三四五六七八九十百零〇两])"
    rf"(?:第\s*(?P<ordinal>{_NUM})\s*步\s*[：:、.．]?|"
    rf"(?P<number>{_NUM})\s*[、.．:：](?![0-9０-９]))"
)


def clean_step_description(value: str) -> str:
    value = value.strip()
    marker = _MARKER.match(value)
    return value[marker.end():].strip() if marker else value


def _number(value: str) -> int | None:
    if value.isdecimal():
        return int(value)
    digits = {char: index for index, char in enumerate("零一二三四五六七八九")}
    if value in digits:
        return digits[value]
    if value.count("十") == 1 and "百" not in value:
        tens, units = value.split("十")
        if (not tens or tens in digits) and (not units or units in digits):
            return digits.get(tens, 1) * 10 + digits.get(units, 0)
    return None


def parse_recipe_steps(instruction: str) -> list[str]:
    text = instruction.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    markers = []
    previous = None
    for marker in _MARKER.finditer(text):
        number = _number(marker.group("ordinal") or marker.group("number"))
        line_start = not text[text.rfind("\n", 0, marker.start()) + 1:marker.start()].strip()
        # Inline numbering must advance in sequence. A bare number in a
        # sentence (ratios, amounts, times) is not a new step.
        if line_start or (previous is not None and number == previous + 1):
            markers.append(marker)
            previous = number
    if not markers:
        return [line.strip() for line in text.split("\n") if line.strip()]
    parts = []
    prefix = text[:markers[0].start()].strip()
    if prefix:
        parts.append(prefix)
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        part = text[marker.end():end].strip()
        if part:
            parts.append(part)
    return parts
