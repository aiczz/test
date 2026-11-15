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

    # ★ 「这个诉求本质上是**营养**需求，不是中医功效需求」的标记。
    #
    # 为什么需要它：`effects_json` 是中医功效词（补气血 / 健脾 / 润肺…），
    # 里面几乎没有营养学词汇 —— 实测全库只有 **1 条**「补充蛋白质」。
    # 所以「健身要补蛋白」这种诉求，靠 effect_keywords 是匹配不到东西的，
    # 必须改用「每 100g 蛋白质含量」来排。不处理的话，
    # 用户说「家里有健身的」，推出来的还是山药和石榴。
    prefer_high_protein: bool = False

    # ★ 「这个诉求要排除哪些口味/做法/食材」。
    #
    # 这是为了让推荐**自洽**的关键。比如用户说「润燥润肺」，
    # 我们不能一边推润肺的雪梨，一边又推带青红椒/辣椒/咖喱的刺激菜
    # —— 虽然青红椒炒鱿鱼的配料里有鱿鱼（滋阴）被功效匹配到了，
    # 但青红椒本身会加重燥热，和「润燥」是矛盾的。
    #
    # 只写**标签命中**即可：硬约束掩码会检查 DishInsight.tags 和
    # DishInsight.main_ingredients，命中其中任何一个就踢出候选。
    exclude_tags: list[str] = field(default_factory=list)

    def as_prompt_line(self) -> str:
        if self.prefer_high_protein:
            return (
                f"用户明确表达了「{self.name}」的诉求，这是**营养**需求。"
                "请优先挑选蛋白质含量高的食材/菜品，"
                "并在回答里围绕蛋白质、修复与增肌来说明，不要只讲时令和天气。"
            )
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
        # 脾胃弱的时候，辣/油炸/生冷都会加重负担
        exclude_tags=["辣", "麻辣", "香辣", "辣椒", "油炸", "生冷"],
    ),
    HealthGoal(
        name="润燥润肺",
        phrases=["润燥", "润肺", "嗓子干", "咽干", "口干", "咳嗽", "秋燥", "干燥", "嗓子疼", "润喉"],
        effect_keywords=["润肺", "润燥", "生津", "止咳", "滋阴", "润心肺", "生津止渴"],
        # 嗓子/喉咙不舒服的时候，任何刺激性的东西都会雪上加霜
        exclude_tags=["辣", "麻辣", "香辣", "青红椒", "辣椒", "泡椒", "咖喱", "芥末", "花椒"],
    ),
    HealthGoal(
        name="清热降火",
        phrases=["上火", "清热", "降火", "火气", "燥热", "长痘", "口疮"],
        effect_keywords=["清热", "降火", "解毒", "清热润燥", "清热降火", "消暑"],
        # 火气大的时候吃油炸/烘烤会加重，辛辣本身就是"上火"的来源
        exclude_tags=["辣", "麻辣", "香辣", "辣椒", "油炸", "红烧", "咖喱"],
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
        name="健身增肌",
        phrases=[
            "健身", "增肌", "长肌肉", "练肌肉", "撸铁", "高蛋白", "补蛋白",
            "蛋白质", "增重", "长身体", "运动后", "练完",
        ],
        # ⚠️ 这几个是库里**真实存在**的、勉强沾边的功效词（数量很少）。
        #    真正起作用的排序是下面的 prefer_high_protein ——
        #    靠每 100g 蛋白质含量排，而不是靠中医功效词。
        effect_keywords=["补虚养身", "补虚强身", "强身健体", "补充蛋白质", "养血强身"],
        prefer_high_protein=True,
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


def extract_goal_semantic(message: str) -> HealthGoal | None:
    """关键词优先，命中不了再用向量找最近邻诉求。

    【为什么要有这一层】
    用户说「嗓子疼想喝点润喉的」——「嗓子疼」「润喉」都不在 phrases 里，
    关键词路径判成无诉求，最后推出来的是土豆炖排骨。
    向量匹配能把这句话落到「润燥润肺」上（实测余弦 0.66）。

    【为什么先走关键词】
    关键词是确定性的，向量是概率性的。能确定的时候就不该交给概率。
    只有关键词判不出来时才多花一次 embedding 调用（约 0.3~1s）。
    """
    goal = extract_goal(message)
    if goal is not None:
        return goal
    if not message or not message.strip():
        return None
    try:
        from app.services.retrieval.embed_client import embed_text, is_embedding_configured
        from app.services.retrieval.goal_index import get_goal_index

        if not is_embedding_configured():
            return None
        index = get_goal_index()
        if not index.available:
            return None
        vector = embed_text(message.strip())
        if vector is None:
            return None
        hit = index.match(vector)
        if hit is None:
            return None
        name, _sim = hit
        return next((g for g in _GOALS if g.name == name), None)
    except Exception:  # noqa: BLE001 —— 向量只是增强，绝不能让需求解析挂掉
        return None


def effect_keywords_of(goal: HealthGoal | None) -> list[str]:
    return list(goal.effect_keywords) if goal else []


def goal_fit(effect_tags: set[str], keywords: list[str]) -> float:
    """这个食材/菜品和诉求的契合度（0~1）。

    `effect_tags` 是该食材（或菜品所有食材）的功效标签集合。

    【为什么按「匹配精度」算，而不是数命中了几个】
    effects_json 里有大量宽泛标签，比如猪肉的「滋阴润燥」——
    它同时命中「滋阴」和「润燥」。更要命的是菜品功效是**所有配料取并集**：
    一道麻辣香锅有十几样配料，随便都能凑出 3 个相关标签，
    于是「嗓子疼想润喉」推出来的是麻辣香锅。
    改成 命中数 ÷ 该菜总标签数（精度），配料越多分母越大，
    真正靠主料对症的菜（雪梨、川贝、银耳）才能浮上来。
    """
    if not keywords or not effect_tags:
        return 0.0
    matched = {tag for tag in effect_tags if any(keyword in tag for keyword in keywords)}
    if not matched:
        return 0.0
    precision = len(matched) / max(len(effect_tags), 2)
    return min(precision * 3.0, 1.0)
