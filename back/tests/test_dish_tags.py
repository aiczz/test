"""菜品标签归一化 + 菜谱分类筛选的测试。

对应两个真实发生过的问题：
1. 菜谱页分类点进去是空的 —— 前端写死「家常」，库里是「家常菜」，字符串对不上；
2. 库里 985 个原始标签里有 571 个只出现一次，同一件事有四五种写法。

这里的断言分三层：
· 规则层：同义写法必须归到同一个规范名，且**顺序陷阱**不能复发；
· 一致性层：规则产出的每个规范名都必须出现在分组表里（否则界面上永远看不到它）；
· 接口层：分类区报的菜品数 == 按这个分类筛出来的菜品数。
"""

from sqlalchemy import text
from sqlmodel import Session, create_engine
from sqlmodel.pool import StaticPool

from app.data.dish_tags import (
    ALL_CANONICAL_TAGS,
    RETIRED_TAGS,
    TAG_GROUPS,
    _RULES,
    canonical_dish_tags,
    canonical_tag,
    is_filter_tag,
)
from app.services import recipe_service


# =====================================================================
# 规则层
# =====================================================================

def test_synonyms_collapse_to_one_name():
    """同一件事的不同写法必须归一 —— 这是「点了分类没有菜」的根因。"""
    for raw, expected in (
        ("家常", "家常菜"),
        ("家常菜", "家常菜"),
        ("汤", "汤羹"),
        ("汤羹", "汤羹"),
        ("老火汤", "汤羹"),
        ("素食", "素菜"),
        ("纯素", "素菜"),
        ("宴客", "宴客菜"),
        ("下饭", "下饭菜"),
        ("下饭菜", "下饭菜"),
        ("面条", "面点主食"),
        ("拌面", "面点主食"),
        ("低脂", "低脂减重"),
        ("香辣", "辣"),
    ):
        assert canonical_tag(raw) == expected, raw


def test_rule_order_traps_do_not_regress():
    """顺序陷阱的回归测试（每一条都是踩过的坑）。

    规则是「从上往下第一条命中即返回」，所以宽泛规则放在具体规则前面
    就会把具体的吃掉。下面每一条都对应一次真实的误分类。
    """
    # 「下饭菜」含「饭」，曾整个被「饭」规则吃掉 → 分类页显示 0 道
    assert canonical_tag("下饭菜") == "下饭菜"
    assert canonical_tag("蛋炒饭") == "饭"
    # 「年夜饭」同上
    assert canonical_tag("年夜饭") == "年夜饭"
    assert canonical_tag("年夜饭必备") == "年夜饭"
    # 「鸡蛋」含「鸡」，曾被「鸡肉」规则吃掉
    assert canonical_tag("鸡蛋") == "鸡蛋"
    assert canonical_tag("番茄鸡蛋") == "鸡蛋"
    assert canonical_tag("鸡翅") == "鸡肉"
    assert canonical_tag("鸡胸肉") == "鸡肉"
    # 裸「蛋」会让「高蛋白」变成鸡蛋 —— 所以鸡蛋规则里不能有裸「蛋」
    assert canonical_tag("高蛋白") is None
    # 「炒面」含「炒」，必须先被主食规则吃掉
    assert canonical_tag("炒面") == "面点主食"
    assert canonical_tag("汤面") == "面点主食"
    # 「红烧肉」这类同时含做法和主料的，归做法
    assert canonical_tag("红烧牛肉") == "红烧卤味"


def test_rules_only_produce_grouped_or_retired_tags():
    """规则能产出的规范名，必须要么在分组表里、要么在 RETIRED_TAGS 里。

    漏一个的后果是：这个标签会出现在卡片上，既点不动、又没人知道它是有意退场的
    —— 正是用户抱怨的「标签和分类对不上」。

    ★ 精选目录（700 道）之后，筛选区从 45 个分类收窄到 28 个：
    「年夜饭」「便当」这类只剩几道，撑不起一个入口，退到 RETIRED_TAGS。
    但**规则留着** —— 删规则会让这些菜掉进更宽泛的桶里被错误归类
    （「年夜饭」会被「饭」规则吃掉，变成一道主食）。
    """
    produced = {canonical for _, canonical in _RULES}
    known = set(ALL_CANONICAL_TAGS) | set(RETIRED_TAGS)
    unknown = produced - known
    assert not unknown, f"这些规范标签既没归组、也没登记为退场：{unknown}"


def test_retired_tags_do_not_overlap_the_filter_groups():
    """退场的标签不能再出现在筛选区里，否则等于没收窄。"""
    overlap = set(RETIRED_TAGS) & set(ALL_CANONICAL_TAGS)
    assert not overlap, f"这些标签同时被标成退场和保留：{overlap}"


def test_retired_tags_are_not_filterable_but_stay_on_cards():
    """退场标签的两种表现要对得上：

    · `is_filter_tag` 是 False（筛选区里没有它）
    · 但菜的标签里仍然保留它（卡片上的分类依然准确，只是不可点）
    · 而且它必须排在**可点的核心分类之后** —— 卡片通常只显示前两个标签，
      排前面就成「显示一个点不动的分类」了
    """
    assert not is_filter_tag("年夜饭")
    assert is_filter_tag("家常菜")

    tags = canonical_dish_tags(["年夜饭", "家常菜", "汤"])
    assert "年夜饭" in tags, "退场不等于删掉，卡片上还要有"
    assert tags[:2] == ["家常菜", "汤羹"], f"核心分类必须排在前面，实际 {tags}"


def test_no_duplicate_tag_across_groups():
    """一个标签只能出现在一个分组里，否则筛选区会重复显示。"""
    seen: list[str] = []
    for _, tags in TAG_GROUPS:
        for tag in tags:
            assert tag not in seen, f"{tag} 出现在多个分组里"
            seen.append(tag)


def test_rules_have_no_duplicate_canonical():
    """同一个规范名只该有一条规则，否则改了其中一条会莫名其妙不生效。"""
    canonicals = [canonical for _, canonical in _RULES]
    assert len(canonicals) == len(set(canonicals))


def test_canonical_dish_tags_keeps_long_tail_and_orders_canonical_first():
    # 「夏天」是真实存在的长尾标签（全库 5 道菜），归不进任何一个分类
    tags = canonical_dish_tags(["夏天", "汤", "家常", "老火汤"])
    # 规范标签排前面并按分组顺序稳定排列，长尾标签原样留在后面
    assert tags == ["家常菜", "汤羹", "夏天"]
    # 「汤」和「老火汤」归成同一个后不能重复出现
    assert tags.count("汤羹") == 1


def test_canonical_dish_tags_falls_back_to_name():
    """`tags_json` 为空的菜靠菜名兜底。

    实测 43 道菜一个标签都没有（「牛肉面」「煎牛排」「腊八粥」…），
    不兜底的话它们在分类页里一道都点不到。
    """
    assert canonical_dish_tags([], "牛肉面") == ["面点主食"]
    assert canonical_dish_tags([], "煎牛排") == ["煎烤炸"]
    assert canonical_dish_tags([], "腊八粥") == ["粥"]
    # 有分类标签时不该再拿菜名去加料
    assert canonical_dish_tags(["汤"], "牛肉面") == ["汤羹"]
    # 名字也归不出来时返回空，而不是编一个
    assert canonical_dish_tags([], "蜜枣") == []


def test_is_filter_tag():
    assert is_filter_tag("快手菜")
    assert not is_filter_tag("秋日暖汤")
    assert not is_filter_tag("")


# =====================================================================
# 接口层（清洗库六表的最小副本）
# =====================================================================

def _compact_engine():
    """最小六表副本。

    ⚠️ 六张表**必须齐全**：`uses_compact_catalog` 在 auto 模式下会拒绝
    「只导入了一部分」的库并直接抛错（这是防止后端跑在残缺数据上的保护）。
    这里只往 dishes 里灌数据，另外五张建空表即可。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE dishes ("
                "id INTEGER PRIMARY KEY, dish_name TEXT, description TEXT, "
                "cuisine TEXT, instruction_text TEXT, tags_json TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE ingredients ("
                "id INTEGER PRIMARY KEY, name TEXT, category TEXT, "
                "is_edible INTEGER, is_core_raw INTEGER, effects_json TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE dish_ingredients ("
                "id INTEGER PRIMARY KEY, dish_id INTEGER, ingredient_id INTEGER, "
                "core_ingredient_id INTEGER, raw_name TEXT, raw_text TEXT, "
                "quantity TEXT, role TEXT, grams REAL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE seasonal_calendar ("
                "id TEXT PRIMARY KEY, level TEXT, name TEXT, season TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE seasonal_food ("
                "id TEXT PRIMARY KEY, calendar_id TEXT, level TEXT, "
                "time_name TEXT, season TEXT, ingredient_id INTEGER, note TEXT, "
                "recommendation_reason TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE seasonal_dish_links ("
                "seasonal_food_id TEXT, dish_id INTEGER, match_type TEXT)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO dishes VALUES "
                # 同一件事的不同写法，必须都归到「汤羹」
                "(1, '番茄蛋花汤', NULL, NULL, '煮 10 分钟', '[\"汤\", \"家常\"]'), "
                "(2, '老火例汤', NULL, NULL, '炖 90 分钟', '[\"老火汤\", \"家常菜\"]'), "
                # tags_json 为空 → 靠菜名兜底成「面点主食」
                "(3, '牛肉面', NULL, NULL, '煮 15 分钟', NULL), "
                # 完全归不出来，只用于验证「没有菜的分类不出现」
                "(4, '蜜枣', NULL, NULL, NULL, NULL)"
            )
        )
    return engine


def test_tag_groups_report_only_non_empty_categories():
    with Session(_compact_engine()) as session:
        groups = dict(recipe_service.tag_groups(session))
        assert groups, "分类区不该是空的"
        flat = {name: count for entries in groups.values() for name, count in entries}
        # 三道菜各自贡献一个分类
        assert flat["汤羹"] == 2
        assert flat["家常菜"] == 2
        assert flat["面点主食"] == 1
        # 一道菜都没有的分类不出现在界面上（点了才是空的）
        assert all(count > 0 for count in flat.values())
        assert "快手菜" not in flat
        # 分组名和顺序来自 dish_tags.TAG_GROUPS
        assert list(groups)[0] == TAG_GROUPS[0][0]


def test_tag_filter_matches_reported_count_and_dedupes():
    """分类区报的数字，必须等于按这个分类筛出来的条数。

    写「汤」和写「老火汤」的两道菜都得筛到，且一道菜不能因为
    多个原始标签命中同一个规范分类而被重复计数。
    """
    with Session(_compact_engine()) as session:
        listed = {name: count for _, tags in recipe_service.tag_groups(session) for name, count in tags}
        for tag, expected in listed.items():
            items, total = recipe_service.list_recipes(
                session, tag=tag, page=1, page_size=50
            )
            assert total == expected, tag
            assert len(items) == expected, tag
            assert items, f"{tag} 报有 {expected} 道菜，但筛不出内容"

        # 「汤羹」筛到的是 1 和 2，不是 4 条
        items, total = recipe_service.list_recipes(session, tag="汤羹", page=1, page_size=50)
        assert sorted(item.id for item in items) == [1, 2]

        # 卡片上显示的标签也是归一后的名字
        assert sorted(items[0].tags) == ["家常菜", "汤羹"]

        # 菜名兜底的那道菜也能被筛到
        items, total = recipe_service.list_recipes(session, tag="面点主食", page=1, page_size=50)
        assert [item.id for item in items] == [3]


def test_unknown_tag_filters_everything_out():
    """未知分类返回空，而不是悄悄忽略筛选条件把全库倒出来。"""
    with Session(_compact_engine()) as session:
        _, total = recipe_service.list_recipes(session, tag="不存在的分类", page=1, page_size=50)
        assert total == 0


def test_servings_are_not_fabricated_on_the_compact_catalog():
    """★ 清洗库的菜谱不能报一个编出来的「份量」。

    用户报过：「改了家庭人数之后，AI 那一页所有人数相关的还是没变化」。
    查下来就是这里 —— `dishes` 表**没有份量列**，而
    `RecipeRecord.servings` 默认写死 3，于是每一道菜的卡片上都是「3人份」。
    那个 3 是个常量，改家庭人数它当然一动不动。

    现在没有数据就不给值（null），前端按「没有这一项」处理。
    """
    with Session(_compact_engine()) as session:
        items, total = recipe_service.list_recipes(session, page=1, page_size=50)
        assert total > 0
        assert {item.servings for item in items} == {None}, (
            "清洗库没有份量列，就不该报一个数字"
        )


def test_home_schemas_tolerate_missing_servings():
    """★ servings 为 None 时，首页那几个结构不能炸。

    真实发生过：`MenuBrief.servings` 标的是必填 `str`，而清洗库
    `to_brief()` 给的是 `None` —— 于是整个 `/api/home` 直接 500。
    测试没发现是因为**测试夹具用的是旧演示库**，那里 `recipes.servings`
    是真的有值（整数 3），永远走不到 None 这条分支。
    只有清洗库才复现，所以这个用例必须建在 compact 夹具上。
    """
    from app.schemas.home import HomeRecipeItem, MenuBrief

    with Session(_compact_engine()) as session:
        items, _ = recipe_service.list_recipes(session, page=1, page_size=1)
        brief = items[0]
        assert brief.servings is None, "前提：清洗库的份量就是 None"

        # 首页把同一份 brief 塞进这两个结构，都必须合法
        MenuBrief(id=0, title="秋季家常菜单", image=None,
                  servings=brief.servings, tags=["当季推荐"])
        HomeRecipeItem(
            **brief.model_dump(), reason="当季食材", highlights=[], score=1.0
        )


def test_duration_flag_is_not_a_fabricated_number():
    """清洗库没有时长列：有依据的才给数字，没依据的必须标成估算。

    `_compact_engine` 里三道菜的做法都写了时间（「煮 10 分钟」这种），
    所以这里应该都是「有依据」；关键是**这个标记要真的传出来**，
    前端才能决定显不显示数字。
    """
    with Session(_compact_engine()) as session:
        items, _ = recipe_service.list_recipes(session, page=1, page_size=50)
        for item in items:
            if item.duration_estimated:
                # 估算的一律是兜底的 30 分钟 —— 前端据此显示「时长不详」
                assert item.duration_minutes == 30, item.name
