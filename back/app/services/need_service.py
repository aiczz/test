"""需求解析：把用户的口语诉求变成**可执行的筛选条件**。

【为什么需要它】
用户说「我气血不足，想吃点补气血的」，原来的管线完全没有这个概念：
意图只有「闲聊 / 吃什么 / 用我的食材」三档，没有任何地方去理解「补气血」。
于是模型只能拿手里的时令/天气素材硬凑一段回答 —— 用户看到的自然是
「答非所问」。

而我们的清洗库里**本来就有这个信息**：`ingredients.effects_json` 里有
「补益气血」（鸡肉/核桃仁/山药/莲藕/莲子/猪心/鳝鱼…）、「益气养血」、
「润肺」、「健脾」、「安神」…… 实测 124 个核心食材带功效标签。

所以这一步做的事很具体：
    口语诉求 → 目标（goal）→ 一组功效关键词
    → 交给打分算法去匹配我们自己的 effects_json（而不是让模型自由发挥）

【边界】
· 只做**饮食偏好/食养方向**的匹配，不做诊断、不给治疗建议。
  用户说「气血不足」，我们只能把「有补益气血功效的食材」排前面，
  不能也不该宣称能治病 —— 提示词里也写死了这条。
· 匹配的是「食材本身带的功效标签」，不是模型的知识。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class HealthGoal:
    """解析出来的一个饮食诉求。"""

    name: str                    # 展示用，如「补气血」
    phrases: list[str] = field(default_factory=list)   # 用户可能怎么说
    effect_keywords: list[str] = field(default_factory=list)  # 拿去匹配 effects_json

    def as_prompt_line(self) -> str:
        return (
            f"用户明确表达了「{self.name}」的诉求。"
            f"请优先挑选带有这类功效的食材/菜品"
            f"（在我们的功效库里的关键词：{'、'.join(self.effect_keywords[:6])}），"
            "并在回答里围绕这个诉求说明，不要只讲时令和天气。"
        )


# =====================================================================
# 诉求词典
#
# ⚠️ effect_keywords 全部来自我们**实际库里的 effects_json 取值**
#    （已核对存在，见 docs/算法与AI设计.md）。不是凭空写的近义词表 ——
#    写一个库里没有的词等于永远匹配不上，这类 bug 很隐蔽。
# =====================================================================
_GOALS: list[HealthGoal] = [
    HealthGoal(
        name="补气血",
        phrases=[
            "补气血", "气血不足", "气血两虚", "气血亏", "气血虚", "补血", "养血",
            "贫血", "气色差", "面色差", "脸色差", "体虚",
        ],
        effect_keywords=[
            "补气血", "补益气血", "益气养血", "气血双补", "养血", "补血",
            "调理气血", "滋阴养血", "补肾养血", "补虚养身", "滋补",
        ],
    ),
    HealthGoal(
        name="健脾养胃",
        phrases=[
            "健脾", "养胃", "脾胃", "肠胃不好", "消化不好", "胃口差",
            "食欲不振", "积食", "胃不好",
        ],
        effect_keywords=["健脾", "养胃", "补脾", "健胃", "开胃", "消食", "导滞", "健脾宽中"],
    ),
    HealthGoal(
        name="润燥润肺",
        phrases=["润燥", "润肺", "嗓子干", "咽干", "口干", "咳嗽", "秋燥", "干燥"],
        effect_keywords=["润肺", "润燥", "生津", "止咳", "滋阴", "润心肺", "生津止渴"],
    ),
    HealthGoal(
        name="清热降火",
        phrases=["上火", "清热", "降火", "火气", "燥热", "长痘", "口疮"],
        effect_keywords=["清热", "降火", "解毒", "清热润燥", "清热降火", "消暑"],
    ),
    HealthGoal(
        name="安神助眠",
        phrases=["失眠", "睡不好", "睡不着", "助眠", "安神", "多梦", "睡眠"],
        effect_keywords=["安神", "养心", "宁心", "安神助眠"],
    ),
    HealthGoal(
        name="明目护眼",
        phrases=["明目", "护眼", "眼睛", "视力", "眼干"],
        effect_keywords=["明目", "益目", "护眼", "保护眼睛", "补肝"],
    ),
    HealthGoal(
        name="低脂减重",
        phrases=["减肥", "瘦身", "减脂", "低脂", "控制体重", "轻食", "热量低"],
        effect_keywords=["瘦身", "减肥", "低脂"],
    ),
    HealthGoal(
        name="增强免疫",
        phrases=["免疫力", "抵抗力", "容易感冒", "增强体质", "体质差"],
        effect_keywords=["免疫", "增强正气", "强身健体", "增强人体免疫力"],
    ),
    HealthGoal(
        name="祛湿利水",
        phrases=["祛湿", "湿气", "水肿", "去湿", "利水"],
        effect_keywords=["祛湿", "利湿", "去湿", "利水", "消肿"],
    ),
    HealthGoal(
        name="补肾强腰",
        phrases=["补肾", "肾虚", "腰膝酸软", "腰酸"],
        effect_keywords=["补肾", "补肾益气", "补肾养血", "壮腰", "补元气"],
    ),
    HealthGoal(
        name="补钙强骨",
        phrases=["补钙", "骨质疏松", "强骨", "长个子"],
        effect_keywords=["补钙", "强健骨骼"],
    ),
]


def all_goals() -> list[HealthGoal]:
    return _GOALS


def extract_goal(message: str) -> HealthGoal | None:
    """从用户这句话里解析出诉求。解析不到返回 None。

    匹配规则：命中最长的短语优先 —— 避免「补血」抢先命中「补气血」这种
    子串关系导致的错误归类。
    """
    if not message:
        return None

    best: tuple[int, HealthGoal] | None = None
    for goal in _GOALS:
        for phrase in goal.phrases:
            if phrase in message:
                if best is None or len(phrase) > best[0]:
                    best = (len(phrase), goal)
    return best[1] if best else None


def effect_keywords_of(goal: HealthGoal | None) -> list[str]:
    return list(goal.effect_keywords) if goal else []


def goal_fit(effect_tags: set[str], keywords: list[str]) -> float:
    """这个食材/菜品和诉求的契合度（0~1）。

    `effect_tags` 是该食材（或菜品所有食材）的功效标签集合。
    命中 2 个关键词就算满分 —— 再多没有额外信息量。
    """
    if not keywords or not effect_tags:
        return 0.0
    hits = sum(1 for keyword in keywords if any(keyword in tag for tag in effect_tags))
    return min(hits / 2.0, 1.0)
