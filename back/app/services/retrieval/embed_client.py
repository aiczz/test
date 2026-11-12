"""Embedding 客户端 —— 和 ai/client.py 风格一致：永不抛异常。

搬自 Project2 的 build_embeddings.py + semantic.py 的 embed_query，
适配成和 ai/client.py 同样的返回约定（失败返回 None 而不是抛异常）。
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from threading import RLock

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 同一句话在聊天里可能被重复检索（重问、换数量、详情追问），
# 每次重新调用 embedding 服务要 1s 以上，还会挤占模型的交互预算。
# 这里做一个很小的 LRU + TTL 缓存，只缓存查询文本。
_QUERY_CACHE_TTL = 900.0
_QUERY_CACHE_MAX = 256
_query_cache: OrderedDict[str, tuple[float, list[float]]] = OrderedDict()
_query_lock = RLock()


def is_embedding_configured() -> bool:
    """有没有配好 embedding 服务。没配好就全链路跳过 RAG。"""
    return settings.embedding_configured


def embed_text(text: str, *, timeout: int | None = None) -> list[float] | None:
    """把一段文本编成向量。失败返回 None，永不抛异常。

    单条 embedding 正常耗时 < 1s，这里 timeout 给 60s 是给大文本留余量。
    """
    if not text or not text.strip():
        return None
    if not is_embedding_configured():
        return None

    text = text.strip()
    cache_key = f"{settings.embedding_base_url}|{settings.embedding_model}|{text}"
    now = time.monotonic()
    with _query_lock:
        hit = _query_cache.get(cache_key)
        if hit and hit[0] > now:
            _query_cache.move_to_end(cache_key)
            return list(hit[1])

    api_key = settings.embedding_api_key.strip() or settings.ai_api_key.strip()
    url = settings.embedding_base_url.rstrip("/") + "/embeddings"
    payload = {
        "model": settings.embedding_model,
        "input": text,
    }

    effective_timeout = timeout or settings.embedding_timeout_seconds
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=effective_timeout) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code != 200:
            body = response.text[:200].replace("\n", " ")
            logger.warning("Embedding 调用失败 %s: %s", response.status_code, body)
            return None

        data = response.json()
        vec = data.get("data")
        if not vec or not isinstance(vec, list):
            logger.warning("Embedding 返回格式异常，前 200 字：%s", str(data)[:200])
            return None
        # 返回的是 list[dict]，第一个 dict 的 embedding 字段就是向量
        first = vec[0]
        if isinstance(first, dict):
            emb = first.get("embedding")
        else:
            emb = first  # 有些服务直接返回向量列表
        if not emb or not isinstance(emb, list):
            return None
        # 校验维度 —— 防止换了模型没改配置
        if len(emb) != settings.embedding_dim:
            logger.warning(
                "Embedding 维度不匹配：期望 %d，得到 %d",
                settings.embedding_dim, len(emb),
            )
            return None
        vec = [float(v) for v in emb]
        with _query_lock:
            _query_cache[cache_key] = (time.monotonic() + _QUERY_CACHE_TTL, vec)
            _query_cache.move_to_end(cache_key)
            while len(_query_cache) > _QUERY_CACHE_MAX:
                _query_cache.popitem(last=False)
        return list(vec)

    except httpx.TimeoutException:
        logger.warning("Embedding 超时")
        return None
    except Exception as exc:  # noqa: BLE001 —— 兜住一切，绝不让主链路挂掉
        logger.warning("Embedding 调用异常：%s", exc)
        return None


def embed_batch(texts: list[str], *, timeout: int | None = None) -> list[list[float] | None]:
    """批量 embedding。逐条调用（避免服务端对 batch 大小有限制），失败的条目返回 None。

    Project2 的经验：超过 25 条可能报 400，所以这里简单逐条调，
    速度足够（单机预构建阶段每秒能编几条到几十条，10000 条半小时内搞定）。
    """
    return [embed_text(t, timeout=timeout) for t in texts]
