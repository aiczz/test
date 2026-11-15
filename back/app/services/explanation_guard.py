"""Conservative factual gate: unverified quantified/health claims are not prose."""
import re

_CLAIM = re.compile(
    r"保证|一定能|治疗|治愈|治好|降血压|降血糖|润肺|养胃|生津|滋补|补血|补益|抗癌|排毒|补气血|增强.*免疫|"
    r"低钠|低盐|少盐|低热量|低脂|均衡|看不到.*冰箱|手头.*食材|"
    # 只拦真正可能说错的量：时间/重量/热量。道数、人数另有确定性校验
    # （数量确认、结果校验），拦在这里会把每句正常的"挑了 3 道"都毙掉。
    r"[\d一二三四五六七八九十两半]+\s*(?:分钟|小时|克|毫克|卡路里|千卡|%)"
)


def checked_text(value: str | None, fallback: str) -> tuple[str, bool]:
    text = (value or '').strip()
    if not text or _CLAIM.search(text):
        return fallback, bool(text)
    return text, False
