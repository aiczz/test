"""Conservative factual gate — sentence-level repair, not wholesale rejection.

【为什么改】旧版一发现功效词（润肺/补血/补气血…）就把整段回答扔掉，
退回机械拼装。但那些词恰恰是食养场景里模型**被提示词要求说**的——
用户问「滋阴补血」，模型答得越专业越容易被毙。而且现在模型手里的
功效/营养数据全部来自候选行的真实数据，功效词早已不是"凭空宣称"。

新版策略：
- 硬医疗承诺（治好/治愈/消炎/退烧/降血压…）——仍然零容忍，但只丢
  含它的那一**句**，其余句子保留；
- 数量/时长——只拦「候选行里没有的数」：模型被要求引用候选数据，
  引用的数字放行，编造的数字连句子一起丢（grounded_numbers 由调用方
  用候选行文本构建）；
- 一句都保不住时才退回 fallback。
"""

import re

# 硬医疗承诺：食养建议绝不能出现的词，出现即丢句。
_HARD_CLAIM = re.compile(
    r"保证|一定能|包治|根治|治疗|治愈|治好|消炎|退烧|降血压|降血糖|抗癌|排毒|"
    r"看不到.*冰箱|手头.*食材"
)

# 未落地的数量：只拦时间/重量/热量这类"可以说错"的量。
# 道数、人数另有确定性校验（数量确认、结果校验），不在这里拦。
_QUANTITY = re.compile(
    r"[\d一二三四五六七八九十两半][\d.一二三四五六七八九十两半]*\s*"
    r"(?:分钟|小时|克|毫克|卡路里|千卡|kcal|mg|g)(?![A-Za-z])"
)


def grounded_numbers_of(*texts: str) -> set[str]:
    """从候选行等已核实的文本里提取全部数量 token，供 checked_text 放行。"""
    grounded: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in _QUANTITY.finditer(text):
            grounded.add(match.group(0).strip())
    return grounded


def checked_text(
    value: str | None,
    fallback: str,
    grounded_numbers: set[str] | None = None,
) -> tuple[str, bool]:
    """逐句体检模型回答：硬承诺句直接丢，编造数量的句直接丢。

    返回 (修复后的文本, 是否丢过句)。一句都保不住时退回 fallback。
    """
    text = (value or '').strip()
    if not text:
        return fallback, False

    sentences = [s for s in re.split(r'(?<=[。！？；;])', text) if s.strip()]
    kept: list[str] = []
    rejected = False
    for sentence in sentences:
        if _HARD_CLAIM.search(sentence):
            rejected = True
            continue
        invented = [
            m.group(0)
            for m in _QUANTITY.finditer(sentence)
            if not (grounded_numbers and m.group(0).strip() in grounded_numbers)
        ]
        if invented:
            rejected = True
            continue
        kept.append(sentence)

    repaired = ''.join(kept).strip()
    if not repaired:
        return fallback, True
    return repaired, rejected
