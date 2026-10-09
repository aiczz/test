"""从完整清洗库（10000 道）里精选出一个「够用、干净、有图」的交付目录。

【为什么要精选】
10000 道菜对产品不是优势，是负担：
  · 前端首屏要拉 3.5 MB JSON（gzip 后约 600KB）才能渲染菜谱页；
  · 9500 道没有配图，卡片上是一片「暂无配图」，观感很差；
  · 分类被摊薄 —— 45 个分类，有些只剩几道，点进去像坏了。
精选到 700 道之后：每一道要么有图、要么是明确的家常菜，
每个分类都有足够内容，首屏数据量降到 1/14。

【选法（可复现，规则全在下面）】
  A 组 · 有配图的
      菜名能对上 `front/mealmind/lib/data/dish_images.dart` 里的图。
      实测 625 道，但只有 481 个**不同菜名** —— 同名的是重复条目
      （同一个菜被清洗成了多条），按菜名去重，保留数据质量最好的那条。
  B 组 · 没配图的，按规则补到总数 700
      硬门槛（缺一不可）：
        · 至少落进一个**筛选区里的核心分类**（这就是"分类明确"）
        · 菜名能过「可推荐菜名」检查（不太长、不含营销词/教程词）
        · 配料匹配率 >= 0.85（整菜营养是按配料算的，匹配差就没法信）
        · 配料数 3~12（少于 3 是残次品，多于 12 不是家常菜）
        · 有热量、有钠
        · 菜名不与已选的重复
      打分（"常见"的代理指标）：
        · 主料命中「常见食材表」的个数 —— 最常见的那批
          （鸡蛋/青椒/胡萝卜/土豆/番茄/猪肉/牛肉/鸡肉/虾/白菜/茄子/黄瓜…）
        · 分类数 2~4 个（既不是没分类，也不是堆了六个标签）
        · 配料里核心食材占比
        · 菜名短（家常菜名一般 3~6 字）

【输出】
    sql/catalog_v1/   6 张 CSV（其中 3 张是过滤后的子集）+ README

跑法：
    python sql/scripts/curate_catalog.py            # 生成
    python sql/scripts/curate_catalog.py --check    # 只看统计，不写文件
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "back"))

from app.data.dish_tags import (  # noqa: E402
    ALL_CANONICAL_TAGS,
    canonical_dish_tags,
    canonical_tag,
)
from app.services.scoring_service import is_recommendable_dish_name  # noqa: E402

SRC = ROOT / "sql" / "cleaned_v2"
OUT = ROOT / "sql" / "catalog_v1"
DISH_IMAGES = ROOT / "front" / "mealmind" / "lib" / "data" / "dish_images.dart"

TARGET_TOTAL = 700

# 每个分类希望达到的道数。
#
# 【为什么不能只设一个统一下限】
# 第一版给每个分类都设「至少 8 道」，结果是这样的：
#     家常菜 658（94%，等于筛不动）  炒 17   清淡 9   粥 8
# 原因是「家常菜」这种宽标签几乎每道菜都有，随便选都能满足，
# 于是 219 个补选名额全被它吃掉了，而「炒」「清淡」这些**真正用来筛菜**的
# 维度根本没补上。
#
# 所以改成按分类设目标，再用**贪心覆盖**去填：每一轮挑那道
# 「最能填上当前缺口」的菜（覆盖的未达标分类最多），同分再看质量分。
# 这样有限的 219 个名额会优先补齐稀疏的维度。
#
# 家常菜不设目标 —— 它是兜底标签，本来就该覆盖大多数菜。
CATEGORY_TARGETS: dict[str, int] = {
    # 家常快手（快手菜/下饭菜在 A 组里已经很多，目标定低一点避免挤占名额）
    "快手菜": 200, "下饭菜": 200, "宴客菜": 50, "下酒菜": 20,
    # 品类
    "素菜": 60, "汤羹": 70, "面点主食": 60, "饭": 40, "粥": 20,
    "凉菜": 40, "水产海鲜": 60,
    # 做法
    "蒸": 35, "炒": 45, "炖煮焖": 75, "煎烤炸": 25, "红烧卤味": 50,
    # 口味
    "清淡": 25, "辣": 50,
    # 人群 · 目标
    "低脂减重": 45, "早餐": 40, "养生滋补": 25,
    # 主要食材
    "鸡肉": 20, "猪肉": 20, "牛肉": 20, "鸡蛋": 20,
    "豆腐豆制品": 20, "蔬菜": 25,
}

# 每个核心分类至少要有这么多道，否则界面上的分类会显得空
MIN_PER_CATEGORY = 8

# 主料里出现这些词，基本就是调料而不是"主料"—— 蒜姜葱几乎每道菜都有
_SEASONING_LIKE = {
    "蒜", "姜", "葱", "香菜", "小米椒", "辣椒", "米辣", "红椒", "干辣椒",
    "花椒", "青蒜", "蒜苗", "蒜苔", "姜片", "洋葱丝",
}

# 要写进 catalog_v1 的文件；前三个会被过滤，后三个原样复制
COPY_AS_IS = [
    ("db_ingredients.csv", "ingredients"),
    ("db_seasonal_calendar.csv", "seasonal_calendar"),
    ("db_seasonal_food.csv", "seasonal_food"),
]
FILTER_BY_DISH = [
    ("db_dishes.csv", "dishes", "id"),
    ("db_dish_ingredients.csv", "dish_ingredients", "dish_id"),
    ("seasonal_dish_links.csv", "seasonal_dish_links", "dish_id"),
]


def image_dish_names() -> set[str]:
    """dish_images.dart 里配了图的菜名。"""
    text = DISH_IMAGES.read_text(encoding="utf-8")
    return set(re.findall(r"'([^']+)'\s*:\s*'assets/", text))


# =====================================================================
# 数据来源：**完整清洗库的 CSV**，不是 back/shishi.db
#
# ⚠️ 这里踩过一个坑：第一版直接读 `back/shishi.db`。跑完第一次精选、
#    把那个库导入成 700 道之后，再跑一次就变成「从 700 道里再选 700 道」
#    —— 候选池只剩 219，结果只选出 661 道，而且每跑一次就少一批。
#    精选脚本必须是**纯 CSV → CSV** 的变换：输入永远是完整的清洗结果，
#    跟当前工作库里装了多少道毫无关系。
# =====================================================================


def read_csv(filename: str) -> list[dict[str, str]]:
    with (SRC / filename).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _int(value: str | None) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def dish_rows() -> list[dict]:
    rows = []
    for raw in read_csv("db_dishes.csv"):
        rows.append({
            "id": _int(raw.get("id")),
            "dish_name": (raw.get("dish_name") or "").strip(),
            "tags_json": raw.get("tags_json") or "",
            "matched_ratio": _float(raw.get("matched_ratio")),
            "ingredient_count": _int(raw.get("ingredient_count")),
            "energy_kcal": _float(raw.get("energy_kcal")),
            "na_mg": _float(raw.get("na_mg")),
        })
    return rows


def common_ingredient_ids() -> set[int]:
    """「常见食材表」：被最多菜当作**主料**用、且不是调料的那批核心食材。

    注意用 role='main' 而不是 usage_count —— 后者会被蒜姜葱这种
    "每道菜都放一点"的调料刷到榜首，那不是"常见食材"，那是"常用调料"。
    """
    ingredients = read_csv("db_ingredients.csv")
    core = {
        _int(raw.get("id"))
        for raw in ingredients
        if (raw.get("is_core_raw") or "").strip() in {"1", "1.0", "True", "true"}
    }
    names = {_int(raw.get("id")): (raw.get("name") or "").strip()
             for raw in ingredients}

    counts: Counter[int] = Counter()
    for raw in read_csv("db_dish_ingredients.csv"):
        if (raw.get("role") or "").strip() != "main":
            continue
        food_id = _int(raw.get("ingredient_id"))
        if food_id is not None and food_id in core:
            counts[food_id] += 1

    picked: set[int] = set()
    for food_id, _count in counts.most_common():
        if names.get(food_id, "") in _SEASONING_LIKE:
            continue
        picked.add(food_id)
        if len(picked) >= 40:  # 取前 40 个真·常见主料
            break
    return picked


def seasonal_linked_ids() -> set[int]:
    """带 seasonal_dish_links 的菜 —— 时令信号最直接的那批。"""
    ids = set()
    for raw in read_csv("seasonal_dish_links.csv"):
        value = _int(raw.get("dish_id"))
        if value is not None:
            ids.add(value)
    return ids


def main_ingredient_ids() -> dict[int, set[int]]:
    """每道菜的主料 id（role='main'）。"""
    result: dict[int, set[int]] = defaultdict(set)
    for raw in read_csv("db_dish_ingredients.csv"):
        if (raw.get("role") or "").strip() != "main":
            continue
        dish_id, food_id = _int(raw.get("dish_id")), _int(raw.get("ingredient_id"))
        if dish_id is not None and food_id is not None:
            result[dish_id].add(food_id)
    return result


def core_tags_of(row: dict, name: str | None = None) -> list[str]:
    try:
        raw = json.loads(row["tags_json"]) if row["tags_json"] else []
    except (TypeError, ValueError):
        raw = []
    tags = canonical_dish_tags(raw, name or row["dish_name"])
    return [t for t in tags if t in ALL_CANONICAL_TAGS]


def quality_score(
    row: dict, tags: list[str], common_hits: int, seasonal_linked: bool = False
) -> float:
    """越大越"常见、清晰"。规则见模块顶部。"""
    score = 0.0
    # 主料踩中几个常见食材 —— 这是"家常"最强的一个信号
    score += min(common_hits, 3) * 3.0
    # 分类数：2~4 最舒服（一个分类太少，六个就杂了）
    if 2 <= len(tags) <= 4:
        score += 2.0
    elif len(tags) == 1:
        score += 0.5
    # 配料数：3~8 是家常菜的典型区间
    count = row["ingredient_count"] or 0
    if 3 <= count <= 8:
        score += 1.5
    elif 9 <= count <= 12:
        score += 0.6
    # 菜名短的好（家常菜名一般 3~6 字）
    length = len(row["dish_name"])
    if 3 <= length <= 6:
        score += 1.5
    elif length <= 9:
        score += 0.6
    # 配料匹配率越高，整菜营养越可信
    ratio = row["matched_ratio"] or 0
    score += min(ratio, 1.0) * 1.0
    # ★ 有时令关联的菜优先保留。
    #   全库只有 88 道带 seasonal_dish_links，而时令我们在打分里给的是最大权重
    #   （3.0）—— 第一版没管这件事，精选后只剩 15 条关联，
    #   等于把设计好的时令信号砍掉大半。加这个奖励把那 88 道尽量捞进精选集。
    if seasonal_linked:
        score += 6.0
    return score


def passes_hard_gate(row: dict, tags: list[str]) -> bool:
    if not tags:
        return False
    if not is_recommendable_dish_name(row["dish_name"]):
        return False
    if (row["matched_ratio"] or 0) < 0.85:
        return False
    count = row["ingredient_count"] or 0
    if not 3 <= count <= 12:
        return False
    if row["energy_kcal"] is None or row["na_mg"] is None:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="精选交付目录")
    parser.add_argument("--check", action="store_true", help="只统计，不写文件")
    parser.add_argument("--target", type=int, default=TARGET_TOTAL)
    args = parser.parse_args()

    with_image = image_dish_names()
    rows = dish_rows()
    common = common_ingredient_ids()
    mains = main_ingredient_ids()
    seasonal = seasonal_linked_ids()

    print(f"完整库：{len(rows)} 道；配了图的菜名：{len(with_image)} 个")
    print(f"常见主料（前 40）：{len(common)} 个\n")

    # ---- A 组：有配图的，同名去重（保留质量最好的） ----
    #
    # ⚠️ 这里**也要过菜名质量检查**。第一版只看了「有没有图」，
    #    结果混进来 39 条抓取来的营销长标题（「㊙️不加一滴水‼️仔姜炒鸡‼️
    #    鸡肉鲜嫩一秒上头」，平均 19.8 字）—— 有图也没法看。
    #    实测 481 个有图的菜名里 442 个是正常菜名，只损失 39 道。
    by_name: dict[str, dict] = {}
    skipped_names: list[str] = []
    for row in rows:
        name = row["dish_name"]
        if name not in with_image:
            continue
        if not is_recommendable_dish_name(name):
            skipped_names.append(name)
            continue
        tags = core_tags_of(row)
        hits = len(mains.get(row["id"], set()) & common)
        row["_tags"] = tags
        row["_score"] = quality_score(row, tags, hits, row["id"] in seasonal)
        best = by_name.get(name)
        if best is None or row["_score"] > best["_score"]:
            by_name[name] = row
    picked = list(by_name.values())
    print(f"A 组（有配图 + 菜名能看，按菜名去重）：{len(picked)} 道")
    if skipped_names:
        print(f"  因菜名不像菜名而剔除：{len(skipped_names)} 道"
              f"（例如「{skipped_names[0][:28]}…」）")

    # ---- B 组：没配图的，过硬门槛后打分 ----
    candidates: list[dict] = []
    for row in rows:
        if row["dish_name"] in with_image:
            continue
        tags = core_tags_of(row)
        if not passes_hard_gate(row, tags):
            continue
        hits = len(mains.get(row["id"], set()) & common)
        row["_tags"] = tags
        row["_score"] = quality_score(row, tags, hits, row["id"] in seasonal)
        row["_hits"] = hits
        candidates.append(row)

    print(f"B 组候选（过硬门槛）：{len(candidates)} 道")
    # 同名的高分优先
    candidates.sort(key=lambda r: (-r["_score"], r["id"]))

    budget = max(0, args.target - len(picked))
    print(f"还要补 {budget} 道来凑满 {args.target}\n")

    # ---- 配额：贪心覆盖，优先补齐稀疏的分类 ----
    have: Counter[str] = Counter()
    for row in picked:
        have.update(row["_tags"])

    taken_names = {row["dish_name"] for row in picked}
    chosen: list[dict] = []

    # 第 0 轮：带时令关联的菜**先无条件收进来**。
    #
    # 全库只有 88 道有 seasonal_dish_links，而时令是打分里权重最高的因子（3.0）。
    # 靠质量分奖励只能捞回一部分（实测 15 → 34），因为贪心覆盖那轮是按
    # 「谁填的缺口多」选的，不看分数。时令这种东西漏一道少一道，
    # 所以单独给它们一轮。
    for row in candidates:
        if len(chosen) >= budget:
            break
        if row["id"] in seasonal:
            taken_names.add(row["dish_name"])
            chosen.append(row)
            have.update(row["_tags"])

    if chosen:
        print(f"其中「有时令关联」优先保留：{len(chosen)} 道")

    def deficit() -> dict[str, int]:
        return {
            tag: max(0, CATEGORY_TARGETS.get(tag, MIN_PER_CATEGORY) - have[tag])
            for tag in ALL_CANONICAL_TAGS
        }

    # 第一轮：贪心覆盖 —— 每轮挑「最能填上当前缺口」的那道
    #
    # 8261 个候选 × 最多 219 轮，每轮扫一遍候选算覆盖数：
    # 实测一两秒，没必要上更聪明的数据结构。
    while len(chosen) < budget:
        gaps = deficit()
        if not any(gaps.values()):
            break
        best_row = None
        best_gain = 0
        best_score = float("-inf")
        for row in candidates:
            if row["dish_name"] in taken_names:
                continue
            gain = sum(gaps[t] for t in row["_tags"] if gaps[t] > 0)
            if gain <= 0:
                continue
            # 先看覆盖的缺口总量，再看质量分，最后按 id 保证确定性
            if gain > best_gain or (
                gain == best_gain and row["_score"] > best_score
            ):
                best_row, best_gain, best_score = row, gain, row["_score"]
        if best_row is None:
            break
        taken_names.add(best_row["dish_name"])
        chosen.append(best_row)
        have.update(best_row["_tags"])

    # 第二轮：缺口补完了还有名额，就按质量分把剩下的填满
    for row in candidates:
        if len(chosen) >= budget:
            break
        if row["dish_name"] in taken_names:
            continue
        taken_names.add(row["dish_name"])
        chosen.append(row)
        have.update(row["_tags"])

    final = picked + chosen
    print(f"B 组实际选了 {len(chosen)} 道")
    print(f"合计 {len(final)} 道\n")

    final_tags: Counter[str] = Counter()
    for row in final:
        final_tags.update(row["_tags"])

    print("=== 精选后的分类分布 ===")
    for tag in ALL_CANONICAL_TAGS:
        print(f"  {tag:<12} {final_tags[tag]}")

    thin = [t for t in ALL_CANONICAL_TAGS if final_tags[t] < MIN_PER_CATEGORY]
    if thin:
        print(f"\n⚠️ 不足 {MIN_PER_CATEGORY} 道的分类：{thin}")

    unnamed = [row["dish_name"] for row in final if not row["_tags"]]
    print(f"\n没有任何核心分类的：{len(unnamed)} 道")

    if args.check:
        print("\n（--check：没有写文件）")
        return 0

    # ---- 写文件 ----
    ids = {int(row["id"]) for row in final}
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, _table, key in FILTER_BY_DISH:
        src = SRC / filename
        dst = OUT / filename
        with src.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            fields = reader.fieldnames or []
            kept = 0
            with dst.open("w", encoding="utf-8", newline="") as out:
                writer = csv.DictWriter(out, fieldnames=fields)
                writer.writeheader()
                for record in reader:
                    try:
                        value = int(record[key])
                    except (TypeError, ValueError):
                        continue
                    if value in ids:
                        writer.writerow(record)
                        kept += 1
        print(f"  写出 {filename:<28} {kept} 行")

    for filename, _table in COPY_AS_IS:
        shutil.copyfile(SRC / filename, OUT / filename)
        print(f"  复制 {filename:<28}（原样）")

    (OUT / "README.md").write_text(
        render_readme(final, final_tags, with_image), encoding="utf-8"
    )
    print(f"  写出 README.md")
    print(f"\n完成 → {OUT}")
    return 0


def render_readme(final, final_tags, with_image) -> str:
    rows = "\n".join(
        f"| {tag} | {final_tags[tag]} |" for tag in ALL_CANONICAL_TAGS
    )
    return f"""# 精选菜谱目录 v1（{len(final)} 道）

**这是交付给服务器导入的那份目录。**完整清洗库（10000 道）在
`../cleaned_v2/`，仍然保留，只是不用于部署。

## 为什么是 {len(final)} 道

10000 道对产品是负担：首屏要拉 3.5 MB JSON、9500 道没有配图
（卡片上一片「暂无配图」）、45 个分类被摊薄到有些只剩几道。
精选之后每一道要么有图、要么是明确的家常菜，分类也都撑得起来。

## 怎么选出来的

规则全部写在 `../scripts/curate_catalog.py` 里，可重跑：

**A 组 · 有配图的（{len(with_image)} 个菜名）**
对得上 `front/mealmind/lib/data/dish_images.dart` 的菜名；
同名条目按数据质量去重（同一个菜在清洗结果里有多条）。

**B 组 · 没配图的，按规则补**
硬门槛：至少落进一个筛选区里的核心分类、菜名能过「可推荐菜名」检查、
配料匹配率 ≥ 0.85、配料数 3~12、有热量和钠。
打分：主料命中「常见食材表」的个数 + 分类数 2~4 + 配料数 3~8 + 菜名短 + 匹配率。
另外保证每个分类至少有 8 道。

## 分类分布

| 分类 | 道数 |
|---|---|
{rows}

## 重新生成

```bash
python sql/scripts/curate_catalog.py
```

改完 `back/app/data/dish_tags.py` 的 `TAG_GROUPS`（那是筛选区里会出现哪些分类）
之后要重跑一次 —— 分类变了，每类的配额也会跟着变。
"""


if __name__ == "__main__":
    raise SystemExit(main())
