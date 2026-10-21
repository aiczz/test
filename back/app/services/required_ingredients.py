"""Explicit ingredient inclusion, checked against ingredient records, not titles."""
from __future__ import annotations

import re

# Generic animal requests must not be satisfied by flavourings or lookalike names.
ANIMALS = {
    '鱼': (r'鱼|三文|龙利|巴沙', r'鱿鱼|章鱼|墨鱼|乌贼|鲍鱼|鳄鱼|鱼香|鱼露|鱼油|鱼腥草|鱼豆腐|鱼胶|鱼肝油'),
    '鸡肉': (r'鸡', r'鸡蛋|鸡精|鸡粉|鸡汁|鸡腿菇|鸡油|鸡高汤'),
    '牛肉': (r'牛|肥牛', r'牛奶|牛乳|牛油|牛油果|牛蒡|牛肉粉'),
    '猪肉': (r'猪|五花肉|里脊|瘦肉|培根|火腿|排骨', r'猪油'),
    '羊肉': (r'羊', r'羊奶|羊乳|羊肚菌'),
    '虾': (r'虾', r'虾酱|虾油|虾皮|虾粉'),
    '鸭肉': (r'鸭', r'鸭蛋|鸭油'),
    '蟹': (r'蟹', r'蟹味菇|蟹柳|蟹棒'),
    '贝类': (r'贝|蛤|蚬|蚝|牡蛎|鲍鱼|螺肉', r'蚝油|贝母'),
    '鱿鱼': (r'鱿鱼|章鱼|墨鱼|乌贼|八爪鱼', r'墨鱼汁'),
    '兔肉': (r'兔', r'兔耳草'),
    '鹅肉': (r'鹅', r'鹅蛋|鹅油'),
    '其他肉类': (r'肉类|肉馅|肉末|肉糜|午餐肉|肠|鱼豆腐', r'鸡肉|鱼肉|牛肉|猪肉|羊肉|鸭肉|鹅肉|兔肉|植物肉|素肉|肠粉|素肠'),
}
ALIASES = {'鱼肉': '鱼', '鱼类': '鱼', '鸡': '鸡肉', '牛': '牛肉', '猪': '猪肉',
           '羊': '羊肉', '鸭': '鸭肉', '虾肉': '虾', '虾类': '虾'}


def edit(message: str, previous: list[str] | None, terms: list[str]) -> list[str] | None:
    """None means no edit; [] explicitly cancels a previous restriction."""
    if re.search(r'什么意思|为什么|是否|吗[？?]?$|怎么理解', message):
        return None
    if re.search(r'取消食材限制|不限食材|取消只(?:要|吃|推荐)|不要只(?:要|吃|推荐)|不只(?:要|吃)|不再只(?:要|吃)', message):
        return []
    vocabulary = set(terms) | set(ANIMALS) | set(ALIASES)
    result = None
    for match in re.finditer(r'(?<!不)(?:只要|只吃|只推荐|仅推荐|仅要|全部换成|都换成|^换成)\s*([^，,。；;！!？?]+)', message):
        tail = match[1].strip()
        if tail not in vocabulary:
            tail = re.sub(r'(?:的菜谱|的菜|菜谱|就行了?|即可|都可以|吧|呢|了|的)+$', '', tail).strip()
            if tail.endswith('菜') and tail[:-1] in vocabulary:
                tail = tail[:-1]
        targets = re.split(r'和|或|、', tail)
        if re.match(r'^[0-9零一二两三四五六七八九十]+(?:道|到|个|种|样|款|$)', tail) or tail in {
            '汤', '素菜', '荤菜', '全素', '不辣', '清淡', '少盐', '低钠', '高蛋白',
            '图片', '配图', '食材', '菜谱', '步骤', '简单的', '快手菜',
        }:
            continue
        if targets and all(t in vocabulary for t in targets):
            result = list(dict.fromkeys(ALIASES.get(t, t) for t in targets))
        elif re.fullmatch(r'[\u4e00-\u9fff]{1,12}', tail) and re.search(r'鱼|虾|蟹|肉|菇|豆|菜|瓜|蛋', tail):
            # An unknown explicit ingredient must fail closed, never silently become
            # an unrestricted recommendation. Unsupported targets produce no matches.
            result = [tail]
    return result


def animal_groups(name: str) -> set[str]:
    return {key for key, (positive, negative) in ANIMALS.items()
            if re.search(positive, name) and not re.search(negative, name)}


def matches(names: list[str] | tuple[str, ...], required: tuple[str, ...] | list[str]) -> bool:
    if not required:
        return True
    def contains(target: str, name: str) -> bool:
        target = ALIASES.get(target, target)
        if target in ANIMALS:
            return target in animal_groups(name)
        return target in name
    if not any(contains(target, name) for target in required for name in names):
        return False
    # "Only fish" allows vegetables/tofu/eggs, but not beef/chicken as a second meat.
    allowed = {group for target in required for group in animal_groups(target)}
    return not allowed or not any(animal_groups(name) - allowed for name in names)
