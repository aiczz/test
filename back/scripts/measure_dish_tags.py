"""量一下菜品标签归一化到底做到什么程度（开发期自检脚本，不参与运行时）。

跑法：
    python scripts/measure_dish_tags.py

它回答三个问题：
1. 归一化后还剩多少个不同的展示标签？（卡片上会看到的名字）
2. 每个筛选分类各有多少道菜？有没有「点进去是空的」？
3. 哪些原始标签没能进任何分类？出现次数多少？（长尾白名单的依据）
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.dish_tags import (  # noqa: E402
    ALL_CANONICAL_TAGS,
    TAG_GROUPS,
    canonical_tag,
)

DB = ROOT / "shishi.db"


def main() -> int:
    conn = sqlite3.connect(str(DB))
    rows = conn.execute("SELECT tags_json FROM dishes").fetchall()
    conn.close()

    total = 0
    no_tags = 0
    covered = 0
    tag_counter: Counter[str] = Counter()
    canon_counter: Counter[str] = Counter()
    unclassified: Counter[str] = Counter()

    for (raw,) in rows:
        total += 1
        try:
            tags = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            tags = []
        if not isinstance(tags, list) or not tags:
            no_tags += 1
            tags = []

        hit_canon: set[str] = set()
        for tag in tags:
            text = str(tag).strip()
            if not text:
                continue
            tag_counter[text] += 1
            canon = canonical_tag(text)
            if canon:
                hit_canon.add(canon)
                canon_counter[canon] += 1
            else:
                unclassified[text] += 1

        if hit_canon:
            covered += 1

    print(f"菜品总数            {total}")
    print(f"完全没有标签的菜     {no_tags}")
    print(f"至少落进一个分类的   {covered}  ({covered / total:.1%})")
    print(f"原始标签去重数       {len(tag_counter)}")
    print(f"只出现一次的原始标签 {sum(1 for c in tag_counter.values() if c == 1)}")
    print()

    print("=== 分组覆盖 ===")
    empty: list[str] = []
    for group, tags in TAG_GROUPS:
        print(f"[{group}]")
        for tag in tags:
            count = canon_counter.get(tag, 0)
            if count == 0:
                empty.append(tag)
            print(f"   {tag:<12} {count}")
    print()

    missing = [t for t in ALL_CANONICAL_TAGS if canon_counter.get(t, 0) == 0]
    if missing:
        print(f"⚠️ 规则定义了但一道菜都没有的分类：{missing}")

    print("=== 未归类的原始标签（出现 >=5 次）===")
    for tag, count in unclassified.most_common():
        if count >= 5:
            print(f"   {tag:<20} {count}")
    print(f"   未归类标签出现总次数 {sum(unclassified.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
