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
SEASONAL_SOURCE = SQL_ROOT / "seasonal_source"
OUTPUT = SQL_ROOT / "cleaned_v2"
TEMP = SQL_ROOT / "cleaned_v2.__building__"
ZIP_PATH = SQL_ROOT / "cleaned_v2.zip"

NULLISH = {"", "—", "-", "--", "null", "NULL", "None"}

# 菜谱级删减采用保守的多证据规则。地域只处理明确的低频异国/西式信号；
# 健康性优先使用菜名与标签，营养密度仅在历史营养质量达标时作为补充证据。
DISH_HEALTH_PROTECT_RE = re.compile(
    r"低脂|低卡|低糖|无糖|少糖|少油|无油|减脂|减肥|健康|轻食|全麦|蒸|水煮"
)
DISH_UNHEALTHY_NAME_RE = re.compile(
    r"奶茶|甜甜圈|冰淇淋|雪糕|奶油蛋糕|芝士蛋糕|慕斯蛋糕|磅蛋糕|"
    r"曲奇|饼干|糖果|披萨|汉堡|热狗|薯条|炸鸡|炸薯|油炸|可乐"
)
DISH_UNHEALTHY_TAGS = {
    "蛋糕", "甜品", "烘焙", "零食", "饼干", "冷饮", "甜品饮品",
    "西点", "糕点", "奶油蛋糕", "磅蛋糕", "甜甜圈",
}
DISH_BEVERAGE_TAGS = {"饮品", "饮料", "冷饮", "冰饮", "甜品饮品"}
DISH_HEALTH_PROTECT_TAGS = {"减肥", "清淡", "健康", "低脂", "低卡", "素食"}
DISH_SUGARY_BEVERAGE_RE = re.compile(
    r"奶茶|奶昔|果汁|汽水|可乐|冰沙|冰饮|含糖|加糖|红糖|黑糖|冰糖|"
    r"蜂蜜|糖浆|炼乳|奶油|椰奶|酸奶|乳酸菌|果茶|甜"
)
DISH_LOW_USE_FOREIGN_RE = re.compile(
    r"西班牙|意大利|意式|法式|法国|美式|美国|英式|英国|墨西哥|"
    r"土耳其|印度|越南|俄式|俄罗斯|地中海|西餐|欧式"
)
DISH_LOW_USE_FOREIGN_TAGS = {
    "西式", "西式早餐", "西餐", "西点", "法式", "欧式面包",
    "意式", "墨西哥", "异国风味",
}
DISH_DOMESTIC_TAGS = {"家常菜", "下饭菜", "中式", "中式早餐"}
DISH_NUTRITION_RISK_RE = re.compile(
    r"酥|脆|煎|烤|烧烤|红烧|干锅|肥|油|奶油|芝士|糖|腊|炸"
)
DISH_TARGET_COUNT = 10_000
DISH_MAX_SAME_TITLE = 2
DISH_COMMON_CHINESE_RE = re.compile(
    r"炒|炖|蒸|煮|焖|汤|粥|面|饭|饺子|包子|馒头|凉拌|红烧|清蒸|家常"
)
DISH_MARKETING_RE = re.compile(
    r"零失败|超简单|巨好吃|好吃到|网红|必学|必做|绝绝子|秘制|独家|"
    r"[🔥🌈💯😋😍🤤🍰🍓🍅🥕🥜]"
)
DISH_REMAINING_RISK_RE = re.compile(r"奶油|芝士|糖霜|糖浆|肥肉|猪油|煎炸|油酥")
DISH_TAG_WEIGHTS = {
    "家常菜": 30, "下饭菜": 20, "快手菜": 15, "清淡": 15,
    "减肥": 12, "健康": 12, "中式": 20, "中式早餐": 18,
    "早餐": 8, "汤羹": 8, "汤": 6, "素菜": 8, "素食": 8,
    "蒸": 8, "炖": 8, "煮": 6, "粥": 6, "主食": 5,
    "大鱼大肉": -10, "下酒菜": -6, "烤箱": -4, "煎": -3,
}

# 完整食材目录只做确定性同义词规范化；不把“青菜、肉、海鲜”等宽泛词猜成具体品种。
CATALOG_NAME_ALIASES = {
    "耗油": "蚝油", "食盐": "盐", "盐巴": "盐", "少量盐": "盐",
    "白砂糖": "白糖", "砂糖": "白糖", "清水": "水", "凉水": "水",
    "食油": "食用油", "麻油": "香油", "大料": "八角",
    "鸡": "鸡肉", "鲜虾": "虾", "大虾": "虾",
}
CATALOG_QUANTITY_PREFIX_RE = re.compile(
    r"^(?:约|大约|适量|少许|少量|若干|一点|一些|数片|几片|几根|几只|半个|半根|"
    r"一根|两根|一个|两个|一只|两只|\d+(?:\.\d+)?(?:克|g|斤|个|只|根|片|块|勺|杯)?)"
)
CATALOG_WRAPPER_RE = re.compile(r"^[【\[（(]+|[】\]）)]+$")

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
    # 物种明确的切法、肉馅和部位别名，可以安全回归到原生食材。
    "鸡大腿": "鸡腿", "鸡小腿": "鸡腿", "鸡全腿": "鸡腿", "琵琶腿": "鸡腿",
    "鸡全翅": "鸡翅", "鸡翅尖": "鸡翅", "全鸡": "鸡肉", "整鸡": "鸡肉",
    "鸡块": "鸡肉", "鸡肉块": "鸡肉", "鸡肉片": "鸡肉", "鸡肉丁": "鸡肉",
    "鸡肉丝": "鸡肉", "鸡肉馅": "鸡肉", "鸡肉糜": "鸡肉", "鸡肉末": "鸡肉",
    "猪肉馅": "猪肉", "猪肉糜": "猪肉", "猪肉沫": "猪肉", "猪肉末": "猪肉",
    "猪肉片": "猪肉", "猪肉丝": "猪肉", "猪肉丁": "猪肉", "猪肉块": "猪肉",
    "牛肉馅": "牛肉", "牛肉糜": "牛肉", "牛肉沫": "牛肉", "牛肉末": "牛肉",
    "牛肉片": "牛肉", "牛肉丝": "牛肉", "牛肉丁": "牛肉", "牛肉块": "牛肉",
    "羊肉片": "羊肉", "羊肉卷": "羊肉", "肥牛卷": "肥牛", "牛腱": "牛腱子",
    "羊腿": "羊腿肉", "鲩鱼": "草鱼", "鲩鱼腩": "草鱼", "海水虾": "虾",
    "藕片": "藕", "青柠檬": "柠檬", "洋白菜": "卷心菜", "大蒜头": "蒜",
    "头蒜": "蒜", "土豆土豆": "土豆", "绿辣椒": "青椒", "小红辣椒": "红辣椒",
}

# 旧分类本身并不可靠；这里只覆盖语义确定且已实际发现的错类。
CATEGORY_NAME_OVERRIDES = {
    "羊腿肉": "畜肉",
    "猪后腿肉": "畜肉",
    "蟹味菇": "菌菇藻类",
}

# 经菜谱原文人工确认，名称本身就是可购买的原生食材，但旧数据缺少权威营养匹配或频次不足。
# 这里只接受语义唯一的名称；加工品、粉、面、馅、汤、汁仍不得进入。
MANUAL_CORE_NAMES = {
    "白芸豆", "羊蝎子", "梅头肉", "美人椒", "南姜", "干葱", "瓜子",
}

# “父食材 -> 子食材”只服务于搜索扩展，不改写原始 dish_ingredients。
# 例如选择“鸡肉”时，可以找到鸡腿、鸡胸肉和鸡翅菜谱。
INGREDIENT_HIERARCHY = {
    "鸡肉": ["鸡胸肉", "鸡腿", "鸡翅", "三黄鸡", "童子鸡", "老母鸡", "乌鸡", "肉鸡"],
    "鸡翅": ["鸡翅根", "鸡中翅", "鸡翅中"],
    "猪肉": ["五花肉", "排骨", "猪里脊", "猪骨", "猪颈肉", "瘦猪肉", "猪排", "猪肋排", "猪后腿肉", "猪腿肉", "猪小排", "猪大排", "梅花肉", "梅头肉", "猪蹄"],
    "排骨": ["猪肋排", "猪小排", "猪大排"],
    "牛肉": ["牛腩", "牛里脊", "牛排", "牛腱子", "牛仔骨", "牛尾", "牛柳", "牦牛肉", "牛展"],
    "羊肉": ["羊排", "羊腿肉", "羊蝎子"],
    "鸭肉": ["鸭翅"],
    "虾": ["虾仁", "大虾", "黑虎虾", "河虾", "海虾", "青虾", "北极虾", "草虾", "九节虾", "南美白对虾", "大头虾", "沼虾"],
    "螃蟹": ["大闸蟹", "梭子蟹", "青蟹", "海蟹"],
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


def clean_catalog_name(value: str) -> str:
    name = clean_name(value)
    name = CATALOG_WRAPPER_RE.sub("", name)
    name = CATALOG_QUANTITY_PREFIX_RE.sub("", name)
    name = re.sub(r"(?:适量|少许|少量|若干)$", "", name)
    return CATALOG_NAME_ALIASES.get(name, name) or "未命名食材"


def core_name_from_raw(raw_name: str, new_id: dict[str, int]) -> str | None:
    """仅在名称可确定时把菜谱自由文本补回核心食材关系。"""
    name = clean_catalog_name(raw_name)
    candidates = [name]
    stripped = strip_quantity_and_form(name)
    if stripped != name:
        candidates.append(stripped)
    if CUT_SUFFIX_RE.search(name):
        candidates.append(CUT_SUFFIX_RE.sub("", name))
    explicit = EXPLICIT_ALIASES.get(name)
    if isinstance(explicit, str):
        candidates.append(explicit)
    for candidate in candidates:
        candidate = CATALOG_NAME_ALIASES.get(candidate, candidate)
        if candidate in new_id and candidate not in {"肉", "鱼", "蛋"}:
            return candidate
    return None


def catalog_type_for(
    name: str,
    action: dict[str, object] | None,
    seasoning_names: set[str],
) -> tuple[str, str, str]:
    """返回目录类型、复核状态和分类理由。"""
    if action and action.get("action") == "SPLIT":
        return "composite", "verified", "明确多食材组合，组成见桥接表"
    if name == "水":
        return "other_food", "verified", "基础用水"
    drop_type = str(action.get("drop_type") or "") if action else ""
    if drop_type == "seasoning" or is_seasoning(name, seasoning_names):
        return "seasoning", "verified", "调味料"
    if drop_type == "processed" or PROCESSED_RE.search(name) or BEVERAGE_RE.search(name):
        return "processed", "verified", "加工、半成品、乳制品或饮品"
    if TOOL_RE.search(name) or INSTRUCTION_RE.search(name):
        return "non_food", "review", "疑似工具、包装或操作说明"
    if name in AMBIGUOUS or re.search(r"各种|各类|其他|混合|自选", name):
        return "generic", "review", "宽泛名称，保留原义而不猜测具体品种"
    if PUNCT_RE.search(name):
        return "composite", "review", "疑似复合名称，组成未完全确认"
    return "other_food", "review", "菜谱实际使用名称，待进一步规范"


def dish_filter_reason(
    dish_name: str,
    dish_tags: set[str],
    nutrition: dict[str, str] | None,
) -> tuple[str, str, str] | None:
    """返回菜谱级删除类型、原因和可审计证据；无命中时返回 None。"""
    name = clean_name(dish_name)
    protected = bool(DISH_HEALTH_PROTECT_RE.search(name)) or bool(
        dish_tags & DISH_HEALTH_PROTECT_TAGS
    )

    unhealthy_tag_hits = sorted(dish_tags & DISH_UNHEALTHY_TAGS)
    unhealthy_name_match = DISH_UNHEALTHY_NAME_RE.search(name)
    if not protected and (unhealthy_name_match or unhealthy_tag_hits):
        evidence = []
        if unhealthy_name_match:
            evidence.append(f"菜名关键词={unhealthy_name_match.group(0)}")
        if unhealthy_tag_hits:
            evidence.append(f"标签={','.join(unhealthy_tag_hits)}")
        return "unhealthy_high_signal", "高糖/高脂零食、甜点或油炸快餐", "；".join(evidence)

    beverage_hits = sorted(dish_tags & DISH_BEVERAGE_TAGS)
    beverage_name_match = DISH_SUGARY_BEVERAGE_RE.search(name)
    if not protected and beverage_hits and beverage_name_match:
        return (
            "unhealthy_sugary_beverage",
            "含糖或高能量饮品，不作为健康菜谱保留",
            f"菜名关键词={beverage_name_match.group(0)}；标签={','.join(beverage_hits)}",
        )

    # legacy 营养值只在覆盖率、重量置信度及总重量均合格时使用；不使用钠估算，
    # 避免历史调味料估算误差误删普通中餐。
    if not protected and nutrition and DISH_NUTRITION_RISK_RE.search(name):
        try:
            weight = float(nutrition.get("total_weight_g") or 0)
            matched = float(nutrition.get("matched_ratio") or 0)
            confidence = float(nutrition.get("weight_confidence") or 0)
            kcal_100g = 100 * float(nutrition.get("energy_kcal") or 0) / weight
            fat_100g = 100 * float(nutrition.get("fat_g") or 0) / weight
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        else:
            if (
                weight >= 100
                and matched >= 50
                and confidence >= 60
                and kcal_100g >= 400
                and fat_100g >= 20
            ):
                return (
                    "unhealthy_nutrition_density",
                    "可靠历史营养显示能量与脂肪密度同时偏高",
                    f"{kcal_100g:.1f}kcal/100g；脂肪{fat_100g:.1f}g/100g；"
                    f"匹配率{matched:.1f}%；重量置信度{confidence:.1f}%",
                )

    foreign_name_match = DISH_LOW_USE_FOREIGN_RE.search(name)
    foreign_tag_hits = sorted(dish_tags & DISH_LOW_USE_FOREIGN_TAGS)
    if (
        (foreign_name_match or foreign_tag_hits)
        and not dish_tags & DISH_DOMESTIC_TAGS
    ):
        evidence = []
        if foreign_name_match:
            evidence.append(f"菜名地域词={foreign_name_match.group(0)}")
        if foreign_tag_hits:
            evidence.append(f"标签={','.join(foreign_tag_hits)}")
        return "low_use_foreign", "中国家庭场景中相对低频的异国或西式菜谱", "；".join(evidence)

    return None


def normalized_dish_title(value: str) -> str:
    name = clean_name(value).lower()
    name = re.sub(r"[【】\[\]（）()《》<>#*_~·—–\-:：,，。.!！?？/\\|+&＆'\"]", "", name)
    name = re.sub(r"\d+(?:\.\d+)?(?:寸|人份|份|克|g|ml|分钟|小时)?", "", name)
    name = re.sub(r"(?:的做法|做法|教程|食谱|家庭版|家常版|简单版|懒人版)$", "", name)
    return name or clean_name(value).lower()


def dish_priority_base(
    row: dict[str, str],
    dish_tags: set[str],
    nutrition: dict[str, str] | None,
    main_ingredient_count: int,
) -> tuple[int, str]:
    """精选约一万道菜谱时的确定性基础分；返回分数及审计摘要。"""
    name = clean_name(row.get("dish_name", ""))
    score = sum(DISH_TAG_WEIGHTS.get(tag, 0) for tag in dish_tags)
    signals: list[str] = []

    positive_tags = sorted(tag for tag in dish_tags if DISH_TAG_WEIGHTS.get(tag, 0) > 0)
    if positive_tags:
        signals.append(f"常用标签={','.join(positive_tags)}")

    if DISH_COMMON_CHINESE_RE.search(name):
        score += 8
        signals.append("常见中式做法")
    if 2 <= len(name) <= 24:
        score += 5
    elif len(name) > 40:
        score -= 10
        signals.append("标题过长")
    if DISH_MARKETING_RE.search(name):
        score -= 8
        signals.append("营销化标题")
    if DISH_REMAINING_RISK_RE.search(name):
        score -= 6
        signals.append("剩余高油糖信号")

    instruction_len = len(clean_name(row.get("instruction_text", "")))
    ingredient_text_len = len(clean_name(row.get("ingredient_text", "")))
    if 40 <= instruction_len <= 3000:
        score += 10
        signals.append("步骤完整")
    elif instruction_len:
        score += 3
    else:
        score -= 12
        signals.append("缺少步骤")
    if 10 <= ingredient_text_len <= 1000:
        score += 5
    elif not ingredient_text_len:
        score -= 8
        signals.append("缺少用料文本")

    if 1 <= main_ingredient_count <= 8:
        score += 6
    elif main_ingredient_count <= 15:
        score += 3
    else:
        score -= 5

    if nutrition:
        try:
            matched = float(nutrition.get("matched_ratio") or 0)
            confidence = float(nutrition.get("weight_confidence") or 0)
            suspect = int(float(nutrition.get("suspect") or 0))
        except (TypeError, ValueError):
            pass
        else:
            if matched >= 50 and confidence >= 60 and suspect == 0:
                score += 6
                signals.append("营养数据较完整")

    return score, "；".join(signals) or "基础信息完整度"


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
    name = clean_name(row.get("name", ""))
    if name in CATEGORY_NAME_OVERRIDES:
        return CATEGORY_NAME_OVERRIDES[name]
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
    if name in MANUAL_CORE_NAMES:
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
    return r'''-- 菜谱数据库 V2：核心原生食材 + 完整菜谱食材目录（utf8mb4）
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
CREATE TABLE ingredient_hierarchy (
  parent_ingredient_id INT NOT NULL, child_ingredient_id INT NOT NULL,
  PRIMARY KEY(parent_ingredient_id,child_ingredient_id),
  FOREIGN KEY(parent_ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE,
  FOREIGN KEY(child_ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE,
  CHECK(parent_ingredient_id <> child_ingredient_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ingredient_catalog (
  id INT PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE, ingredient_type VARCHAR(30) NOT NULL,
  core_ingredient_id INT NULL, category VARCHAR(50) NOT NULL, subcategory VARCHAR(50) NOT NULL,
  is_core_raw TINYINT(1) NOT NULL DEFAULT 0, is_edible TINYINT(1) NOT NULL DEFAULT 1,
  review_status VARCHAR(20) NOT NULL, usage_count INT NOT NULL DEFAULT 0, reason VARCHAR(255),
  FOREIGN KEY(core_ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL,
  KEY idx_catalog_type(ingredient_type), KEY idx_catalog_core(core_ingredient_id), KEY idx_catalog_review(review_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ingredient_catalog_aliases (
  alias_name VARCHAR(255) NOT NULL, catalog_ingredient_id INT NOT NULL,
  canonical_name VARCHAR(255) NOT NULL, usage_count INT NOT NULL DEFAULT 0, source VARCHAR(50) NOT NULL,
  PRIMARY KEY(alias_name,catalog_ingredient_id),
  FOREIGN KEY(catalog_ingredient_id) REFERENCES ingredient_catalog(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE seasonal_calendar (
  id VARCHAR(50) PRIMARY KEY, level VARCHAR(20) NOT NULL, name VARCHAR(50) NOT NULL,
  gregorian_time VARCHAR(100), lunar_time VARCHAR(100), season VARCHAR(10) NOT NULL,
  sort_order INT NOT NULL, description VARCHAR(500),
  UNIQUE KEY uk_seasonal_calendar_level_name(level,name), KEY idx_seasonal_calendar_sort(sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE seasonal_food (
  id VARCHAR(20) PRIMARY KEY, calendar_id VARCHAR(50) NOT NULL, level VARCHAR(20) NOT NULL,
  time_name VARCHAR(50) NOT NULL, season VARCHAR(10) NOT NULL, category VARCHAR(20) NOT NULL,
  name VARCHAR(100) NOT NULL, note VARCHAR(500), recommendation_reason VARCHAR(500), source VARCHAR(100) NOT NULL,
  entity_type VARCHAR(30) NOT NULL, catalog_ingredient_id INT NULL, core_ingredient_id INT NULL,
  match_status VARCHAR(40) NOT NULL,
  UNIQUE KEY uk_seasonal_food(calendar_id,category,name),
  FOREIGN KEY(calendar_id) REFERENCES seasonal_calendar(id) ON DELETE CASCADE,
  FOREIGN KEY(catalog_ingredient_id) REFERENCES ingredient_catalog(id) ON DELETE SET NULL,
  FOREIGN KEY(core_ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL,
  KEY idx_seasonal_food_name(name), KEY idx_seasonal_food_catalog(catalog_ingredient_id),
  KEY idx_seasonal_food_season(season)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE seasonal_knowledge (
  id VARCHAR(20) PRIMARY KEY, calendar_id VARCHAR(50) NOT NULL, seasonal_food_id VARCHAR(20) NULL,
  time_name VARCHAR(50) NOT NULL, level VARCHAR(20) NOT NULL, season VARCHAR(10) NOT NULL,
  category VARCHAR(30) NOT NULL, name VARCHAR(100) NOT NULL, content TEXT NOT NULL,
  source VARCHAR(100) NOT NULL, knowledge_type VARCHAR(20) NOT NULL,
  FOREIGN KEY(calendar_id) REFERENCES seasonal_calendar(id) ON DELETE CASCADE,
  FOREIGN KEY(seasonal_food_id) REFERENCES seasonal_food(id) ON DELETE SET NULL,
  KEY idx_seasonal_knowledge_calendar(calendar_id), KEY idx_seasonal_knowledge_food(seasonal_food_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dishes (
  id INT PRIMARY KEY, dish_name VARCHAR(255) NOT NULL, description TEXT, cuisine VARCHAR(50), ingredient_text MEDIUMTEXT, instruction_text MEDIUMTEXT,
  ingredient_count INT NOT NULL DEFAULT 0, main_ingredient_count INT NOT NULL DEFAULT 0,
  search_ingredient_count INT NOT NULL DEFAULT 0, total_weight_g DECIMAL(12,2), KEY idx_dish_name(dish_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE seasonal_dish_links (
  seasonal_food_id VARCHAR(20) NOT NULL, dish_id INT NOT NULL, match_type VARCHAR(30) NOT NULL,
  PRIMARY KEY(seasonal_food_id,dish_id),
  FOREIGN KEY(seasonal_food_id) REFERENCES seasonal_food(id) ON DELETE CASCADE,
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE,
  KEY idx_seasonal_dish_links_dish(dish_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dish_ingredients (
  id BIGINT PRIMARY KEY, dish_id INT NOT NULL, ingredient_id INT NULL, catalog_ingredient_id INT NOT NULL,
  raw_name VARCHAR(255) NOT NULL, raw_text VARCHAR(500) NOT NULL,
  quantity VARCHAR(100), role VARCHAR(20) NOT NULL, grams DECIMAL(12,3), grams_source VARCHAR(30),
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE, FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL,
  FOREIGN KEY(catalog_ingredient_id) REFERENCES ingredient_catalog(id) ON DELETE RESTRICT,
  KEY idx_di_dish(dish_id), KEY idx_di_ing(ingredient_id), KEY idx_di_catalog(catalog_ingredient_id), KEY idx_di_role(role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dish_ingredient_components (
  dish_ingredient_id BIGINT NOT NULL, component_ingredient_id INT NOT NULL,
  PRIMARY KEY(dish_ingredient_id,component_ingredient_id),
  FOREIGN KEY(dish_ingredient_id) REFERENCES dish_ingredients(id) ON DELETE CASCADE,
  FOREIGN KEY(component_ingredient_id) REFERENCES ingredients(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE dish_ingredient_search (
  dish_id INT NOT NULL, ingredient_id INT NOT NULL, source_ingredient_id INT NOT NULL,
  match_type VARCHAR(20) NOT NULL,
  PRIMARY KEY(dish_id,ingredient_id),
  FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE,
  FOREIGN KEY(ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE,
  FOREIGN KEY(source_ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE,
  KEY idx_dis_ingredient(ingredient_id), KEY idx_dis_source(source_ingredient_id)
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
 ("ingredient_hierarchy","ingredient_hierarchy.csv",["parent_ingredient_id","child_ingredient_id"]),
 ("ingredient_catalog","ingredient_catalog.csv",["id","name","ingredient_type","core_ingredient_id","category","subcategory","is_core_raw","is_edible","review_status","usage_count","reason"]),
 ("ingredient_catalog_aliases","ingredient_catalog_aliases.csv",["alias_name","catalog_ingredient_id","canonical_name","usage_count","source"]),
 ("seasonal_calendar","seasonal_calendar.csv",["id","level","name","gregorian_time","lunar_time","season","sort_order","description"]),
 ("seasonal_food","seasonal_food.csv",["id","calendar_id","level","time_name","season","category","name","note","recommendation_reason","source","entity_type","catalog_ingredient_id","core_ingredient_id","match_status"]),
 ("seasonal_knowledge","seasonal_knowledge.csv",["id","calendar_id","seasonal_food_id","time_name","level","season","category","name","content","source","knowledge_type"]),
 ("dishes","dishes.csv",["id","dish_name","description","cuisine","ingredient_text","instruction_text","ingredient_count","main_ingredient_count","search_ingredient_count","total_weight_g"]),
 ("seasonal_dish_links","seasonal_dish_links.csv",["seasonal_food_id","dish_id","match_type"]),
 ("dish_ingredients","dish_ingredients.csv",["id","dish_id","ingredient_id","catalog_ingredient_id","raw_name","raw_text","quantity","role","grams","grams_source"]),
 ("dish_ingredient_components","dish_ingredient_components.csv",["dish_ingredient_id","component_ingredient_id"]),
 ("dish_ingredient_search","dish_ingredient_search.csv",["dish_id","ingredient_id","source_ingredient_id","match_type"]),
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
                cur.execute("SELECT COUNT(*) FROM dish_ingredients d LEFT JOIN ingredients i ON i.id=d.ingredient_id WHERE d.ingredient_id IS NOT NULL AND i.id IS NULL"); print("orphan_ingredient",cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM dish_ingredients d LEFT JOIN ingredient_catalog c ON c.id=d.catalog_ingredient_id WHERE c.id IS NULL"); print("orphan_catalog",cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM seasonal_food f LEFT JOIN seasonal_calendar c ON c.id=f.calendar_id WHERE c.id IS NULL"); print("orphan_seasonal_calendar",cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM seasonal_dish_links l LEFT JOIN seasonal_food f ON f.id=l.seasonal_food_id LEFT JOIN dishes d ON d.id=l.dish_id WHERE f.id IS NULL OR d.id IS NULL"); print("orphan_seasonal_dish",cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM dish_ingredient_components c LEFT JOIN dish_ingredients d ON d.id=c.dish_ingredient_id LEFT JOIN ingredients i ON i.id=c.component_ingredient_id WHERE d.id IS NULL OR i.id IS NULL"); print("orphan_component",cur.fetchone()[0]); return
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
    seasonal_files = [
        "seasonal_calendar.csv", "seasonal_food.csv", "seasonal_knowledge.csv",
    ]
    missing_seasonal = [
        name for name in seasonal_files if not (SEASONAL_SOURCE / name).exists()
    ]
    if missing_seasonal:
        raise FileNotFoundError(f"季节数据源缺文件：{missing_seasonal}")
    if TEMP.exists():
        shutil.rmtree(TEMP)
    TEMP.mkdir(parents=True)

    rows = read_csv(SOURCE / "main_ingredient.csv")
    seasonal_calendar_source = read_csv(SEASONAL_SOURCE / "seasonal_calendar.csv")
    seasonal_food_source = read_csv(SEASONAL_SOURCE / "seasonal_food.csv")
    seasonal_knowledge_source = read_csv(SEASONAL_SOURCE / "seasonal_knowledge.csv")
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

    # 建立食材父子层级。层级只扩展搜索，不改写原始菜谱用料。
    hierarchy_pairs = sorted({
        (new_id[parent], new_id[child])
        for parent, children in INGREDIENT_HIERARCHY.items()
        if parent in new_id
        for child in children
        if child in new_id and child != parent
    })
    handle, out = writer(
        TEMP / "ingredient_hierarchy.csv",
        ["parent_ingredient_id", "child_ingredient_id"],
    )
    with handle:
        for parent_id, child_id in hierarchy_pairs:
            out.writerow({
                "parent_ingredient_id": parent_id,
                "child_ingredient_id": child_id,
            })

    parents_by_child: dict[int, set[int]] = defaultdict(set)
    for parent_id, child_id in hierarchy_pairs:
        parents_by_child[child_id].add(parent_id)

    def ancestors(ingredient_id: int) -> set[int]:
        result: set[int] = set()
        stack = list(parents_by_child.get(ingredient_id, set()))
        while stack:
            parent_id = stack.pop()
            if parent_id in result:
                continue
            result.add(parent_id)
            stack.extend(parents_by_child.get(parent_id, set()))
        return result

    # 第一遍扫描全部菜谱用料：采集复核样本、直接/拆分食材，并据此决定菜谱保留集合。
    samples_text: dict[int, list[str]] = defaultdict(list)
    samples_dish: dict[int, list[str]] = defaultdict(list)
    direct_by_dish: dict[int, set[int]] = defaultdict(set)
    directly_linked_dish_ids: set[int] = set()
    search_rows: dict[tuple[int, int], tuple[int, str]] = {}
    source_di_count = 0
    with (SOURCE / "dish_ingredients.csv").open("r", encoding="utf-8-sig", newline="") as src:
        for source_rel_id, rel in enumerate(csv.DictReader(src), 1):
            source_di_count += 1
            dish_id = int(rel["dish_id"])
            old_id = int(rel["ingredient_id"]) if rel.get("ingredient_id") else 0
            action = action_by_old.get(old_id)
            if action and len(samples_text[old_id]) < 3:
                if rel.get("raw_text") not in samples_text[old_id]:
                    samples_text[old_id].append(rel.get("raw_text", ""))
                if rel.get("dish_id") not in samples_dish[old_id]:
                    samples_dish[old_id].append(rel.get("dish_id", ""))

            resolved: list[tuple[int, str]] = []
            if action and action["action"] in {"KEEP", "MERGE"}:
                resolved.append((int(action["new_id"]), "direct"))
            elif action and action["action"] == "SPLIT":
                resolved.extend(
                    (int(value), "split")
                    for value in str(action.get("new_id", "")).split("|")
                    if value
                )
            else:
                fallback_core_name = core_name_from_raw(rel.get("raw_name", ""), new_id)
                if fallback_core_name:
                    resolved.append((new_id[fallback_core_name], "direct"))

            for ingredient_id, match_type in resolved:
                direct_by_dish[dish_id].add(ingredient_id)
                if match_type == "direct":
                    directly_linked_dish_ids.add(dish_id)
                key = (dish_id, ingredient_id)
                existing = search_rows.get(key)
                priority = {"direct": 0, "split": 1, "ancestor": 2}
                if existing is None or priority[match_type] < priority[existing[1]]:
                    search_rows[key] = (ingredient_id, match_type)
                for parent_id in ancestors(ingredient_id):
                    search_rows.setdefault(
                        (dish_id, parent_id), (ingredient_id, "ancestor")
                    )

    # 第二阶段按菜名、标签和合格的历史营养证据做保守删减。
    # 先形成零有效食材候选集合，再只对这些可保留候选应用菜谱质量规则。
    initial_kept_dish_ids = set(directly_linked_dish_ids)
    tag_name_by_id = {
        int(row["id"]): row["name"] for row in read_csv(SOURCE / "tags.csv")
    }
    tags_by_dish: dict[int, set[str]] = defaultdict(set)
    with (SOURCE / "dish_tags.csv").open("r", encoding="utf-8-sig", newline="") as src:
        for row in csv.DictReader(src):
            dish_id = int(row["dish_id"])
            if dish_id in initial_kept_dish_ids:
                tag_name = tag_name_by_id.get(int(row["tag_id"]))
                if tag_name:
                    tags_by_dish[dish_id].add(tag_name)

    nutrition_by_dish: dict[int, dict[str, str]] = {}
    with (SOURCE / "dish_nutrition.csv").open("r", encoding="utf-8-sig", newline="") as src:
        for row in csv.DictReader(src):
            dish_id = int(row["dish_id"])
            if dish_id in initial_kept_dish_ids:
                nutrition_by_dish[dish_id] = row

    quality_drop_by_dish: dict[int, dict[str, str]] = {}
    candidate_meta: dict[int, dict[str, object]] = {}
    title_frequency: Counter[str] = Counter()
    with (SOURCE / "dishes.csv").open("r", encoding="utf-8-sig", newline="") as src:
        for row in csv.DictReader(src):
            dish_id = int(row["id"])
            if dish_id not in initial_kept_dish_ids:
                continue
            result = dish_filter_reason(
                row.get("dish_name", ""),
                tags_by_dish.get(dish_id, set()),
                nutrition_by_dish.get(dish_id),
            )
            if result:
                drop_type, reason, evidence = result
                quality_drop_by_dish[dish_id] = {
                    "drop_type": drop_type,
                    "reason": reason,
                    "evidence": evidence,
                }
                continue
            title_key = normalized_dish_title(row.get("dish_name", ""))
            base_score, score_evidence = dish_priority_base(
                row,
                tags_by_dish.get(dish_id, set()),
                nutrition_by_dish.get(dish_id),
                len(direct_by_dish[dish_id]),
            )
            candidate_meta[dish_id] = {
                "title_key": title_key,
                "base_score": base_score,
                "score_evidence": score_evidence,
            }
            title_frequency[title_key] += 1

    # 从通过健康/地域规则的候选中精选约一万道。标题频次代表数据源中的常用度；
    # 每个规范标题通常最多保留两版，并强制覆盖候选集中仍有菜谱的全部核心食材。
    for meta in candidate_meta.values():
        frequency = title_frequency[str(meta["title_key"])]
        popularity_bonus = min(20, 4 * (frequency.bit_length() - 1))
        meta["popularity_bonus"] = popularity_bonus
        meta["score"] = int(meta["base_score"]) + popularity_bonus

    ranked_candidate_ids = sorted(
        candidate_meta,
        key=lambda dish_id: (-int(candidate_meta[dish_id]["score"]), dish_id),
    )
    target_count = min(DISH_TARGET_COUNT, len(ranked_candidate_ids))
    candidate_ingredient_ids = {
        ingredient_id
        for dish_id in candidate_meta
        for ingredient_id in direct_by_dish[dish_id]
    }
    uncovered_ingredient_ids = set(candidate_ingredient_ids)
    selected_dish_ids: set[int] = set()

    for dish_id in ranked_candidate_ids:
        newly_covered = direct_by_dish[dish_id] & uncovered_ingredient_ids
        if newly_covered:
            selected_dish_ids.add(dish_id)
            uncovered_ingredient_ids -= newly_covered
        if not uncovered_ingredient_ids:
            break
    if uncovered_ingredient_ids:
        raise RuntimeError(f"精选菜谱未覆盖候选食材：{sorted(uncovered_ingredient_ids)}")

    selected_title_counts = Counter(
        str(candidate_meta[dish_id]["title_key"]) for dish_id in selected_dish_ids
    )
    for dish_id in ranked_candidate_ids:
        if len(selected_dish_ids) >= target_count:
            break
        if dish_id in selected_dish_ids:
            continue
        title_key = str(candidate_meta[dish_id]["title_key"])
        if selected_title_counts[title_key] >= DISH_MAX_SAME_TITLE:
            continue
        selected_dish_ids.add(dish_id)
        selected_title_counts[title_key] += 1

    # 极端情况下标题上限可能导致不足；最后按总分补齐，仍保持确定性。
    for dish_id in ranked_candidate_ids:
        if len(selected_dish_ids) >= target_count:
            break
        selected_dish_ids.add(dish_id)

    if len(selected_dish_ids) != target_count:
        raise RuntimeError(f"精选菜谱数量错误：{len(selected_dish_ids)} != {target_count}")

    for dish_id, meta in candidate_meta.items():
        if dish_id in selected_dish_ids:
            continue
        frequency = title_frequency[str(meta["title_key"])]
        quality_drop_by_dish[dish_id] = {
            "drop_type": "low_priority_catalog_trim",
            "reason": "在约一万道精选库中综合优先级较低",
            "evidence": (
                f"综合分={meta['score']}；同名规范标题频次={frequency}；"
                f"{meta['score_evidence']}"
            ),
        }

    pretrim_candidate_count = len(candidate_meta)
    kept_dish_ids = selected_dish_ids
    direct_by_dish = {
        dish_id: ingredient_ids
        for dish_id, ingredient_ids in direct_by_dish.items()
        if dish_id in kept_dish_ids
    }
    search_rows = {
        key: value for key, value in search_rows.items() if key[0] in kept_dish_ids
    }
    main_count = {dish_id: len(ids) for dish_id, ids in direct_by_dish.items()}
    search_count = Counter(dish_id for dish_id, _ in search_rows)

    # 建立覆盖全部菜谱用料的统一目录。核心原生食材沿用 1..590 的 ID；
    # 调味料、加工食材、复合名称和待复核名称追加在其后。
    catalog_resolution_rows: list[dict[str, object]] = []
    catalog_usage = Counter()
    alias_usage: Counter[tuple[str, str]] = Counter()
    extra_catalog_meta: dict[str, tuple[str, str, str]] = {}
    with (SOURCE / "dish_ingredients.csv").open("r", encoding="utf-8-sig", newline="") as src:
        for rel in csv.DictReader(src):
            dish_id = int(rel["dish_id"])
            if dish_id not in kept_dish_ids:
                continue
            old_id = int(rel["ingredient_id"]) if rel.get("ingredient_id") else 0
            action = action_by_old.get(old_id)
            raw_name = clean_name(rel.get("raw_name", "")) or "未命名食材"
            core_name: str | None = None
            components: list[int] = []
            if action and action["action"] in {"KEEP", "MERGE"}:
                core_name = str(action["new_name"])
            elif action and action["action"] == "SPLIT":
                components = [
                    int(value) for value in str(action.get("new_id", "")).split("|") if value
                ]
            else:
                core_name = core_name_from_raw(raw_name, new_id)

            if core_name:
                catalog_name = core_name
                ingredient_type = "core_raw"
                review_status = "verified"
                catalog_reason = "核心原生食材或确定性别名"
                core_ingredient_id = new_id[core_name]
            else:
                catalog_name = clean_catalog_name(raw_name)
                ingredient_type, review_status, catalog_reason = catalog_type_for(
                    catalog_name, action, seasoning_names
                )
                core_ingredient_id = ""
                previous = extra_catalog_meta.get(catalog_name)
                priority = {
                    "seasoning": 0, "processed": 1, "composite": 2,
                    "other_food": 3, "generic": 4, "non_food": 5,
                }
                if previous is None or priority[ingredient_type] < priority[previous[0]]:
                    extra_catalog_meta[catalog_name] = (
                        ingredient_type, review_status, catalog_reason
                    )

            catalog_usage[catalog_name] += 1
            alias_usage[(raw_name, catalog_name)] += 1
            catalog_resolution_rows.append({
                "catalog_name": catalog_name,
                "core_ingredient_id": core_ingredient_id,
                "ingredient_type": ingredient_type,
                "components": components,
            })

    core_row_by_name = {
        row["name"]: row for row in read_csv(TEMP / "main_ingredient.csv")
    }
    dish_catalog_names = set(extra_catalog_meta)

    # 季节数据先使用核心名、完整目录名或唯一别名做确定匹配。来源中标为
    # 水果/蔬菜/食材但完整目录尚无记录的名称，补入完整目录；“菜品”不伪装成食材。
    alias_targets: dict[str, set[str]] = defaultdict(set)
    for alias_name, canonical_name in alias_usage:
        alias_targets[alias_name].add(canonical_name)
    seasonal_catalog_categories: dict[str, set[str]] = defaultdict(set)
    seasonal_resolution_names: list[str | None] = []
    for row in seasonal_food_source:
        raw_seasonal_name = clean_name(row["名称"])
        seasonal_name = clean_catalog_name(raw_seasonal_name)
        resolved_name: str | None = None
        if seasonal_name in new_id or seasonal_name in extra_catalog_meta:
            resolved_name = seasonal_name
        elif len(alias_targets.get(raw_seasonal_name, set())) == 1:
            resolved_name = next(iter(alias_targets[raw_seasonal_name]))
        elif row["类别"] != "菜品":
            resolved_name = seasonal_name
            extra_catalog_meta.setdefault(
                seasonal_name,
                ("seasonal_food", "verified", "季节数据源补充的可食用名称"),
            )
        if row["类别"] != "菜品" and resolved_name:
            seasonal_catalog_categories[resolved_name].add(row["类别"])
        seasonal_resolution_names.append(resolved_name)

    catalog_id_by_name = dict(new_id)
    next_catalog_id = len(new_id) + 1
    stable_extra_names = sorted(dish_catalog_names) + sorted(
        set(extra_catalog_meta) - dish_catalog_names
    )
    for name in stable_extra_names:
        if name in catalog_id_by_name:
            continue
        catalog_id_by_name[name] = next_catalog_id
        next_catalog_id += 1

    catalog_fields = [
        "id", "name", "ingredient_type", "core_ingredient_id", "category",
        "subcategory", "is_core_raw", "is_edible", "review_status",
        "usage_count", "reason",
    ]
    handle, out = writer(TEMP / "ingredient_catalog.csv", catalog_fields)
    with handle:
        for name, catalog_id in sorted(catalog_id_by_name.items(), key=lambda item: item[1]):
            if name in new_id:
                core_row = core_row_by_name[name]
                out.writerow({
                    "id": catalog_id, "name": name, "ingredient_type": "core_raw",
                    "core_ingredient_id": new_id[name], "category": core_row["category_major"],
                    "subcategory": core_row["category_sub"], "is_core_raw": 1,
                    "is_edible": 1, "review_status": "verified",
                    "usage_count": catalog_usage[name], "reason": "核心原生食材",
                })
            else:
                ingredient_type, review_status, catalog_reason = extra_catalog_meta[name]
                seasonal_categories = seasonal_catalog_categories.get(name, set())
                if "水果" in seasonal_categories:
                    category, subcategory = "水果", "季节数据补充"
                elif "蔬菜" in seasonal_categories:
                    category, subcategory = "蔬菜", "季节数据补充"
                elif seasonal_categories:
                    category, subcategory = "时令食材", "季节数据补充"
                else:
                    category, subcategory = "扩展食材", ingredient_type
                out.writerow({
                    "id": catalog_id, "name": name, "ingredient_type": ingredient_type,
                    "core_ingredient_id": "", "category": category,
                    "subcategory": subcategory, "is_core_raw": 0,
                    "is_edible": 0 if ingredient_type == "non_food" else 1,
                    "review_status": review_status, "usage_count": catalog_usage[name],
                    "reason": catalog_reason,
                })

    handle, out = writer(
        TEMP / "ingredient_catalog_aliases.csv",
        ["alias_name", "catalog_ingredient_id", "canonical_name", "usage_count", "source"],
    )
    with handle:
        for (alias_name, canonical_name), alias_count in sorted(alias_usage.items()):
            out.writerow({
                "alias_name": alias_name,
                "catalog_ingredient_id": catalog_id_by_name[canonical_name],
                "canonical_name": canonical_name,
                "usage_count": alias_count,
                "source": "dish_ingredients.raw_name",
            })

    # 第二遍只输出仍有有效基础食材的菜谱用料；删除菜谱的全部用料同步退出。
    role_count = Counter()
    di_fields = ["id", "dish_id", "ingredient_id", "catalog_ingredient_id", "raw_name", "raw_text", "quantity", "role", "grams", "grams_source"]
    handle, out = writer(TEMP / "dish_ingredients.csv", di_fields)
    component_handle, component_out = writer(
        TEMP / "dish_ingredient_components.csv",
        ["dish_ingredient_id", "component_ingredient_id"],
    )
    output_di_count = 0
    component_count = 0
    with handle, component_handle, (SOURCE / "dish_ingredients.csv").open("r", encoding="utf-8-sig", newline="") as src:
        for rel in csv.DictReader(src):
            dish_id = int(rel["dish_id"])
            if dish_id not in kept_dish_ids:
                continue
            output_di_count += 1
            resolution = catalog_resolution_rows[output_di_count - 1]
            old_id = int(rel["ingredient_id"]) if rel.get("ingredient_id") else 0
            action = action_by_old.get(old_id)
            rel["id"] = output_di_count
            rel["catalog_ingredient_id"] = catalog_id_by_name[str(resolution["catalog_name"])]
            if resolution["core_ingredient_id"]:
                rel["ingredient_id"] = resolution["core_ingredient_id"]
                rel["role"] = "main"
            elif resolution["ingredient_type"] == "seasoning":
                rel["ingredient_id"] = ""
                rel["role"] = "seasoning"
            else:
                rel["ingredient_id"] = ""
                rel["role"] = str(resolution["ingredient_type"])
                if resolution["components"]:
                    rel["grams"] = ""
                    rel["grams_source"] = "split_unknown"
            role_count[rel["role"]] += 1
            out.writerow(rel)
            for component_id in resolution["components"]:
                component_count += 1
                component_out.writerow({
                    "dish_ingredient_id": output_di_count,
                    "component_ingredient_id": component_id,
                })

    handle, out = writer(
        TEMP / "dish_ingredient_search.csv",
        ["dish_id", "ingredient_id", "source_ingredient_id", "match_type"],
    )
    with handle:
        for (dish_id, ingredient_id), (source_id, match_type) in sorted(search_rows.items()):
            out.writerow({
                "dish_id": dish_id,
                "ingredient_id": ingredient_id,
                "source_ingredient_id": source_id,
                "match_type": match_type,
            })

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

    # 只保留至少关联一个确定基础食材（含确定 SPLIT）的菜谱。
    # 保留原 dish id，避免外部收藏等引用因重编号整体错位。
    dropped_dishes = []
    kept_dish_count = 0
    kept_dish_names: dict[int, str] = {}
    with (SOURCE / "dishes.csv").open("r", encoding="utf-8-sig", newline="") as src:
        rd = csv.DictReader(src); dish_fields = list(rd.fieldnames or [])
        insert_at = dish_fields.index("total_weight_g")
        dish_fields.insert(insert_at, "main_ingredient_count")
        dish_fields.insert(insert_at + 1, "search_ingredient_count")
        handle, out = writer(TEMP / "dishes.csv", dish_fields)
        with handle:
            for row in rd:
                dish_id = int(row["id"])
                if dish_id not in kept_dish_ids:
                    quality_drop = quality_drop_by_dish.get(dish_id)
                    dropped_dishes.append({
                        "id": dish_id,
                        "dish_name": row["dish_name"],
                        "ingredient_count": row.get("ingredient_count", ""),
                        "drop_type": quality_drop["drop_type"] if quality_drop else "no_core_ingredient",
                        "reason": quality_drop["reason"] if quality_drop else "没有可确定关联的基础原生食材",
                        "evidence": quality_drop["evidence"] if quality_drop else "基础食材关联数=0",
                        "ingredient_text": row.get("ingredient_text", ""),
                    })
                    continue
                kept_dish_count += 1
                kept_dish_names[dish_id] = row["dish_name"]
                row["main_ingredient_count"] = main_count[dish_id]
                row["search_ingredient_count"] = search_count[dish_id]
                out.writerow(row)

    handle, out = writer(
        TEMP / "dropped_dishes.csv",
        ["id", "dish_name", "ingredient_count", "drop_type", "reason", "evidence", "ingredient_text"],
    )
    with handle:
        out.writerows(dropped_dishes)

    # 规范化季节/月份/节气/节日日历，并把时令名称连接到完整食材目录。
    calendar_fields = [
        "id", "level", "name", "gregorian_time", "lunar_time", "season",
        "sort_order", "description",
    ]
    calendar_by_key: dict[tuple[str, str], str] = {}
    handle, out = writer(TEMP / "seasonal_calendar.csv", calendar_fields)
    with handle:
        for row in seasonal_calendar_source:
            calendar_by_key[(row["层级"], row["名称"])] = row["id"]
            out.writerow({
                "id": row["id"], "level": row["层级"], "name": row["名称"],
                "gregorian_time": row["公历时间"], "lunar_time": row["农历时间"],
                "season": row["所属季节"], "sort_order": row["顺序"],
                "description": row["简介"],
            })

    seasonal_food_fields = [
        "id", "calendar_id", "level", "time_name", "season", "category",
        "name", "note", "recommendation_reason", "source", "entity_type",
        "catalog_ingredient_id", "core_ingredient_id", "match_status",
    ]
    seasonal_food_output: list[dict[str, object]] = []
    seasonal_food_id_by_key: dict[tuple[str, str, str, str], str] = {}
    seasonal_dish_links: list[dict[str, object]] = []
    for index, (row, resolved_name) in enumerate(
        zip(seasonal_food_source, seasonal_resolution_names), 1
    ):
        food_id = f"SF{index:04d}"
        key = (row["时间名称"], row["层级"], row["类别"], row["名称"])
        seasonal_food_id_by_key[key] = food_id
        catalog_id = catalog_id_by_name.get(resolved_name or "", "")
        core_id = new_id.get(resolved_name or "", "")
        if resolved_name:
            entity_type = "ingredient"
            if core_id:
                match_status = "core_exact"
            elif extra_catalog_meta.get(resolved_name, ("", "", ""))[0] == "seasonal_food":
                match_status = "seasonal_catalog"
            elif clean_name(row["名称"]) == resolved_name:
                match_status = "catalog_exact"
            else:
                match_status = "catalog_alias"
        else:
            entity_type = "dish_keyword"
            keyword = clean_name(row["名称"])
            matched_dishes = [
                (dish_id, dish_name)
                for dish_id, dish_name in kept_dish_names.items()
                if keyword and keyword in clean_name(dish_name)
            ]
            match_status = "dish_title_keyword" if matched_dishes else "unmatched_dish_keyword"
            for dish_id, dish_name in matched_dishes:
                seasonal_dish_links.append({
                    "seasonal_food_id": food_id,
                    "dish_id": dish_id,
                    "match_type": "exact_title" if clean_name(dish_name) == keyword else "title_contains",
                })
        seasonal_food_output.append({
            "id": food_id, "calendar_id": row["日历id"], "level": row["层级"],
            "time_name": row["时间名称"], "season": row["所属季节"],
            "category": row["类别"], "name": row["名称"], "note": row["备注"],
            "recommendation_reason": row["推荐理由"], "source": row["数据来源"],
            "entity_type": entity_type, "catalog_ingredient_id": catalog_id,
            "core_ingredient_id": core_id, "match_status": match_status,
        })
    handle, out = writer(TEMP / "seasonal_food.csv", seasonal_food_fields)
    with handle:
        out.writerows(seasonal_food_output)

    handle, out = writer(
        TEMP / "seasonal_dish_links.csv",
        ["seasonal_food_id", "dish_id", "match_type"],
    )
    with handle:
        out.writerows(sorted(
            seasonal_dish_links,
            key=lambda value: (str(value["seasonal_food_id"]), int(value["dish_id"])),
        ))

    knowledge_fields = [
        "id", "calendar_id", "seasonal_food_id", "time_name", "level",
        "season", "category", "name", "content", "source", "knowledge_type",
    ]
    handle, out = writer(TEMP / "seasonal_knowledge.csv", knowledge_fields)
    with handle:
        for row in seasonal_knowledge_source:
            key = (row["时间"], row["层级"], row["类别"], row["名称"])
            seasonal_food_id = seasonal_food_id_by_key.get(key, "")
            out.writerow({
                "id": row["id"],
                "calendar_id": calendar_by_key[(row["层级"], row["时间"])],
                "seasonal_food_id": seasonal_food_id,
                "time_name": row["时间"], "level": row["层级"],
                "season": row["所属季节"], "category": row["类别"],
                "name": row["名称"], "content": row["内容"],
                "source": row["数据来源"],
                "knowledge_type": "food" if seasonal_food_id else "summary",
            })

    # 删除菜谱时同步删除营养；保留菜谱仍沿用 legacy，绝不伪造部分营养。
    with (SOURCE / "dish_nutrition.csv").open("r", encoding="utf-8-sig", newline="") as src:
        rd = csv.DictReader(src); dn_fields = list(rd.fieldnames or []) + ["nutrition_version"]
        handle, out = writer(TEMP / "dish_nutrition.csv", dn_fields)
        dn_count = 0
        nutrition_dish_ids: set[int] = set()
        with handle:
            for row in rd:
                if int(row["dish_id"]) not in kept_dish_ids:
                    continue
                dish_id = int(row["dish_id"])
                nutrition_dish_ids.add(dish_id)
                dn_count += 1; row["nutrition_version"] = "legacy"; out.writerow(row)
            for dish_id in sorted(kept_dish_ids - nutrition_dish_ids):
                blank_row = {field: "" for field in dn_fields}
                blank_row.update(dish_id=dish_id, suspect=0, nutrition_version="missing")
                dn_count += 1
                out.writerow(blank_row)

    # 字典保持原样；菜谱标签必须按保留菜谱同步过滤。
    for filename in ["tcm_effects.csv", "target_groups.csv", "tags.csv"]:
        shutil.copy2(SOURCE / filename, TEMP / filename)
    source_dish_tag_count = 0
    dish_tag_count = 0
    handle, out = writer(TEMP / "dish_tags.csv", ["dish_id", "tag_id"])
    with handle, (SOURCE / "dish_tags.csv").open("r", encoding="utf-8-sig", newline="") as src:
        for row in csv.DictReader(src):
            source_dish_tag_count += 1
            if int(row["dish_id"]) not in kept_dish_ids:
                continue
            dish_tag_count += 1
            out.writerow(row)

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
    catalog_rows = read_csv(TEMP / "ingredient_catalog.csv")
    valid_catalog_ids = {int(r["id"]) for r in catalog_rows}
    catalog_continuous = valid_catalog_ids == set(range(1, len(catalog_rows) + 1))
    orphan_ingredients = 0
    orphan_dishes = 0
    orphan_catalog = 0
    missing_catalog = 0
    dish_ids = {int(r["id"]) for r in read_csv(TEMP / "dishes.csv")}
    with (TEMP / "dish_ingredients.csv").open("r", encoding="utf-8-sig", newline="") as fh:
        for rel in csv.DictReader(fh):
            if rel["ingredient_id"] and int(rel["ingredient_id"]) not in valid_ing_ids: orphan_ingredients += 1
            if int(rel["dish_id"]) not in dish_ids: orphan_dishes += 1
            if not rel["catalog_ingredient_id"]: missing_catalog += 1
            elif int(rel["catalog_ingredient_id"]) not in valid_catalog_ids: orphan_catalog += 1
    component_rows = read_csv(TEMP / "dish_ingredient_components.csv")
    valid_dish_ingredient_ids = set(range(1, output_di_count + 1))
    orphan_components = sum(
        1 for row in component_rows
        if int(row["dish_ingredient_id"]) not in valid_dish_ingredient_ids
        or int(row["component_ingredient_id"]) not in valid_ing_ids
    )
    alias_rows = read_csv(TEMP / "ingredient_catalog_aliases.csv")
    orphan_aliases = sum(
        1 for row in alias_rows
        if int(row["catalog_ingredient_id"]) not in valid_catalog_ids
    )
    calendar_rows = read_csv(TEMP / "seasonal_calendar.csv")
    calendar_ids = {row["id"] for row in calendar_rows}
    seasonal_food_rows = read_csv(TEMP / "seasonal_food.csv")
    seasonal_food_ids = {row["id"] for row in seasonal_food_rows}
    seasonal_knowledge_rows = read_csv(TEMP / "seasonal_knowledge.csv")
    seasonal_link_rows = read_csv(TEMP / "seasonal_dish_links.csv")
    seasonal_errors: list[str] = []
    if len(calendar_rows) != len(seasonal_calendar_source) or len(calendar_ids) != len(calendar_rows):
        seasonal_errors.append("calendar_count_or_duplicate")
    if len(seasonal_food_rows) != len(seasonal_food_source) or len(seasonal_food_ids) != len(seasonal_food_rows):
        seasonal_errors.append("food_count_or_duplicate")
    if any(row["calendar_id"] not in calendar_ids for row in seasonal_food_rows):
        seasonal_errors.append("food_calendar_orphan")
    if any(
        row["entity_type"] == "ingredient" and (
            not row["catalog_ingredient_id"]
            or int(row["catalog_ingredient_id"]) not in valid_catalog_ids
        )
        for row in seasonal_food_rows
    ):
        seasonal_errors.append("food_catalog_orphan")
    if any(
        row["core_ingredient_id"] and int(row["core_ingredient_id"]) not in valid_ing_ids
        for row in seasonal_food_rows
    ):
        seasonal_errors.append("food_core_orphan")
    if len(seasonal_knowledge_rows) != len(seasonal_knowledge_source):
        seasonal_errors.append("knowledge_count")
    if any(row["calendar_id"] not in calendar_ids for row in seasonal_knowledge_rows):
        seasonal_errors.append("knowledge_calendar_orphan")
    if any(
        row["seasonal_food_id"] and row["seasonal_food_id"] not in seasonal_food_ids
        for row in seasonal_knowledge_rows
    ):
        seasonal_errors.append("knowledge_food_orphan")
    if sum(bool(row["seasonal_food_id"]) for row in seasonal_knowledge_rows) != len(seasonal_food_rows):
        seasonal_errors.append("knowledge_food_coverage")
    if len({(row["seasonal_food_id"], row["dish_id"]) for row in seasonal_link_rows}) != len(seasonal_link_rows):
        seasonal_errors.append("dish_link_duplicate")
    if any(
        row["seasonal_food_id"] not in seasonal_food_ids or int(row["dish_id"]) not in dish_ids
        for row in seasonal_link_rows
    ):
        seasonal_errors.append("dish_link_orphan")
    effect_ids = {int(r["id"]) for r in read_csv(TEMP / "tcm_effects.csv")}
    group_ids = {int(r["id"]) for r in read_csv(TEMP / "target_groups.csv")}
    orphan_effects = sum(1 for r in read_csv(TEMP / "ingredient_effects.csv") if int(r["ingredient_id"]) not in valid_ing_ids or int(r["effect_id"]) not in effect_ids)
    orphan_groups = sum(1 for r in read_csv(TEMP / "ingredient_groups.csv") if int(r["ingredient_id"]) not in valid_ing_ids or int(r["group_id"]) not in group_ids)
    hierarchy_rows = read_csv(TEMP / "ingredient_hierarchy.csv")
    orphan_hierarchy = sum(
        1 for r in hierarchy_rows
        if int(r["parent_ingredient_id"]) not in valid_ing_ids
        or int(r["child_ingredient_id"]) not in valid_ing_ids
        or r["parent_ingredient_id"] == r["child_ingredient_id"]
    )
    search_data = read_csv(TEMP / "dish_ingredient_search.csv")
    orphan_search = sum(
        1 for r in search_data
        if int(r["dish_id"]) not in dish_ids
        or int(r["ingredient_id"]) not in valid_ing_ids
        or int(r["source_ingredient_id"]) not in valid_ing_ids
    )
    duplicate_search = len(search_data) - len({
        (r["dish_id"], r["ingredient_id"]) for r in search_data
    })
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

    # 通用“鸡肉”必须覆盖鸡腿、鸡胸肉、鸡翅菜谱，但不伪造原始用料行。
    chicken_id = new_id["鸡肉"]
    chicken_children = {new_id[n] for n in ["鸡腿", "鸡胸肉", "鸡翅"]}
    child_dishes = {
        int(r["dish_id"]) for r in search_data
        if int(r["ingredient_id"]) in chicken_children and r["match_type"] != "ancestor"
    }
    chicken_dishes = {
        int(r["dish_id"]) for r in search_data
        if int(r["ingredient_id"]) == chicken_id
    }
    chicken_expansion_ok = bool(child_dishes) and child_dishes <= chicken_dishes

    if failed_present or failed_absent or not continuous or not catalog_continuous or any([
        orphan_ingredients, orphan_dishes, orphan_effects, orphan_groups,
        orphan_hierarchy, orphan_search, duplicate_search, duplicate_names,
        orphan_catalog, missing_catalog, orphan_components, orphan_aliases,
    ]) or seasonal_errors or not all(reverse_counts.values()) or not all(nutrition_check.values()) or not chicken_expansion_ok:
        raise RuntimeError({"failed_present": failed_present, "failed_absent": failed_absent, "continuous": continuous, "catalog_continuous": catalog_continuous, "orphans": [orphan_ingredients, orphan_dishes, orphan_effects, orphan_groups, orphan_hierarchy, orphan_search, orphan_catalog, missing_catalog, orphan_components, orphan_aliases], "seasonal_errors": seasonal_errors, "reverse_counts": reverse_counts, "nutrition_check": nutrition_check, "chicken_expansion_ok": chicken_expansion_ok})

    counts = Counter(str(a["action"]) for a in actions)
    drop_types = Counter(str(a["drop_type"]) for a in actions if a["action"] == "DROP")
    dish_drop_types = Counter(row["drop_type"] for row in dropped_dishes)
    catalog_type_counts = Counter(row["ingredient_type"] for row in catalog_rows)
    seasonal_match_counts = Counter(row["match_status"] for row in seasonal_food_rows)
    mapped_old = counts["KEEP"] + counts["MERGE"]
    relation_coverage = role_count["main"] / output_di_count if output_di_count else 0
    report = f"""# 菜谱数据库 V2 清洗报告

## 1. 处理范围与原则

- 数据源：`菜谱数据库_交付_20260918 (1)`，只读取、不修改。
- 规范依据：`菜谱数据库_V2_数据清洗与关联重构指南_Codex.md`。
- 目标：把食材主表收敛为基础原生食材；调味料、加工食品、成品、工具、操作语句和无法确认的碎片不进入主表。
- 映射策略：只使用明确别名、明确数量/形态剥离；不使用模糊包含匹配，不对 REVIEW 强行归并。
- 菜谱删减：删除高信号甜点/零食/油炸快餐、含糖饮品和相对低频异国菜；健康/低脂等明确标识优先保护。
- 营养阈值：仅在匹配率≥50%、重量置信度≥60%、总重量≥100g 时使用；能量≥400kcal/100g 且脂肪≥20g/100g 才作为补充删除证据。
- 精选规则：通过上述规则后，按家常/中式/清淡标签、步骤与用料完整度、营养完整度及同名频次排序；规范同名通常最多保留 {DISH_MAX_SAME_TITLE} 版，并优先覆盖所有仍有候选菜谱的核心食材。
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
| 完整食材目录 | {len(catalog_rows):,} |
| 食材目录别名 | {len(alias_rows):,} |
| 复合用料组成关系 | {len(component_rows):,} |
| 季节日历节点 | {len(calendar_rows):,} |
| 时令食物记录 | {len(seasonal_food_rows):,} |
| 季节知识记录 | {len(seasonal_knowledge_rows):,} |
| 时令菜品标题关系 | {len(seasonal_link_rows):,} |

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
| 原菜谱总数 | 200,000 |
| 保留菜谱 | {kept_dish_count:,} |
| 删除菜谱合计 | {len(dropped_dishes):,} |
| 删除零有效食材菜谱 | {dish_drop_types['no_core_ingredient']:,} |
| 删除高糖/高脂/油炸高信号菜谱 | {dish_drop_types['unhealthy_high_signal']:,} |
| 删除含糖或高能量饮品 | {dish_drop_types['unhealthy_sugary_beverage']:,} |
| 删除可靠营养高能量高脂菜谱 | {dish_drop_types['unhealthy_nutrition_density']:,} |
| 删除国内相对低频异国/西式菜谱 | {dish_drop_types['low_use_foreign']:,} |
| 健康/地域规则通过后的候选菜谱 | {pretrim_candidate_count:,} |
| 精选库优先级删减 | {dish_drop_types['low_priority_catalog_trim']:,} |
| 原 dish_ingredients | {source_di_count:,} |
| 新 dish_ingredients | {output_di_count:,} |
| main | {role_count['main']:,} |
| seasoning | {role_count['seasoning']:,} |
| processed | {role_count['processed']:,} |
| composite | {role_count['composite']:,} |
| other_food | {role_count['other_food']:,} |
| generic | {role_count['generic']:,} |
| non_food | {role_count['non_food']:,} |
| 菜谱核心关联覆盖率（main/保留用料） | {relation_coverage:.2%} |
| 菜谱搜索关联 | {len(search_data):,} |
| 食材父子关系 | {len(hierarchy_pairs):,} |
| 原 dish_tags / 新 dish_tags | {source_dish_tag_count:,} / {dish_tag_count:,} |

保留菜谱的 `raw_name`、`raw_text`、`quantity` 均保留；SPLIT 因无法可靠分摊克数，`grams` 置空并标记 `split_unknown`。原 `ingredient_count` 不变，新增 `main_ingredient_count` 与 `search_ingredient_count`。删除类型、原因和证据见 `dropped_dishes.csv`。

每条 `dish_ingredients` 均有非空 `catalog_ingredient_id`。目录类型分布：{dict(catalog_type_counts)}。`ingredient_id` 继续指向590条核心原生食材，保持现有推荐与搜索兼容；调味料、加工食材、复合名称和待复核项通过完整目录闭环。

反向菜谱关联回归：{', '.join(f'{k}={v:,}' for k,v in reverse_counts.items())}。

“鸡肉”搜索展开回归：鸡腿/鸡胸肉/鸡翅菜谱共 {len(child_dishes):,} 道，全部可由鸡肉检索到。

## 5. 季节数据整合

- `seasonal_calendar.csv` 统一承载 4 季、12 月、24 节气和 12 个传统节日，共 {len(calendar_rows):,} 个节点。
- `seasonal_food.csv` 共 {len(seasonal_food_rows):,} 条，匹配状态：{dict(seasonal_match_counts)}。
- 水果/蔬菜/普通食材如果不在原完整目录中，以 `seasonal_food` 类型补入完整目录，不进入590条核心营养食材表，也不伪造营养值。
- 来源中“菜品”优先匹配已有食材；无法作为食材的名称按菜名关键词关联，共形成 {len(seasonal_link_rows):,} 条精选菜谱关系。
- `seasonal_knowledge.csv` 共 {len(seasonal_knowledge_rows):,} 条，其中 {sum(bool(row['seasonal_food_id']) for row in seasonal_knowledge_rows):,} 条连接具体时令食物，其余为汇总知识。

## 6. 其他关联与覆盖率

| 指标 | 原数量 | 新数量 |
|---|---:|---:|
| ingredient_effects | {rel_stats['ingredient_effects.csv'][0]:,} | {rel_stats['ingredient_effects.csv'][1]:,} |
| ingredient_groups | {rel_stats['ingredient_groups.csv'][0]:,} | {rel_stats['ingredient_groups.csv'][1]:,} |

- 营养数据覆盖率：{nutrition_covered}/{len(ordered_names)} = {nutrition_covered/len(ordered_names):.2%}
- 功效数据覆盖率：{effects_covered}/{len(ordered_names)} = {effects_covered/len(ordered_names):.2%}
- 六个代表营养映射：{', '.join(f'{k}={"通过" if v else "失败"}' for k,v in nutrition_check.items())}

## 7. 完整性与回归测试

- 新食材 ID 连续：通过（1..{len(ordered_names)}）。
- 食材名称唯一：通过。
- dish_ingredients 食材外键孤儿：{orphan_ingredients}。
- dish_ingredients 菜品外键孤儿：{orphan_dishes}。
- dish_ingredients 完整目录空值/孤儿：{missing_catalog}/{orphan_catalog}。
- 完整目录别名孤儿：{orphan_aliases}；复合用料组成关系孤儿：{orphan_components}。
- ingredient_effects 外键孤儿：{orphan_effects}。
- ingredient_groups 外键孤儿：{orphan_groups}。
- ingredient_hierarchy 外键/自环错误：{orphan_hierarchy}。
- dish_ingredient_search 外键孤儿：{orphan_search}，重复键：{duplicate_search}。
- 季节日历、时令食物、季节知识和菜谱关系：数量与源表一致，外键零孤儿，重复键为0。
- 删除菜谱在 dish_ingredients、dish_tags、dish_nutrition、dish_ingredient_search 中残留：0。
- 指南“必须存在”清单：全部通过。
- 指南“必须不存在”清单：全部通过。
- 全部 16,693 个旧名称均分配 KEEP/MERGE/DROP/SPLIT/REVIEW 动作。

## 8. 审计边界

- `REVIEW` 不进入主表，等待人工确认；不能确定的 `SPLIT` 只保留菜谱原文，不伪造克数。
- MERGE 不合并或平均营养值；canonical 行只使用自身权威营养来源。新增“鸡腿、虾”规范名不继承模糊物种营养。
- `dish_nutrition` 是历史估算，只能按 legacy 使用；未来如需 V2 营养，应基于完整原料体系另行重算。
"""
    (TEMP / "CLEANING_REPORT.md").write_text(report, encoding="utf-8")

    # 输出清单，便于开发验收。
    readme = """# cleaned_v2 交付说明

本目录由 `../scripts/clean_v2.py` 从原始交付目录和 `../seasonal_source` 确定性生成。

- 先阅读 `CLEANING_REPORT.md`。
- `main_ingredient.csv` 保留590条核心原生食材，用于推荐、营养和层级搜索。
- `ingredient_catalog.csv` 覆盖全部菜谱用料和季节数据补充食材；每条 `dish_ingredients` 都有非空 `catalog_ingredient_id`。
- `ingredient_catalog_aliases.csv` 保存菜谱原名称到规范目录名称的映射。
- `dish_ingredient_components.csv` 保存“葱姜蒜、青红椒”等复合用料的确定组成。
- `ingredient_id_map.csv` 是所有旧 ID 的审计映射。
- `review_ingredients.csv` 保留仍需人工确认的旧名称。
- `dropped_dishes.csv` 是菜谱删除审计清单，含类型、原因和命中证据。
- `ingredient_hierarchy.csv` 保存通用食材与具体部位/品种关系。
- `dish_ingredient_search.csv` 已展开父级搜索，例如鸡肉可查到鸡腿、鸡胸肉和鸡翅菜谱。
- `seasonal_calendar.csv` 保存季节、月份、二十四节气和传统节日。
- `seasonal_food.csv` 将时令名称连接到核心/完整食材目录，或保留为节令菜名关键词。
- `seasonal_dish_links.csv` 保存节令菜名关键词与精选菜谱的标题关系。
- `seasonal_knowledge.csv` 保存具体食物知识和汇总知识，并连接日历与时令食物。
- 导入前先执行 `schema.sql`，再配置环境变量运行 `load_to_mysql.py`。
"""
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
    print(f"OK old={len(rows)} new={len(ordered_names)} dishes={kept_dish_count}/{kept_dish_count + len(dropped_dishes)} actions={dict(counts)} roles={dict(role_count)} output={OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
