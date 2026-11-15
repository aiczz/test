"""给 12 类食养诉求建向量索引 —— 让「嗓子疼想润喉」这种说法也能命中「润燥润肺」。

诉求只有 12 条，跑一次十几秒。输出 data/embeddings_goals.npz。

用法：cd back && python -m scripts.build_goal_embeddings
"""

from __future__ import annotations

import os
import sys

import numpy as np

_back_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _back_dir not in sys.path:
    sys.path.insert(0, _back_dir)

from app.core.config import settings
from app.services.need_service import all_goals
from app.services.retrieval.embed_client import embed_text, is_embedding_configured

OUT_FILE = os.path.join(_back_dir, "data", "embeddings_goals.npz")


def goal_text(goal) -> str:
    """把一类诉求写成一段说明，给 embedding 编码。

    刻意把「用户可能怎么说」放进去 —— 这是关键词表漏掉的表达，
    也是我们要让向量去覆盖的部分。
    """
    return (
        f"饮食诉求：{goal.name}\n"
        f"用户可能这样说：{'、'.join(goal.phrases)}\n"
        f"相关功效：{'、'.join(goal.effect_keywords)}"
    )


def main() -> None:
    if not is_embedding_configured():
        print("❌ Embedding 未配置")
        sys.exit(1)

    goals = all_goals()
    names: list[str] = []
    vecs: list[np.ndarray] = []
    for goal in goals:
        vec = embed_text(goal_text(goal))
        if vec is None:
            print(f"  ✗ {goal.name} embedding 失败")
            continue
        names.append(goal.name)
        vecs.append(np.array(vec, dtype=np.float32))
        print(f"  ✓ {goal.name}")

    if not names:
        print("没有成功任何一条，退出")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    np.savez_compressed(
        OUT_FILE, names=np.array(names, dtype="<U32"), vecs=np.stack(vecs).astype(np.float16)
    )
    print(f"✓ 保存 {len(names)} 条诉求向量到 {OUT_FILE}（{os.path.getsize(OUT_FILE)/1024:.1f} KB）")


if __name__ == "__main__":
    main()
