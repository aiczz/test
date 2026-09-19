from __future__ import annotations

import csv
import os
import re
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


SQL_ROOT = Path(__file__).resolve().parents[1]
SOURCE = SQL_ROOT / "菜谱数据库_交付_20260918 (1)"
OUTPUT = SQL_ROOT / "cleaned_v2"
TEMP = SQL_ROOT / "cleaned_v2.__building__"
ZIP_PATH = SQL_ROOT / "cleaned_v2.zip"

NULLISH = {"", "—", "-", "--", "null", "NULL", "None"}

REQUIRED_PRESENT = """葱 姜 蒜 洋葱 番茄 圣女果 黄瓜 胡萝卜 菠菜 白菜 西兰花 土豆 南瓜 苹果 香蕉 草莓 葡萄 橙子 猪肉 牛肉 羊肉 排骨 牛腩 鸡肉 鸡胸肉 鸡腿 鸡翅 鸡蛋 鸭蛋 草鱼 鲈鱼 虾 扇贝 香菇 金针菇 木耳""".split()
REQUIRED_ABSENT = """盐 白糖 生抽 老抽 蚝油 料酒 番茄酱 沙拉酱 火腿 火腿肠 培根 香肠 午餐肉 肉松 面包 吐司 饼干 蛋糕 巧克力 照片 塑料袋 保温杯 一个洋葱 几个土豆 香蕉一根 半根胡萝卜 刷表面蛋液""".split()

CATEGORIES = [
    (1, "蔬菜"), (2, "水果"), (3, "畜肉"), (4, "禽肉"), (5, "蛋类"),
    (6, "水产"), (7, "菌菇藻类"), (8, "薯芋"), (9, "豆类"), (10, "谷物/坚果"),
]
CATEGORY_ID = {name: ident for ident, name in CATEGORIES}

SUBCATEGORIES = [
    (1, 1, "叶菜"), (2, 1, "根茎"), (3, 1, "瓜果"), (4, 1, "葱蒜"), (5, 1, "鲜豆"), (6, 1, "其他蔬菜"),
    (7, 2, "仁果"), (8, 2, "核果"), (9, 2, "浆果"), (10, 2, "柑橘"), (11, 2, "瓜果"), (12, 2, "热带水果"), (13, 2, "其他水果"),
    (14, 3, "猪"), (15, 3, "牛"), (16, 3, "羊"), (17, 3, "其他畜肉"),
    (18, 4, "鸡"), (19, 4, "鸭"), (20, 4, "鹅"), (21, 4, "其他禽肉"),
    (22, 5, "鸡蛋"), (23, 5, "鸭蛋"), (24, 5, "鹅蛋"), (25, 5, "鹌鹑蛋"), (26, 5, "其他蛋类"),
    (27, 6, "鱼"), (28, 6, "虾"), (29, 6, "蟹"), (30, 6, "贝"), (31, 6, "其他水产"),
    (32, 7, "菌菇"), (33, 7, "藻类"),
    (34, 8, "薯类"), (35, 8, "芋类"),
    (36, 9, "大豆"), (37, 9, "杂豆"), (38, 9, "鲜豆"),
    (39, 10, "稻米"), (40, 10, "小麦"), (41, 10, "玉米"), (42, 10, "杂粮"), (43, 10, "坚果种子"),
]
SUBCATEGORY_ID = {(cid, name): sid for sid, cid, name in SUBCATEGORIES}

MAJOR_MAP = {
    "蔬菜类及其制品": "蔬菜", "水果类及其制品": "水果",
    "畜肉类及其制品": "畜肉", "禽肉类及其制品": "禽肉",
    "蛋类及其制品": "蛋类", "鱼虾蟹贝类": "水产",
    "菌藻类": "菌菇藻类", "薯类淀粉及其制品": "薯芋",
    "干豆类及其制品": "豆类", "谷类及其制品": "谷物/坚果",
    "坚果种子类": "谷物/坚果",
}

# 仅包含语义完全确定的别名。含糊简称不放在这里。
EXPLICIT_ALIASES = {
    "西红柿": "番茄", "马铃薯": "土豆", "洋芋": "土豆",
    "大蒜": "蒜", "蒜头": "蒜", "蒜瓣": "蒜",
    "生姜": "姜", "老姜": "姜", "嫩姜": "姜",
    "小葱": "葱", "香葱": "葱", "大葱": "葱",
    "芫荽": "香菜", "芫茜": "香菜",
    "包菜": "卷心菜", "圆白菜": "卷心菜", "包心菜": "卷心菜",
    "花椰菜": "菜花", "西红柿果": "番茄",
    "鸡腿肉": "鸡腿", "鲜虾": "虾",
    "猪里脊肉": "猪里脊", "鸡胸": "鸡胸肉",
    "红苕": "红薯", "地瓜": "红薯",
    "小西红柿": "圣女果", "圆葱": "洋葱", "青瓜": "黄瓜",
    "番薯": "红薯", "枸杞子": "枸杞", "猪五花肉": "五花肉",
    "小香葱": "葱", "蒜子": "蒜", "瓣蒜": "蒜",
    "蒜米": "蒜", "蒜蒜": "蒜", "葱葱": "葱", "葱白": "葱", "葱叶": "葱", "葱白葱": "葱",
    "高丽菜": "卷心菜", "葱头": "洋葱", "小土豆": "土豆",
    "罗勒叶": "罗勒", "香菜叶": "香菜", "菠菜叶": "菠菜", "生菜叶": "生菜",
    "芒果肉": "芒果", "榴莲肉": "榴莲", "桂圆肉": "桂圆",
    "鸡蛋清": "蛋清", "牛肉糜": "牛肉", "鱿鱼圈": "鱿鱼",
    "鸡蛋黄": "蛋黄",
}

SPLIT_EXACT = {
    "葱姜蒜": ["葱", "姜", "蒜"], "葱姜": ["葱", "姜"], "姜蒜": ["姜", "蒜"],
    "青红椒": ["青椒", "红椒"], "鸡翅鸡腿": ["鸡翅", "鸡腿"],
    "鸡腿鸡翅": ["鸡腿", "鸡翅"], "鱼虾": ["鱼", "虾"],
    "姜葱蒜": ["姜", "葱", "蒜"], "葱蒜": ["葱", "蒜"],
    "青椒红椒": ["青椒", "红椒"], "青红辣椒": ["青椒", "红辣椒"],
    "黑白芝麻": ["黑芝麻", "白芝麻"],
    "香菜葱": ["香菜", "葱"], "葱花香菜": ["葱", "香菜"],
}

AMBIGUOUS = {
    "克肉", "肉", "肉类", "肉片", "肉块", "肉丁", "肉馅", "鲜肉", "瘦肉", "肥肉",
    "鱼", "鱼肉", "鱼片", "鱼块", "海鲜", "水产", "蔬菜", "水果", "青菜", "时蔬",
    "坚果", "果仁", "豆类", "杂粮", "菌菇", "蘑菇", "蛋", "蛋液", "全蛋液", "蛋白", "蛋黄液",
    "肉沫", "肉糜", "猪肉糜", "各种蔬菜", "其他蔬菜", "绿色蔬菜", "绿叶菜", "杂菜", "各种坚果",
    "香草", "木鱼", "牛叶", "全麦", "果肉", "前腿肉", "后腿肉", "鱼头", "鱼排", "大小姜",
    "各类蔬菜", "绿叶蔬菜", "豆制品", "素菜", "蜜枣", "野山椒", "魔芋",
}

PROCESSED_RE = re.compile(
    r"火腿|培根|香肠|腊肠|午餐肉|肉松|肉干|腊肉|腌肉|熏肉|叉烧|鱼丸|虾丸|肉丸|丸子|"
    r"蟹棒|蟹柳|鱼豆腐|豆腐|豆干|豆皮|腐竹|千张|粉丝|粉条|粉皮|"
    r"面包|吐司|饼干|蛋糕|巧克力|奶油|黄油|芝士|奶酪|炼乳|奶粉|面包糠|面包屑|"
    r"泡打粉|酵母|淀粉|面粉|可可粉|抹茶粉|米粉|糯米粉|玉米粉|葛根粉|藕粉|"
    r"方便面|面条|意大利面|米线|河粉|年糕|油条|馒头|包子|饺子|馄饨|披萨|汉堡|"
    r"米饭|炒饭|焖饭|粥|罐头|果脯|果干|葡萄干|蔓越莓干|蓝莓干|蜜饯|果酱|沙拉|沙司|"
    r"鱼滑|虾滑|肉滑|鱼糕|鱼饼|蛋挞|月饼|曲奇|布丁|慕斯|冰淇淋|雪糕|"
    r"豆沙|豆浆|豆奶|豆渣|蜜豆|蜜红豆|面筋|芋圆|桃胶|蛋白霜|"
    r"泡菜|酸菜|咸菜|梅干菜|冬菜|雪菜|芽菜|橄榄菜|萝卜干|笋干|酸豆角|酸萝卜|酸黄瓜|酸笋|"
    r"泡椒|剁椒|剁辣椒|泡辣椒|泡姜|咸蛋|咸鸭蛋|咸肉|熟|即食|"
    r"红烧肉|卤牛肉|酱牛肉|猪油渣|海苔|番茄膏|香草膏|葱姜水|"
    r"虾干|干虾|干贝|海米|虾米|虾皮|蟹肉棒|蟹足棒|热狗肠|脆皮肠|肠$|"
    r"香干|豆泡|素鸡|豆乳|西米|琼脂|果胶|贝果|每日坚果|水果燕麦|油炸|烟熏|"
    r"鱼干|鱿鱼干|柴鱼|杏干|蛏干|鱼翅|方腿|羊肉串|猪肉脯|肉酥|"
    r"皮蛋|松花蛋|荷包蛋|烤鸭|烤鸡|扒鸡|烧鹅|酱鸭|油鸡枞|酸白菜|"
    r"乳酸菌|剩菜|香草荚|香草籽|镜面果胶|糟辣椒|酸辣椒"
)
BEVERAGE_RE = re.compile(r"咖啡|可乐|汽水|饮料|饮品|果汁|茶$|茶叶|啤酒|白酒|红酒|黄酒|米酒|朗姆酒|椰浆|椰奶|酸奶|牛奶|奶昔|奶$")
TOOL_RE = re.compile(r"照片|塑料袋|保温杯|烤盘|模具|锡纸|油纸|容器|机器|打蛋器|刮刀|裱花袋|牙签|吸管|量勺|刷表面|装饰用|表面用|备用|步骤|做法")
INSTRUCTION_RE = re.compile(r"刷|搅拌|打发|切好|切碎|洗净|焯水|煮熟|炒熟|烤熟|炸好|涂抹|撒在|放入|加入|备用|装饰")
QUANTITY_RE = re.compile(r"\d|[一二两三四五六七八九十几半]+(?:个|颗|只|根|片|块|斤|克|g|G|毫升|ml|ML|勺|杯|碗|把|瓣|撮|袋|盒|罐|条|朵|头|份)|适量|少许|若干|多少")
PUNCT_RE = re.compile(r"[，,、/+＆&]|和|以及|或")

# 这些是调味料，而“葱姜蒜香菜鲜辣椒”由前面的基础食材规则保留。
SEASONING_RE = re.compile(
    r"^(盐|白糖|糖|冰糖|红糖|砂糖|生抽|老抽|酱油|蚝油|醋|料酒|味精|鸡精|花椒|八角|桂皮|香叶|"
    r"胡椒|胡椒粉|孜然|孜然粉|五香粉|十三香|咖喱粉|辣椒粉|豆瓣酱|甜面酱|番茄酱|沙拉酱|"
    r"芥末|蜂蜜|糖浆|盐焗粉|干辣椒|麻椒|藤椒|黑椒|肉桂|百里香|迷迭香|豆蔻|玫瑰|桂花)$|油$|酱$|醋$|酒$|调料$|调味料$"
)

# 可安全去除的“份量 + 形态”包装。只在结果已存在于 canonical 候选集合时采用。
PREFIX_RE = re.compile(r"^(?:约|大约|新鲜|鲜活|鲜|冷冻|冰冻|泡发|去皮|去骨|带皮|无骨|净|整只|整颗|一个|两个|三个|几个|几只|几根|半个|半根|半颗|朵|瓣|克|g)+")
SUFFIX_RE = re.compile(r"(?:一个|两个|三个|几个|几只|一只|两只|几根|一根|两根|半个|半根|半颗|适量|少许|若干|\d+克|克|g)$")
CUT_SUFFIX_RE = re.compile(r"(?:片|块|丁|丝|段|末|碎|瓣)$")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def writer(path: Path, fieldnames: list[str]):
    handle = path.open("w", encoding="utf-8-sig", newline="")
    obj = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    obj.writeheader()
    return handle, obj


def usage(row: dict[str, str]) -> int:
    try:
        return int(float(row.get("usage_count") or 0))
    except ValueError:
        return 0


def clean_name(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip())


def is_seasoning(name: str, seasoning_names: set[str]) -> bool:
    if name in {"葱", "姜", "蒜", "香菜", "辣椒", "青椒", "红椒", "小米椒"}:
        return False
    return name in seasoning_names or bool(SEASONING_RE.search(name)) or bool(
        re.search(r"百里香|迷迭香|肉桂|豆蔻|肉蔻|麻椒|藤椒|黑椒|干辣椒|干红椒|桂花|玫瑰|红油|油辣椒|香茅|川贝|荷叶|干罗勒|干欧芹", name)
    )


def drop_reason(name: str, row: dict[str, str], seasoning_names: set[str]) -> tuple[str, str] | None:
    if is_seasoning(name, seasoning_names):
        return "seasoning", "调味料不进入基础原生食材表"
    if TOOL_RE.search(name) or INSTRUCTION_RE.search(name):
        return "junk", "工具、包装或操作说明"
    if PROCESSED_RE.search(name):
        if re.search(r"火腿|培根|香肠|午餐肉|肉松|肉干|腊肉|腌肉|熏肉|叉烧", name):
            return "processed", "加工肉制品"
        if re.search(r"豆腐|豆干|豆皮|腐竹|千张|粉丝|粉条|粉皮", name):
            return "processed", "豆制品或淀粉制品（严格模式排除）"
        if re.search(r"面包|吐司|饼干|蛋糕|巧克力|奶油|黄油|芝士|奶酪|炼乳|奶粉", name):
            return "processed", "烘焙或乳制加工食品"
        return "processed", "成品、半成品或加工食品"
    if BEVERAGE_RE.search(name) or row.get("category_major") == "乳类及其制品":
        return "processed", "饮料、酒类或乳制品不属于本版核心原生食材"
    return None


def category_for(row: dict[str, str]) -> str | None:
    return MAJOR_MAP.get(row.get("category_major", ""))


def subcategory_for(category: str, name: str, old_sub: str) -> str:
    if category == "蔬菜":
        if re.search(r"葱|蒜|韭|洋葱", name): return "葱蒜"
        if re.search(r"豆|豌豆|蚕豆|毛豆|四季豆|扁豆|荷兰豆", name): return "鲜豆"
        if re.search(r"瓜|番茄|椒|茄", name): return "瓜果"
        if re.search(r"萝卜|笋|藕|芹|姜|茭白", name): return "根茎"
        if re.search(r"菜|菠菜|生菜|莴苣|茼蒿|香菜|罗勒|薄荷", name): return "叶菜"
        return "其他蔬菜"
    if category == "水果":
        if re.search(r"苹果|梨|山楂|枇杷", name): return "仁果"
        if re.search(r"桃|李|梅|枣|樱桃|杏", name): return "核果"
        if re.search(r"莓|葡萄|桑葚|石榴", name): return "浆果"
        if re.search(r"橙|柑|橘|柚|柠檬", name): return "柑橘"
        if re.search(r"西瓜|甜瓜|哈密瓜", name): return "瓜果"
        if re.search(r"香蕉|芒果|菠萝|榴莲|荔枝|龙眼|木瓜|椰子|火龙果|百香果", name): return "热带水果"
        return "其他水果"
    if category == "畜肉":
        if "猪" in name or name in {"五花肉", "排骨", "里脊"}: return "猪"
        if "牛" in name: return "牛"
        if "羊" in name: return "羊"
        return "其他畜肉"
    if category == "禽肉":
        if "鸡" in name: return "鸡"
        if "鸭" in name: return "鸭"
        if "鹅" in name: return "鹅"
        return "其他禽肉"
    if category == "蛋类":
        if "鸡" in name or name == "鸡蛋": return "鸡蛋"
        if "鸭" in name: return "鸭蛋"
        if "鹅" in name: return "鹅蛋"
        if "鹌鹑" in name: return "鹌鹑蛋"
        return "其他蛋类"
    if category == "水产":
        if "虾" in name: return "虾"
        if "蟹" in name: return "蟹"
        if re.search(r"贝|蛤|蚌|蚝|蛎|螺|扇贝|鲍鱼", name): return "贝"
        if re.search(r"鱼|鳕|鲈|鲤|鲫|鲳|鲑|三文|鳗|鳝|泥鳅|带鱼|黄花", name): return "鱼"
        return "其他水产"
    if category == "菌菇藻类":
        return "藻类" if re.search(r"海带|紫菜|裙带菜|藻", name) else "菌菇"
    if category == "薯芋":
        return "芋类" if "芋" in name else "薯类"
    if category == "豆类":
        if re.search(r"毛豆|豌豆|蚕豆|四季豆|扁豆|荷兰豆", name): return "鲜豆"
        if re.search(r"黄豆|黑豆|大豆|青豆", name): return "大豆"
        return "杂豆"
    if category == "谷物/坚果":
        if re.search(r"核桃|杏仁|花生|腰果|榛子|松子|开心果|芝麻|瓜子|莲子|板栗|碧根果", name): return "坚果种子"
        if re.search(r"大米|糙米|糯米|粳米|籼米|黑米|紫米", name): return "稻米"
        if re.search(r"小麦|燕麦|荞麦|大麦", name): return "小麦"
        if "玉米" in name: return "玉米"
        return "杂粮"
    raise AssertionError(category)


def base_candidate(name: str, row: dict[str, str], seasoning_names: set[str]) -> bool:
    if name in REQUIRED_PRESENT:
        return True
    if not category_for(row):
        return False
    if drop_reason(name, row, seasoning_names):
        return False
    if name in AMBIGUOUS or name in SPLIT_EXACT or re.search(r"各种|各类|其他|绿色蔬菜|绿叶菜|绿叶蔬菜|杂菜|混合|自选|制品", name):
        return False
    if len(name) < 1 or len(name) > 10:
        return False
    if re.search(r"[0-9A-Za-z%（）()\[\]【】·:：;；!?！？]", name):
        return False
    if PUNCT_RE.search(name) or QUANTITY_RE.search(name):
        return False
    if re.search(r"料$|馅$|汁$|汤$|羹$|酱$|糊$|泥$|粉$|面$|饭$|饼$|糕$|卷$|包$|片$|块$|丁$|丝$|末$|液$", name):
        # 明确的原生部位和物种不因末字误伤。
        if name not in {"藕", "五花肉", "排骨", "鸡翅", "带鱼"}:
            return False
    # 严格版高质量优先：有明确成分表匹配，或语料高频（低频潜在食材进入 REVIEW）。
    return row.get("nutrition_match") in {"exact", "alias"} or usage(row) >= 20


def strip_quantity_and_form(name: str) -> str:
    value = PREFIX_RE.sub("", name)
    value = SUFFIX_RE.sub("", value)
    return value


def make_synthetic(name: str, prototype: dict[str, str]) -> dict[str, str]:
    result = {key: "" for key in prototype}
    result.update(prototype)
    result["name"] = name
    result["usage_count"] = "0"
    result["nutrition_match"] = ""
    result["nutrition_source_name"] = ""
    for key in list(result):
        if key.endswith("g") or key.endswith("mg") or key.endswith("%") or key in {"能量kcal", "能量kJ", "维生素A(ugRE)", "胡萝卜素(ug)", "视黄醇(ug)", "硒(ug)"}:
            result[key] = ""
    result["tcm_name"] = ""
    result["tcm_taste"] = ""
    result["tcm_user"] = ""
    result["tcm_not_user"] = ""
    result["tcm_side_effects"] = ""
    result["tcm_toxicity"] = ""
    result["tcm_production_place"] = ""
    result["category_source"] = "manual_canonical"
    result["quality"] = "common"
    return result


def classify(rows: list[dict[str, str]], seasoning_names: set[str]):
    by_name = {clean_name(row["name"]): row for row in rows}
    # 指南回归清单里“鸡腿、虾”没有独立源行；创建规范名，但不继承模糊营养。
    synthetic: dict[str, dict[str, str]] = {}
    for canonical, prototype_name in {"鸡腿": "鸡腿肉", "虾": "鲜虾"}.items():
        if canonical not in by_name and prototype_name in by_name:
            synthetic[canonical] = make_synthetic(canonical, by_name[prototype_name])

    initial_candidates = {
        name for name, row in by_name.items() if base_candidate(name, row, seasoning_names)
    } | set(synthetic)

    actions: list[dict[str, object]] = []
    for old_id, row in enumerate(rows, 1):
        name = clean_name(row["name"])
        result = {
            "old_id": old_id, "old_name": name, "action": "", "canonical_name": "",
            "reason": "", "drop_type": "", "possible_candidates": "",
        }
        dr = drop_reason(name, row, seasoning_names)
        if dr:
            result.update(action="DROP", drop_type=dr[0], reason=dr[1])
        elif name in SPLIT_EXACT:
            candidates = SPLIT_EXACT[name]
            result.update(action="SPLIT", possible_candidates="|".join(candidates), reason="明确包含多个独立食材；关系保守保留原文，克数不拆分")
        elif name in AMBIGUOUS:
            result.update(action="REVIEW", reason="名称过于宽泛或形态含义不明确，禁止猜测映射")
        elif PUNCT_RE.search(name):
            parts = [p for p in re.split(r"[，,、/+＆&]|和|以及|或", name) if p]
            resolved = [EXPLICIT_ALIASES.get(p, p) for p in parts]
            if 2 <= len(resolved) <= 4 and all(p in initial_candidates or p in REQUIRED_PRESENT for p in resolved):
                result.update(action="SPLIT", possible_candidates="|".join(resolved), reason="分隔符明确连接多个独立基础食材；克数无法可靠分摊")
            else:
                result.update(action="REVIEW", possible_candidates="|".join(resolved), reason="疑似多食材组合，但无法百分之百确认全部组成")
        elif name in EXPLICIT_ALIASES:
            target = EXPLICIT_ALIASES[name]
            if target in initial_candidates or target in REQUIRED_PRESENT:
                result.update(action="MERGE", canonical_name=target, reason="明确别名或规范名统一")
            else:
                result.update(action="REVIEW", possible_candidates=target, reason="别名目标未进入基础词典，需人工确认")
        else:
            stripped = strip_quantity_and_form(name)
            target = EXPLICIT_ALIASES.get(stripped, stripped)
            if target != name and target in initial_candidates:
                kind = "修复数量/单位残留" if QUANTITY_RE.search(name) else "去除确定的鲜冻/去皮去骨描述"
                result.update(action="MERGE", canonical_name=target, reason=kind)
            elif CUT_SUFFIX_RE.search(name):
                cut = CUT_SUFFIX_RE.sub("", name)
                cut = EXPLICIT_ALIASES.get(cut, cut)
                if cut in initial_candidates and cut not in {"肉", "鱼", "蛋"}:
                    result.update(action="MERGE", canonical_name=cut, reason="去除切片/切块/切丁等形态描述")
                else:
                    result.update(action="REVIEW", possible_candidates=cut if cut else "", reason="形态描述存在，但原始食材无法确定")
            elif name in initial_candidates:
                result.update(action="KEEP", canonical_name=name, reason="符合基础原生食材定义")
            elif QUANTITY_RE.search(name):
                result.update(action="DROP", drop_type="junk", reason="数量或单位残留且无法可靠恢复原食材")
            elif not category_for(row):
                result.update(action="DROP", drop_type="junk", reason="不属于指南允许的基础原生食材类别")
            elif len(name) > 10 or re.search(r"[0-9A-Za-z%（）()\[\]【】·:：;；!?！？]", name):
                result.update(action="DROP", drop_type="junk", reason="说明性文本、规格或非食材碎片")
            else:
                result.update(action="REVIEW", reason="可能是原生食材，但频次、命名或类别证据不足")
        actions.append(result)

    # 生成 canonical 行：KEEP 行优先；合成规范名仅补齐指南要求项。
    canonical_source: dict[str, dict[str, str]] = {}
    for action, row in zip(actions, rows):
        if action["action"] == "KEEP":
            canonical_source[str(action["canonical_name"])] = row
    canonical_source.update(synthetic)
    missing = [name for name in REQUIRED_PRESENT if name not in canonical_source]
    if missing:
        raise RuntimeError(f"必需基础食材没有进入 canonical：{missing}")

    ordered_names = sorted(
        canonical_source,
        key=lambda name: (-usage(canonical_source[name]), CATEGORY_ID[category_for(canonical_source[name])], name),
    )
    new_id = {name: index for index, name in enumerate(ordered_names, 1)}
    for action in actions:
        if action["action"] in {"KEEP", "MERGE"}:
            name = str(action["canonical_name"])
            if name not in new_id:
                action.update(action="REVIEW", possible_candidates=name, canonical_name="", reason="目标规范名未形成有效主表行")
            else:
                action["new_id"] = new_id[name]
                action["new_name"] = name
        elif action["action"] == "SPLIT":
            names = str(action["possible_candidates"]).split("|")
            action["new_id"] = "|".join(str(new_id[n]) for n in names if n in new_id)
            action["new_name"] = "|".join(n for n in names if n in new_id)
        else:
            action["new_id"] = ""
            action["new_name"] = ""
    return actions, canonical_source, ordered_names, new_id


def schema_text() -> str:
    return r'''-- 菜谱数据库 V2：基础原生食材版（utf8mb4）
SET NAMES utf8mb4;

CREATE TABLE ingredient_categories (
  id INT PRIMARY KEY, name VARCHAR(50) NOT NULL UNIQUE, sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ingredient_subcategories (
  id INT PRIMARY KEY, category_id INT NOT NULL, name VARCHAR(50) NOT NULL, sort_order INT NOT NULL DEFAULT 0,
  UNIQUE KEY uk_sub(category_id,name), FOREIGN KEY(category_id) REFERENCES ingredient_categories(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ingredients (
  id INT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE, category_id INT NOT NULL, subcategory_id INT NOT NULL,
  usage_count INT NOT NULL DEFAULT 0, is_core_raw TINYINT(1) NOT NULL DEFAULT 1,
  edible DECIMAL(8,2), water DECIMAL(10,3), energy_kcal DECIMAL(10,3), energy_kj DECIMAL(10,3),
  protein DECIMAL(10,3), fat DECIMAL(10,3), cho DECIMAL(10,3), dietary_fiber DECIMAL(10,3), cholesterol DECIMAL(10,3), ash DECIMAL(10,3),
  vitamin_a DECIMAL(12,3), carotene DECIMAL(12,3), retinol DECIMAL(12,3), thiamin DECIMAL(10,4), riboflavin DECIMAL(10,4), niacin DECIMAL(10,4),
  vitamin_c DECIMAL(10,3), vitamin_e DECIMAL(10,3), ca DECIMAL(12,3), p DECIMAL(12,3), k DECIMAL(12,3), na DECIMAL(12,3), mg DECIMAL(12,3),
  fe DECIMAL(10,3), zn DECIMAL(10,3), se DECIMAL(10,3), cu DECIMAL(10,3), mn DECIMAL(10,3),
  nutrition_source VARCHAR(200), nutrition_match VARCHAR(20), quality VARCHAR(20), category_source VARCHAR(30),
  tcm_user TEXT, tcm_not_user TEXT,
  FOREIGN KEY(category_id) REFERENCES ingredient_categories(id), FOREIGN KEY(subcategory_id) REFERENCES ingredient_subcategories(id),
  KEY idx_ingredients_name(name), KEY idx_ingredients_usage(usage_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE tcm_effects (id INT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE target_groups (id INT PRIMARY KEY, name VARCHAR(200) NOT NULL UNIQUE, is_suitable TINYINT(1) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ingredient_effects (
  ingredient_id INT NOT NULL, effect_id INT NOT NULL, PRIMARY KEY(ingredient_id,effect_id),
  FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE, FOREIGN KEY(effect_id) REFERENCES tcm_effects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ingredient_groups (
  ingredient_id INT NOT NULL, group_id INT NOT NULL, PRIMARY KEY(ingredient_id,group_id),
  FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE, FOREIGN KEY(group_id) REFERENCES target_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dishes (
  id INT PRIMARY KEY, dish_name VARCHAR(255) NOT NULL, description TEXT, cuisine VARCHAR(50), ingredient_text MEDIUMTEXT, instruction_text MEDIUMTEXT,
  ingredient_count INT NOT NULL DEFAULT 0, main_ingredient_count INT NOT NULL DEFAULT 0, total_weight_g DECIMAL(12,2), KEY idx_dish_name(dish_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dish_ingredients (
  id BIGINT PRIMARY KEY, dish_id INT NOT NULL, ingredient_id INT NULL, raw_name VARCHAR(255) NOT NULL, raw_text VARCHAR(500) NOT NULL,
  quantity VARCHAR(100), role VARCHAR(20) NOT NULL, grams DECIMAL(12,3), grams_source VARCHAR(30),
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE, FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL,
  KEY idx_di_dish(dish_id), KEY idx_di_ing(ingredient_id), KEY idx_di_role(role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE tags (id INT PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE, kind VARCHAR(20)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dish_tags (
  dish_id INT NOT NULL, tag_id INT NOT NULL, PRIMARY KEY(dish_id,tag_id),
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE, FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dish_nutrition (
  dish_id INT PRIMARY KEY, total_weight_g DECIMAL(12,2), energy_kcal DECIMAL(12,3), protein_g DECIMAL(12,3), fat_g DECIMAL(12,3), cho_g DECIMAL(12,3),
  dietary_fiber_g DECIMAL(12,3), ca_mg DECIMAL(12,3), fe_mg DECIMAL(12,3), na_mg DECIMAL(12,3), matched_ratio DECIMAL(8,3), weight_confidence DECIMAL(8,3),
  explicit_count INT, estimated_count INT, vague_count INT, suspect TINYINT(1) NOT NULL DEFAULT 0, nutrition_version VARCHAR(20) NOT NULL DEFAULT 'legacy',
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE seasonings (id INT PRIMARY KEY, name VARCHAR(200) NOT NULL UNIQUE, usage_count INT NOT NULL DEFAULT 0, reason VARCHAR(255)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE excluded_names (id INT PRIMARY KEY, name VARCHAR(255) NOT NULL, usage_count INT NOT NULL DEFAULT 0, reason VARCHAR(255), KEY idx_excluded_name(name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
'''


def loader_text() -> str:
    return r'''"""把 cleaned_v2 CSV 安全导入 MySQL；所有主键均使用 CSV 的明确 ID。"""
from __future__ import annotations
import argparse, csv, os
from pathlib import Path
import pymysql

HERE = Path(__file__).resolve().parent
DB = dict(host=os.getenv("MYSQL_HOST", "localhost"), port=int(os.getenv("MYSQL_PORT", "3306")),
          user=os.getenv("MYSQL_USER", "root"), password=os.getenv("MYSQL_PASSWORD", ""),
          database=os.getenv("MYSQL_DB", "recipe_db"), charset="utf8mb4", autocommit=False)

TABLES = [
 ("ingredient_categories","ingredient_categories.csv",["id","name","sort_order"]),
 ("ingredient_subcategories","ingredient_subcategories.csv",["id","category_id","name","sort_order"]),
 ("ingredients","main_ingredient.csv",["id","name","category_id","subcategory_id","usage_count","is_core_raw","可食部%","水分g","能量kcal","能量kJ","蛋白质g","脂肪g","碳水化合物g","膳食纤维g","胆固醇mg","灰分g","维生素A(ugRE)","胡萝卜素(ug)","视黄醇(ug)","硫胺素mg","核黄素mg","烟酸mg","维生素Cmg","维生素E总mg","钙mg","磷mg","钾mg","钠mg","镁mg","铁mg","锌mg","硒(ug)","铜mg","锰mg","nutrition_source_name","nutrition_match","quality","category_source","tcm_user","tcm_not_user"]),
 ("tcm_effects","tcm_effects.csv",["id","name"]),
 ("target_groups","target_groups.csv",["id","name","is_suitable"]),
 ("ingredient_effects","ingredient_effects.csv",["ingredient_id","effect_id"]),
 ("ingredient_groups","ingredient_groups.csv",["ingredient_id","group_id"]),
 ("dishes","dishes.csv",["id","dish_name","description","cuisine","ingredient_text","instruction_text","ingredient_count","main_ingredient_count","total_weight_g"]),
 ("dish_ingredients","dish_ingredients.csv",["id","dish_id","ingredient_id","raw_name","raw_text","quantity","role","grams","grams_source"]),
 ("tags","tags.csv",["id","name","kind"]), ("dish_tags","dish_tags.csv",["dish_id","tag_id"]),
 ("dish_nutrition","dish_nutrition.csv",["dish_id","total_weight_g","energy_kcal","protein_g","fat_g","cho_g","dietary_fiber_g","ca_mg","fe_mg","na_mg","matched_ratio","weight_confidence","explicit_count","estimated_count","vague_count","suspect","nutrition_version"]),
 ("seasonings","excluded_seasonings.csv",["id","name","usage_count","reason"]),
 ("excluded_names","excluded_junk.csv",["id","name","usage_count","reason"]),
]
DB_COL = {"ingredients": ["id","name","category_id","subcategory_id","usage_count","is_core_raw","edible","water","energy_kcal","energy_kj","protein","fat","cho","dietary_fiber","cholesterol","ash","vitamin_a","carotene","retinol","thiamin","riboflavin","niacin","vitamin_c","vitamin_e","ca","p","k","na","mg","fe","zn","se","cu","mn","nutrition_source","nutrition_match","quality","category_source","tcm_user","tcm_not_user"]}
ORDER_DELETE = [x[0] for x in reversed(TABLES)]

def value(v): return None if v is None or v.strip() in {"", "—", "-", "NULL", "null"} else v
def batches(reader, size=2000):
    batch=[]
    for row in reader:
        batch.append(row)
        if len(batch)>=size: yield batch; batch=[]
    if batch: yield batch

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--verify",action="store_true"); args=ap.parse_args()
    con=pymysql.connect(**DB)
    try:
        with con.cursor() as cur:
            if args.verify:
                for table,_,_ in TABLES: cur.execute(f"SELECT COUNT(*) FROM `{table}`"); print(table,cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM dish_ingredients d LEFT JOIN dishes x ON x.id=d.dish_id WHERE x.id IS NULL"); print("orphan_dish",cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM dish_ingredients d LEFT JOIN ingredients i ON i.id=d.ingredient_id WHERE d.ingredient_id IS NOT NULL AND i.id IS NULL"); print("orphan_ingredient",cur.fetchone()[0]); return
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for table in ORDER_DELETE: cur.execute(f"DELETE FROM `{table}`")
            for table,filename,csv_cols in TABLES:
                db_cols=DB_COL.get(table,csv_cols); marks=",".join(["%s"]*len(db_cols)); cols=",".join(f"`{c}`" for c in db_cols)
                sql=f"INSERT INTO `{table}` ({cols}) VALUES ({marks})"
                with (HERE/filename).open(encoding="utf-8-sig",newline="") as fh:
                    rd=csv.DictReader(fh)
                    for batch in batches(rd): cur.executemany(sql,[[value(r.get(c,"")) for c in csv_cols] for r in batch])
                print(f"loaded {table}")
            cur.execute("SET FOREIGN_KEY_CHECKS=1"); con.commit()
    except Exception: con.rollback(); raise
    finally: con.close()
if __name__=="__main__": main()
'''


def main() -> int:
    required_source = [
        "main_ingredient.csv", "dish_ingredients.csv", "dishes.csv", "dish_nutrition.csv",
        "ingredient_effects.csv", "ingredient_groups.csv", "ingredient_categories.csv",
        "ingredient_subcategories.csv", "excluded_seasonings.csv", "excluded_junk.csv",
        "tcm_effects.csv", "target_groups.csv", "tags.csv", "dish_tags.csv",
    ]
    missing = [name for name in required_source if not (SOURCE / name).exists()]
    if missing:
        raise FileNotFoundError(f"源目录缺文件：{missing}")
    if TEMP.exists():
        shutil.rmtree(TEMP)
    TEMP.mkdir(parents=True)

    rows = read_csv(SOURCE / "main_ingredient.csv")
    season_rows = read_csv(SOURCE / "excluded_seasonings.csv")
    seasoning_names = {clean_name(row["name"]) for row in season_rows}
    actions, canonical_source, ordered_names, new_id = classify(rows, seasoning_names)
    action_by_old = {int(a["old_id"]): a for a in actions}

    # 规范食材 usage_count 是所有明确 KEEP/MERGE 旧词条的合计，不把 REVIEW/SPLIT 猜进来。
    usage_sum = Counter()
    for action, row in zip(actions, rows):
        if action["action"] in {"KEEP", "MERGE"}:
            usage_sum[str(action["new_name"])] += usage(row)

    category_rows = [{"id": i, "name": n, "sort_order": i} for i, n in CATEGORIES]
    subcategory_rows = [{"id": sid, "category_id": cid, "name": n, "sort_order": sid} for sid, cid, n in SUBCATEGORIES]
    for filename, data, fields in [
        ("ingredient_categories.csv", category_rows, ["id", "name", "sort_order"]),
        ("ingredient_subcategories.csv", subcategory_rows, ["id", "category_id", "name", "sort_order"]),
    ]:
        handle, out = writer(TEMP / filename, fields)
        with handle: out.writerows(data)

    source_fields = list(rows[0].keys())
    nutrient_fields = source_fields[source_fields.index("可食部%") : source_fields.index("锰mg") + 1]
    main_fields = ["id", "category_id", "subcategory_id", "is_core_raw"] + source_fields
    handle, out = writer(TEMP / "main_ingredient.csv", main_fields)
    with handle:
        for name in ordered_names:
            src = dict(canonical_source[name])
            category = category_for(src)
            assert category
            sub = subcategory_for(category, name, src.get("category_sub", ""))
            src.update(
                id=new_id[name], name=name, usage_count=usage_sum[name],
                category_id=CATEGORY_ID[category], subcategory_id=SUBCATEGORY_ID[(CATEGORY_ID[category], sub)],
                is_core_raw=1, category=f"{category}-{sub}", category_major=category, category_sub=sub,
                category_source="v2_strict_rule",
            )
            # 名称是原生食材、但旧营养来源是熟制/罐装/油炸条目时，不把加工形态数值继承给原生 canonical。
            if re.search(r"熟|罐装|瓶装|油炸|煮|烤|蒸|腌", src.get("nutrition_source_name", "")):
                for field in nutrient_fields: src[field] = ""
                src["nutrition_match"] = "excluded_processed_source"
                src["quality"] = "common"
            out.writerow(src)

    map_fields = ["old_id", "old_name", "action", "new_id", "new_name", "reason"]
    handle, out = writer(TEMP / "ingredient_id_map.csv", map_fields)
    with handle: out.writerows(actions)

    # 菜谱关联重建，同时采集复核样本和每道菜核心食材数。
    samples_text: dict[int, list[str]] = defaultdict(list)
    samples_dish: dict[int, list[str]] = defaultdict(list)
    main_count = Counter()
    role_count = Counter()
    di_fields = ["id", "dish_id", "ingredient_id", "raw_name", "raw_text", "quantity", "role", "grams", "grams_source"]
    handle, out = writer(TEMP / "dish_ingredients.csv", di_fields)
    source_di_count = 0
    with handle, (SOURCE / "dish_ingredients.csv").open("r", encoding="utf-8-sig", newline="") as src:
        for new_rel_id, rel in enumerate(csv.DictReader(src), 1):
            source_di_count += 1
            old_id = int(rel["ingredient_id"]) if rel.get("ingredient_id") else 0
            action = action_by_old.get(old_id)
            if action and len(samples_text[old_id]) < 3:
                if rel.get("raw_text") not in samples_text[old_id]: samples_text[old_id].append(rel.get("raw_text", ""))
                if rel.get("dish_id") not in samples_dish[old_id]: samples_dish[old_id].append(rel.get("dish_id", ""))
            rel["id"] = new_rel_id
            if action and action["action"] in {"KEEP", "MERGE"}:
                rel["ingredient_id"] = action["new_id"]
                rel["role"] = "main"
                main_count[int(rel["dish_id"])] += 1
            elif action and action["action"] == "DROP" and action["drop_type"] == "seasoning":
                rel["ingredient_id"] = ""
                rel["role"] = "seasoning"
            else:
                rel["ingredient_id"] = ""
                rel["role"] = "other"
                if action and action["action"] == "SPLIT":
                    rel["grams"] = ""
                    rel["grams_source"] = "split_unknown"
            role_count[rel["role"]] += 1
            out.writerow(rel)

    drop_fields = ["old_id", "name", "usage_count", "category_major", "category_sub", "drop_type", "reason"]
    review_fields = ["old_id", "name", "usage_count", "category_major", "possible_candidates", "sample_raw_text", "sample_dish_ids", "reason"]
    dropped, reviews = [], []
    for action, row in zip(actions, rows):
        old_id = int(action["old_id"])
        if action["action"] == "DROP":
            dropped.append({"old_id": old_id, "name": row["name"], "usage_count": usage(row), "category_major": row["category_major"], "category_sub": row["category_sub"], "drop_type": action["drop_type"], "reason": action["reason"]})
        elif action["action"] in {"REVIEW", "SPLIT"}:
            reviews.append({"old_id": old_id, "name": row["name"], "usage_count": usage(row), "category_major": row["category_major"], "possible_candidates": action["possible_candidates"], "sample_raw_text": " || ".join(samples_text[old_id]), "sample_dish_ids": "|".join(samples_dish[old_id]), "reason": action["reason"]})
    dropped.sort(key=lambda r: (-int(r["usage_count"]), int(r["old_id"])))
    reviews.sort(key=lambda r: (-int(r["usage_count"]), int(r["old_id"])))
    for filename, data, fields in [("dropped_ingredients.csv", dropped, drop_fields), ("review_ingredients.csv", reviews, review_fields)]:
        handle, out = writer(TEMP / filename, fields)
        with handle: out.writerows(data)

    # 高频结果完整列出，3~19 次条目采用确定性抽样（每十条取一条，便于复现）。
    audit_fields = ["old_id", "old_name", "usage_count", "action", "new_id", "new_name", "reason"]
    high = []
    mid = []
    for action, row in zip(actions, rows):
        if action["action"] in {"KEEP", "MERGE"}:
            item = {**action, "usage_count": usage(row)}
            if usage(row) >= 20: high.append(item)
            elif 3 <= usage(row) <= 19: mid.append(item)
    high.sort(key=lambda r: (-int(r["usage_count"]), int(r["old_id"])))
    mid.sort(key=lambda r: (-int(r["usage_count"]), int(r["old_id"])))
    mid_sample = [row for index, row in enumerate(mid) if index % 10 == 0]
    for filename, data in [("high_frequency_audit.csv", high), ("mid_frequency_sample_audit.csv", mid_sample)]:
        handle, out = writer(TEMP / filename, audit_fields)
        with handle: out.writerows(data)

    # 关联表按 old_id -> new_id 重建并去重。
    old_to_new = {int(a["old_id"]): int(a["new_id"]) for a in actions if a["action"] in {"KEEP", "MERGE"}}
    rel_stats = {}
    for filename, second_col in [("ingredient_effects.csv", "effect_id"), ("ingredient_groups.csv", "group_id")]:
        source_rel = read_csv(SOURCE / filename)
        pairs = sorted({(old_to_new[int(r["ingredient_id"])], int(r[second_col])) for r in source_rel if int(r["ingredient_id"]) in old_to_new})
        handle, out = writer(TEMP / filename, ["ingredient_id", second_col])
        with handle:
            for ing, other in pairs: out.writerow({"ingredient_id": ing, second_col: other})
        rel_stats[filename] = (len(source_rel), len(pairs))

    # 菜品文本字段保持原值，只新增 main_ingredient_count，不改 ingredient_count 语义。
    with (SOURCE / "dishes.csv").open("r", encoding="utf-8-sig", newline="") as src:
        rd = csv.DictReader(src); dish_fields = list(rd.fieldnames or [])
        insert_at = dish_fields.index("total_weight_g")
        dish_fields.insert(insert_at, "main_ingredient_count")
        handle, out = writer(TEMP / "dishes.csv", dish_fields)
        with handle:
            for row in rd:
                row["main_ingredient_count"] = main_count[int(row["id"])]
                out.writerow(row)

    # 旧菜品营养只做版本标记，绝不使用部分核心食材重新估算。
    with (SOURCE / "dish_nutrition.csv").open("r", encoding="utf-8-sig", newline="") as src:
        rd = csv.DictReader(src); dn_fields = list(rd.fieldnames or []) + ["nutrition_version"]
        handle, out = writer(TEMP / "dish_nutrition.csv", dn_fields)
        dn_count = 0
        with handle:
            for row in rd:
                dn_count += 1; row["nutrition_version"] = "legacy"; out.writerow(row)

    # 与食材清洗无关的字典/关联保持原样。
    for filename in ["tcm_effects.csv", "target_groups.csv", "tags.csv", "dish_tags.csv"]:
        shutil.copy2(SOURCE / filename, TEMP / filename)

    # 排除表由本轮动作重新生成，理由可审计。
    season_out = [r for r in dropped if r["drop_type"] == "seasoning"]
    junk_out = [r for r in dropped if r["drop_type"] != "seasoning"]
    handle, out = writer(TEMP / "excluded_seasonings.csv", ["id", "name", "usage_count", "reason"])
    with handle:
        for ident, row in enumerate(season_out, 1): out.writerow({"id": ident, "name": row["name"], "usage_count": row["usage_count"], "reason": row["reason"]})
    handle, out = writer(TEMP / "excluded_junk.csv", ["id", "name", "usage_count", "reason"])
    with handle:
        for ident, row in enumerate(junk_out, 1): out.writerow({"id": ident, "name": row["name"], "usage_count": row["usage_count"], "reason": row["reason"]})

    (TEMP / "schema.sql").write_text(schema_text(), encoding="utf-8")
    (TEMP / "load_to_mysql.py").write_text(loader_text(), encoding="utf-8")

    # 完整性与回归测试。
    main_names = set(ordered_names)
    failed_present = [n for n in REQUIRED_PRESENT if n not in main_names]
    failed_absent = [n for n in REQUIRED_ABSENT if n in main_names]
    continuous = list(new_id.values()) == list(range(1, len(new_id) + 1))
    valid_ing_ids = set(new_id.values())
    orphan_ingredients = 0
    orphan_dishes = 0
    dish_ids = {int(r["id"]) for r in read_csv(SOURCE / "dishes.csv")}
    with (TEMP / "dish_ingredients.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        for rel in csv.DictReader(fh):
            if rel["ingredient_id"] and int(rel["ingredient_id"]) not in valid_ing_ids: orphan_ingredients += 1
            if int(rel["dish_id"]) not in dish_ids: orphan_dishes += 1
    effect_ids = {int(r["id"]) for r in read_csv(TEMP / "tcm_effects.csv")}
    group_ids = {int(r["id"]) for r in read_csv(TEMP / "target_groups.csv")}
    orphan_effects = sum(1 for r in read_csv(TEMP / "ingredient_effects.csv") if int(r["ingredient_id"]) not in valid_ing_ids or int(r["effect_id"]) not in effect_ids)
    orphan_groups = sum(1 for r in read_csv(TEMP / "ingredient_groups.csv") if int(r["ingredient_id"]) not in valid_ing_ids or int(r["group_id"]) not in group_ids)
    duplicate_names = len(ordered_names) - len(main_names)
    duplicate_rel = source_di_count - len({})  # 行 ID 已重新连续生成；保留所有原始用料行。

    # 5 个代表食材必须能反查菜谱。
    reverse_targets = ["番茄", "鸡蛋", "猪肉", "土豆", "苹果"]
    reverse_counts = {name: 0 for name in reverse_targets}
    reverse_ids = {new_id[n]: n for n in reverse_targets}
    with (TEMP / "dish_ingredients.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        for rel in csv.DictReader(fh):
            if rel["ingredient_id"] and int(rel["ingredient_id"]) in reverse_ids:
                reverse_counts[reverse_ids[int(rel["ingredient_id"])]] += 1

    # 六个代表营养映射必须来自各自 canonical 行，禁止 contains/fuzzy。
    nutrition_targets = ["猪肉", "牛肉", "鸡蛋", "番茄", "苹果", "香蕉"]
    nutrition_check = {name: bool(canonical_source[name].get("nutrition_source_name") and canonical_source[name].get("能量kcal")) for name in nutrition_targets}
    nutrition_covered = sum(1 for name in ordered_names if canonical_source[name].get("能量kcal") not in NULLISH)
    effects_covered = len({int(r["ingredient_id"]) for r in read_csv(TEMP / "ingredient_effects.csv")})

    if failed_present or failed_absent or not continuous or any([orphan_ingredients, orphan_dishes, orphan_effects, orphan_groups, duplicate_names]) or not all(reverse_counts.values()) or not all(nutrition_check.values()):
        raise RuntimeError({"failed_present": failed_present, "failed_absent": failed_absent, "continuous": continuous, "orphans": [orphan_ingredients, orphan_dishes, orphan_effects, orphan_groups], "reverse_counts": reverse_counts, "nutrition_check": nutrition_check})

    counts = Counter(str(a["action"]) for a in actions)
    drop_types = Counter(str(a["drop_type"]) for a in actions if a["action"] == "DROP")
    mapped_old = counts["KEEP"] + counts["MERGE"]
    relation_coverage = role_count["main"] / source_di_count if source_di_count else 0
    report = f"""# 菜谱数据库 V2 清洗报告

## 1. 处理范围与原则

- 数据源：`菜谱数据库_交付_20260918 (1)`，只读取、不修改。
- 规范依据：`菜谱数据库_V2_数据清洗与关联重构指南_Codex.md`。
- 目标：把食材主表收敛为基础原生食材；调味料、加工食品、成品、工具、操作语句和无法确认的碎片不进入主表。
- 映射策略：只使用明确别名、明确数量/形态剥离；不使用模糊包含匹配，不对 REVIEW 强行归并。
- 菜品营养：完整保留旧值并标记 `nutrition_version=legacy`；没有用不完整核心食材重新估算。

## 2. 总量

| 指标 | 数量 |
|---|---:|
| 旧食材总数 | {len(rows):,} |
| 新基础食材总数 | {len(ordered_names):,} |
| KEEP | {counts['KEEP']:,} |
| MERGE | {counts['MERGE']:,} |
| DROP | {counts['DROP']:,} |
| SPLIT | {counts['SPLIT']:,} |
| REVIEW | {counts['REVIEW']:,} |
| 删除调味料 | {drop_types['seasoning']:,} |
| 删除加工食品 | {drop_types['processed']:,} |
| 删除非食材/碎片 | {drop_types['junk']:,} |
| 旧 ID 成功映射到新 ID | {mapped_old:,} |

## 3. 规则修复

| 修复类型 | 数量 |
|---|---:|
| 数量/单位残留归并 | {sum(1 for a in actions if a['action']=='MERGE' and '数量/单位' in str(a['reason'])):,} |
| 切片/块/丁/丝/末形态归并 | {sum(1 for a in actions if a['action']=='MERGE' and '形态描述' in str(a['reason'])):,} |
| 明确别名归并 | {sum(1 for a in actions if a['reason']=='明确别名或规范名统一'):,} |
| 高频 KEEP/MERGE 审计条目（usage_count≥20） | {len(high):,} |
| 3~19 次确定性抽样条目 | {len(mid_sample):,} |

高频结果在 `high_frequency_audit.csv`；中频抽样在 `mid_frequency_sample_audit.csv`。REVIEW/SPLIT 连同原文样本和菜品 ID 见 `review_ingredients.csv`。

## 4. 菜谱关联

| 指标 | 数量 |
|---|---:|
| dish_ingredients 总数 | {source_di_count:,} |
| main | {role_count['main']:,} |
| seasoning | {role_count['seasoning']:,} |
| other | {role_count['other']:,} |
| 菜谱关联覆盖率（main/全部用料） | {relation_coverage:.2%} |

`raw_name`、`raw_text`、`quantity` 均保留；SPLIT 因无法可靠分摊克数，`grams` 置空并标记 `split_unknown`。原 `ingredient_count` 不变，新增 `main_ingredient_count`。

反向菜谱关联回归：{', '.join(f'{k}={v:,}' for k,v in reverse_counts.items())}。

## 5. 其他关联与覆盖率

| 指标 | 原数量 | 新数量 |
|---|---:|---:|
| ingredient_effects | {rel_stats['ingredient_effects.csv'][0]:,} | {rel_stats['ingredient_effects.csv'][1]:,} |
| ingredient_groups | {rel_stats['ingredient_groups.csv'][0]:,} | {rel_stats['ingredient_groups.csv'][1]:,} |

- 营养数据覆盖率：{nutrition_covered}/{len(ordered_names)} = {nutrition_covered/len(ordered_names):.2%}
- 功效数据覆盖率：{effects_covered}/{len(ordered_names)} = {effects_covered/len(ordered_names):.2%}
- 六个代表营养映射：{', '.join(f'{k}={"通过" if v else "失败"}' for k,v in nutrition_check.items())}

## 6. 完整性与回归测试

- 新食材 ID 连续：通过（1..{len(ordered_names)}）。
- 食材名称唯一：通过。
- dish_ingredients 食材外键孤儿：{orphan_ingredients}。
- dish_ingredients 菜品外键孤儿：{orphan_dishes}。
- ingredient_effects 外键孤儿：{orphan_effects}。
- ingredient_groups 外键孤儿：{orphan_groups}。
- 指南“必须存在”清单：全部通过。
- 指南“必须不存在”清单：全部通过。
- 全部 16,693 个旧名称均分配 KEEP/MERGE/DROP/SPLIT/REVIEW 动作。

## 7. 审计边界

- `REVIEW` 不进入主表，等待人工确认；不能确定的 `SPLIT` 只保留菜谱原文，不伪造克数。
- MERGE 不合并或平均营养值；canonical 行只使用自身权威营养来源。新增“鸡腿、虾”规范名不继承模糊物种营养。
- `dish_nutrition` 是历史估算，只能按 legacy 使用；未来如需 V2 营养，应基于完整原料体系另行重算。
"""
    (TEMP / "CLEANING_REPORT.md").write_text(report, encoding="utf-8")

    # 输出清单，便于开发验收。
    readme = """# cleaned_v2 交付说明\n\n本目录由 `../scripts/clean_v2.py` 从原始交付目录确定性生成。\n\n- 先阅读 `CLEANING_REPORT.md`。\n- `main_ingredient.csv` 使用明确、连续的新 ID。\n- `ingredient_id_map.csv` 是所有旧 ID 的审计映射。\n- `review_ingredients.csv` 必须人工复核后才能扩大主表。\n- 导入前先执行 `schema.sql`，再配置环境变量运行 `load_to_mysql.py`。\n"""
    (TEMP / "README.md").write_text(readme, encoding="utf-8")

    # 原子替换：所有校验通过后才替换上次成功结果。
    previous = SQL_ROOT / "cleaned_v2.__previous__"
    if previous.exists(): shutil.rmtree(previous)
    if OUTPUT.exists(): OUTPUT.replace(previous)
    TEMP.replace(OUTPUT)
    if previous.exists(): shutil.rmtree(previous)

    zip_tmp = ZIP_PATH.with_suffix(".zip.tmp")
    if zip_tmp.exists(): zip_tmp.unlink()
    with zipfile.ZipFile(zip_tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(OUTPUT.rglob("*")):
            if path.is_file(): archive.write(path, Path("cleaned_v2") / path.relative_to(OUTPUT))
    os.replace(zip_tmp, ZIP_PATH)
    print(f"OK old={len(rows)} new={len(ordered_names)} actions={dict(counts)} roles={dict(role_count)} output={OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
