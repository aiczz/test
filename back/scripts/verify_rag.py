"""验证 RAG 检索效果 —— 打印真实菜名，而不是光秃秃的 id。

用法：
    cd back
    python -m scripts.verify_rag              # 全库检索 Top-K
    python -m scripts.verify_rag --ab         # A/B 对比：有 RAG vs 没 RAG 的推荐结果
"""

from __future__ import annotations

import argparse
import os
import sys

_back_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _back_dir not in sys.path:
    sys.path.insert(0, _back_dir)

from sqlalchemy import text as sqlt
from sqlmodel import Session

from app.core.database import engine
from app.services.retrieval import DishVectorIndex, embed_text

QUERIES = [
    "清淡不上火的",
    "补气血",
    "给健身的人吃，要高蛋白",
    "冬天暖胃的汤",
    "用西红柿做的菜",
    "嗓子疼想吃点润喉的",
    "给孩子吃的，好消化",
    "低盐低钠",
]


def _dish_names(ids: list[str]) -> dict[str, tuple[str, str]]:
    """id -> (菜名, 标签)"""
    if not ids:
        return {}
    names = [f":i{i}" for i in range(len(ids))]
    params = {f"i{i}": int(v) for i, v in enumerate(ids)}
    with Session(engine) as s:
        rows = s.execute(
            sqlt(
                f"SELECT id, dish_name, tags_json FROM dishes WHERE id IN ({','.join(names)})"
            ),
            params,
        ).mappings()
        return {
            str(r["id"]): (str(r["dish_name"] or ""), str(r["tags_json"] or "")[:60])
            for r in rows
        }


def _run_topk(idx: DishVectorIndex) -> None:
    print(f"✅ 索引：{len(idx._ids)} 条，有效 {idx.coverage()} 条\n")
    for q in QUERIES:
        qv = embed_text(q)
        print(f"\n{'='*70}\nQuery：{q}\n{'-'*70}")
        if qv is None:
            print("  ❌ embedding 失败")
            continue
        sims = idx._vecs @ qv
        top = sims.argsort()[::-1][:8]
        id_list = [str(idx._ids[p]) for p in top]
        info = _dish_names(id_list)
        for rank, pos in enumerate(top):
            rid = id_list[rank]
            name, tags = info.get(rid, ("(未找到)", ""))
            print(f"  #{rank+1}  {float(sims[pos]):.3f}  {name}   tags={tags}")


def _run_ab() -> None:
    """对比同一组约束下，带 free_text 与不带 free_text 的推荐差异。"""
    from datetime import datetime

    from app.services.scoring_service import HardConstraints, score_dishes
    from app.services.weather_service import WeatherContext

    case_text = "最近有点上火，想吃点清爽降火的"
    today = datetime.now().strftime("%Y-%m-%d")
    weather = WeatherContext(
        city="武汉", date=today, kind="mild", description="晴 12~22℃",
        temperature_c=17.0, source="unknown",
    )

    with Session(engine) as s:
        print(f"\n{'='*70}\nA/B 对比：free_text = 「{case_text}」\n{'-'*70}")
        common = dict(
            session=s, month=datetime.now().month, weather=weather,
            constraints=HardConstraints(), region="武汉", date_key=today, limit=6,
        )
        base = score_dishes(**common)
        rag = score_dishes(**common, free_text=case_text)

        print("\n[无 RAG]")
        for i, it in enumerate(base):
            print(f"  {i+1}. {it.name}  score={it.score:.2f} "
                  f"semantic={it.factors.get('semantic', 0):.2f}")
        print("\n[有 RAG]")
        for i, it in enumerate(rag):
            print(f"  {i+1}. {it.name}  score={it.score:.2f} "
                  f"semantic={it.factors.get('semantic', 0):.2f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ab", action="store_true", help="跑 A/B 对比而不是全库 Top-K")
    args = parser.parse_args()

    idx = DishVectorIndex()
    if not idx.available:
        print(f"❌ 向量索引不可用（{idx._path}）")
        return

    if args.ab:
        _run_ab()
    else:
        _run_topk(idx)


if __name__ == "__main__":
    main()
