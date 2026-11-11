"""食养诉求的向量匹配 —— 关键词表漏掉的表达交给 embedding。

【为什么需要它】
`need_service.extract_goal` 靠关键词命中（"嗓子干"、"上火"…），
但用户会说「嗓子疼想喝点润喉的」—— 里面没有一个词在表里，于是被判成无诉求，
最后推出来的是土豆炖排骨。

这里把 12 类诉求编码成向量（离线一次性，见 scripts/build_goal_embeddings.py），
运行时把用户原话编码后找最近邻。关键词能命中就绝不用它 —— 确定性 > 概率性。
"""

from __future__ import annotations

import os
import threading

import numpy as np

from app.core.config import settings

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "data")
_PATH = os.path.join(_DATA_DIR, "embeddings_goals.npz")

# 低于这个余弦视为「没有诉求」，宁可不给也不要乱给 —— 一旦误判，
# 整条推荐会被错误诉求带偏，比不识别更糟。
MIN_SIM = 0.52
# 第一名必须领先第二名这么多，否则说明用户这句话模棱两可（如只说"不舒服"），
# 这种情况下返回 None 让人工/LLM 兜底更安全。
MIN_MARGIN = 0.02


class GoalIndex:
    """12 条诉求的小向量索引（常驻内存，几十 KB）。"""

    def __init__(self, path: str = _PATH) -> None:
        self._path = path
        self._names: list[str] = []
        self._vecs: np.ndarray | None = None
        self._loaded = False
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            if not os.path.exists(self._path):
                return
            try:
                with np.load(self._path, allow_pickle=False) as data:
                    names = [str(n) for n in data["names"]]
                    vecs = np.asarray(data["vecs"], dtype=np.float32)
                norms = np.linalg.norm(vecs, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._names = names
                self._vecs = vecs / norms
            except Exception:  # noqa: BLE001 —— 坏了就当没有，不影响关键词路径
                self._names = []
                self._vecs = None

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._vecs is not None and len(self._names) > 0

    def match(self, query_vec: list[float] | np.ndarray) -> tuple[str, float] | None:
        """返回 (诉求名, 相似度)；不够确定时返回 None。"""
        self._ensure_loaded()
        if not self.available or self._vecs is None:
            return None

        q = np.asarray(query_vec, dtype=np.float32).ravel()
        if q.shape[0] != self._vecs.shape[1]:
            return None
        norm = np.linalg.norm(q)
        if norm <= 0:
            return None
        q = q / norm

        sims = self._vecs @ q
        order = np.argsort(-sims)
        best, second = int(order[0]), int(order[1]) if len(order) > 1 else int(order[0])
        best_sim = float(sims[best])
        if best_sim < MIN_SIM:
            return None
        if best_sim - float(sims[second]) < MIN_MARGIN:
            return None
        return self._names[best], best_sim


_INDEX: GoalIndex | None = None


def get_goal_index() -> GoalIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = GoalIndex()
    return _INDEX
