"""Conservative factual gate: unverified quantified/health claims are not prose."""
import re

_CLAIM = re.compile(
    r"保证|一定能|治疗|治愈|治好|降血压|降血糖|润肺|养胃|生津|滋补|补血|补益|抗癌|排毒|补气血|增强.*免疫|"
    r"低钠|低盐|少盐|低热量|低脂|均衡|看不到.*冰箱|手头.*食材|"
    r"[\d一二三四五六七八九十两半]+\s*(?:分钟|小时|人|道|克|毫克|卡路里|千卡|%)"
)


def checked_text(value: str | None, fallback: str) -> tuple[str, bool]:
    text = (value or '').strip()
    if not text or _CLAIM.search(text):
        return fallback, bool(text)
    return text, False
