"""RAG 向量检索模块 —— 给推荐链路加一层语义精排。

搬自 Project2 的架构，但做了三个关键适配：
  1. 数据源换成食时自己的中文清洗库（dishes 10000 条 + 590 核心食材）
  2. embedding 模板加了时令月份、食养功效、做法标签 —— 这些是 Project2 英文数据没有的
  3. 失败降级和 ai/client.py 风格一致：永不抛异常，返回 None 让调用方兜底
"""

from app.services.retrieval.embed_client import embed_text, is_embedding_configured
from app.services.retrieval.vector_index import DishVectorIndex, get_vector_index

__all__ = [
    "embed_text",
    "is_embedding_configured",
    "DishVectorIndex",
    "get_vector_index",
]
