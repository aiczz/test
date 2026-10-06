"""量一下「烹饪时间」到底有多少是真数据、多少是估的。

背景：清洗库 `dishes` **没有时长列**，所以前端看到的那个数字有两条来源：
  1. `instruction_text`（做法文本）里抽出来的 —— 例如「小火炖 30 分钟」
  2. 抽不到就**默认 30 分钟**

第 2 条是估的，却和真数据长得一模一样地显示出来。这个脚本把比例量清楚，
免得把估算值说成事实。

跑法：python scripts/measure_durations.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, create_engine  # noqa: E402

from app.core.database import uses_compact_catalog  # noqa: E402
from app.repositories import catalog_insight_repository  # noqa: E402

DB = ROOT / "shishi.db"


def main() -> int:
    engine = create_engine(f"sqlite:///{DB.as_posix()}")
    with Session(engine) as session:
        if not uses_compact_catalog(engine):
            print("[x] 这个库不是清洗库")
            return 1

        ids = [
            int(row[0])
            for row in session.execute(
                __import__("sqlalchemy").text("SELECT id FROM dishes")
            )
        ]
        insights = catalog_insight_repository.dish_insights(session, ids)

    sources: Counter[str] = Counter()
    buckets: Counter[str] = Counter()
    samples: dict[str, list[str]] = {"table": [], "text": [], "estimated": []}

    for insight in insights.values():
        sources[insight.duration_source] += 1
        minutes = insight.duration_minutes
        buckets[
            "≤10" if minutes <= 10
            else "11-20" if minutes <= 20
            else "21-30" if minutes <= 30
            else "31-60" if minutes <= 60
            else ">60"
        ] += 1
        if len(samples[insight.duration_source]) < 8:
            samples[insight.duration_source].append(
                f"{insight.name}（{minutes} 分钟）"
            )

    total = sum(sources.values())
    print(f"菜品总数 {total}\n")
    print("=== 时长来源 ===")
    for key, label in (
        ("table", "数据库列（最可信）"),
        ("text", "从做法文本里抽的"),
        ("estimated", "★ 抽不到，默认 30 分钟（估的）"),
    ):
        count = sources.get(key, 0)
        print(f"  {label:<28} {count:>6}  ({count / total:.1%})")
    print()
    print("=== 时长分布（看是不是大量堆在 30）===")
    for key in ("≤10", "11-20", "21-30", "31-60", ">60"):
        count = buckets.get(key, 0)
        print(f"  {key:<8} {count:>6}  ({count / total:.1%})")
    print()
    print("=== 抽样 ===")
    for key in ("table", "text", "estimated"):
        print(f"  [{key}] {' / '.join(samples.get(key, [])) or '（无）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
