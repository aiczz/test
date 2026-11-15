"""菜定向量索引 —— 从 Project2 的 semantic.py 改造而来。

【设计原则】
  1. 零外部向量数据库依赖 —— 就一个 .npz 文件（Project2 17 万条 float16 才 325MB，
     食时 1 万条才 ~20MB），numpy 一次矩阵乘法搞定检索，几十毫秒。
  2. 候选集内检索 —— 不让 RAG 跑全库，先让确定性算法拉一批时令候选（200 条），
     RAG 只在这 200 条里做语义精排。这样既快又安全（硬约束已经在前面兜住了）。
  3. 向量可热加载 —— npz 变了自动重新加载，不需要重启服务。

【存储格式】（和 Project2 保持一致）
  embeddings_dishes.npz 包含：
    ids  — unicode str 数组，形状 (n,)
    vecs — float16 数组，形状 (n, dim)，已 L2 归一化
"""

from __future__ import annotations

import os
import time
from threading import RLock

import numpy as np

from app.core.config import settings

logger = __import__("logging").getLogger(__name__)


class DishVectorIndex:
    """菜定向量索引。单例 + 懒加载 + 变更自动重载。"""

    def __init__(self, path: str | None = None):
        self._path = path or settings.vector_index_path
        self._full_path = os.path.abspath(self._path)
        self._lock = RLock()
        self._ids: np.ndarray | None = None        # str 数组
        self._vecs: np.ndarray | None = None       # float32 数组，L2 归一化
        self._pos_of: dict[str, int] = {}          # id → 行号
        self._mtime: float = 0.0
        self._loaded = False

    # ------------------------------------------------------------------
    # 加载 / 检查
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """索引文件存在且可加载。"""
        self._ensure_loaded()
        return self._loaded and self._vecs is not None

    def _ensure_loaded(self) -> None:
        """懒加载；如果文件 mtime 变了，自动重载。"""
        with self._lock:
            if not os.path.isfile(self._full_path):
                self._loaded = False
                return
            mtime = os.path.getmtime(self._full_path)
            if self._loaded and mtime == self._mtime:
                return  # 已加载且文件没变
            try:
                data = np.load(self._full_path, allow_pickle=False)
                self._ids = data["ids"].astype(str)
                self._vecs = data["vecs"].astype(np.float32)  # 加载时转 float32，BLAS 快
                # L2 归一化（构建时可能已经做了，这里再保险一下）
                norms = np.linalg.norm(self._vecs, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._vecs = self._vecs / norms
                # id → 行号映射（O(1) 查位置）
                self._pos_of = {str(rid): i for i, rid in enumerate(self._ids)}
                self._mtime = mtime
                self._loaded = True
                logger.info(
                    "菜定向量索引加载完成：%d 条，%d 维（文件 %s）",
                    len(self._ids), self._vecs.shape[1], self._full_path,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("菜定向量索引加载失败：%s", exc)
                self._loaded = False
                self._ids = None
                self._vecs = None

    def coverage(self) -> int:
        """真实覆盖条数（排除零向量）。构建失败的条目 embedding 是零向量，
        检索时点积恒为 0，自然沉底。"""
        self._ensure_loaded()
        if self._vecs is None:
            return 0
        return int(np.sum(np.linalg.norm(self._vecs, axis=1) > 0))

    # ------------------------------------------------------------------
    # 检索核心
    # ------------------------------------------------------------------

    def sims_for(
        self, query_vec: list[float] | np.ndarray, candidate_ids: list[int | str]
    ) -> np.ndarray | None:
        """在候选集内计算每条候选和 query 的余弦相似度。

        返回 numpy 数组，长度 == len(candidate_ids)，顺序一致。
        库里没有的 id 给 0。索引不可用时返回 None。

        【为什么先全库矩阵乘再收集】
        Project2 的实测：17 万条 × 1024 维的一次全库 matvec 比 5 万次小点积
        快一个量级（BLAS 优化）。食时只有 1 万条，更快。
        """
        self._ensure_loaded()
        if not self.available or self._vecs is None:
            return None

        q = np.asarray(query_vec, dtype=np.float32).ravel()
        if q.ndim != 1 or q.shape[0] != self._vecs.shape[1]:
            logger.warning(
                "Query 维度不匹配：期望 %d，得到 %d",
                self._vecs.shape[1], q.shape[0] if q.ndim == 1 else q.ndim,
            )
            return None
        # L2 归一化 query
        q_norm = np.linalg.norm(q)
        if q_norm > 0:
            q = q / q_norm

        # 全库余弦：vecs 已归一化，所以点积就是余弦相似度
        all_sims = self._vecs @ q   # (n_candidates,)
        out = np.zeros(len(candidate_ids), dtype=np.float32)
        for i, rid in enumerate(candidate_ids):
            pos = self._pos_of.get(str(rid), -1)
            if pos >= 0:
                out[i] = float(all_sims[pos])
        return out

    def top_k(
        self,
        query_vec: list[float] | np.ndarray,
        k: int,
        allowed_ids: set[int] | None = None,
    ) -> list[int]:
        """全库语义召回 top-K 的菜品 id —— 用于 RAG 第二路召回。

        allowed_ids 非空时只在集合内检索（推荐链路传「有配图的菜」，
        否则召回的都是没图的菜，后面会被 recipe_images_only 全部过滤掉）。

        返回的 id 是 int（对应 dishes.id），按相似度从高到低。不可用时返回空列表。
        """
        self._ensure_loaded()
        if not self.available or self._vecs is None or k <= 0:
            return []

        q = np.asarray(query_vec, dtype=np.float32).ravel()
        if q.shape[0] != self._vecs.shape[1]:
            return []
        q_norm = np.linalg.norm(q)
        if q_norm > 0:
            q = q / q_norm

        if allowed_ids is None:
            positions = np.arange(len(self._ids))
        else:
            # 只在允许集合内检索 —— 子矩阵一次 matvec，几百行，可忽略
            picked = [self._pos_of[str(i)] for i in allowed_ids if str(i) in self._pos_of]
            if not picked:
                return []
            positions = np.asarray(picked, dtype=np.int64)

        sims = self._vecs[positions] @ q
        k = min(k, len(sims))
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        out: list[int] = []
        for idx in top:
            if sims[idx] <= 0:  # 零向量占位的条目跳过
                continue
            try:
                out.append(int(self._ids[positions[idx]]))
            except (TypeError, ValueError):
                continue
        return out


# ----------------------------------------------------------------------
# 单例 —— 整个进程共享一份
# ----------------------------------------------------------------------

_index: DishVectorIndex | None = None
_index_lock = RLock()


def get_vector_index() -> DishVectorIndex:
    global _index
    with _index_lock:
        if _index is None:
            _index = DishVectorIndex()
        return _index
