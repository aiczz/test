"""大模型客户端（DeepSeek / 任何兼容 OpenAI Chat Completions 协议的服务）。

【为什么直接用 httpx，不引 openai SDK】
`httpx` 本来就在 requirements 里（测试用），而这套协议只有一个 POST，
自己发请求既能少装一个包，也让部署那台 2 核 2G 的服务器少一份依赖。
换服务商时只改 `.env` 里的 AI_BASE_URL / AI_MODEL，代码一行不用动。

【最重要的约定：这里永不抛异常】
AI 是「锦上添花」，不是主链路。网络抖动、限流、余额不足、返回的不是 JSON
——任何一种都不该让首页或 AI 助手 500。
所以所有函数都返回 `AiResult`，失败时 `ok=False` + `error` 里写明原因，
由调用方决定退回哪套确定性结果。
"""

from __future__ import annotations

import json
import logging
import re
import time
import copy
import hashlib
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from threading import RLock
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 从模型回复里抠出 JSON。模型经常会在 JSON 外面套一层 ```json 围栏，
# 或者在前面加一句「好的，这是结果：」——这两种都很常见，必须容错。
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass(slots=True)
class AiResult:
    """一次大模型调用的结果。失败也是一种「正常结果」，不是异常。"""

    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    elapsed_ms: int = 0
    model: str = ""
    error: str | None = None
    # 是否真的发起了网络请求（缓存命中时为 False）
    called: bool = True
    cached: bool = False

    @staticmethod
    def skipped(reason: str) -> AiResult:
        return AiResult(ok=False, error=reason, called=False)


_request = ContextVar('ai_request', default=(True, None))
_cache: OrderedDict[str, tuple[float, AiResult]] = OrderedDict()
_cache_lock = RLock()
_failures: OrderedDict[str, tuple[float, str]] = OrderedDict()


@contextmanager
def request_options(*, enabled: bool = True, budget: float | None = None):
    deadline = time.monotonic() + budget if budget is not None else None
    token = _request.set((enabled, deadline))
    try:
        yield
    finally:
        _request.reset(token)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def clear_failure_cooldowns() -> None:
    with _cache_lock:
        _failures.clear()


def is_configured() -> bool:
    return settings.ai_configured and _request.get()[0]


def failure_message(result: AiResult) -> str:
    """User-facing connection status without exposing raw provider errors."""
    error = result.error or ""
    if '冷却中' in error:
        reason = failure_message(AiResult.skipped(error.split('；', 1)[0]))
        return reason + '已暂缓重复连接，请稍后再试。'
    if "HTTP 503" in error or "HTTP 502" in error:
        return "模型服务暂时繁忙，请稍后重试。"
    if "HTTP 401" in error or "HTTP 403" in error:
        return "模型服务认证失败，请检查后端的模型密钥和权限。"
    if "HTTP 402" in error:
        return "模型服务额度不足，请检查服务账户余额。"
    if "HTTP 429" in error:
        return "模型请求过于频繁或额度受限，请稍后重试。"
    if "超时" in error or "预算" in error:
        return "模型响应超时，请稍后重试。"
    if "未配置" in error:
        return "后端尚未配置模型服务，请检查模型配置。"
    if "JSON" in error:
        return "模型返回格式异常，请重试。"
    return "暂时无法连接模型服务，请稍后重试。"


def complete_json(messages, *, max_tokens=None, temperature=None, timeout=None) -> AiResult:
    if not is_configured():
        return AiResult.skipped('模型未配置或本次请求使用算法预览')
    deadline = _request.get()[1]
    remaining = deadline - time.monotonic() if deadline is not None else None
    if remaining is not None and remaining <= 0:
        return AiResult.skipped('交互时间预算已用完')
    payload = build_payload(messages, max_tokens=max_tokens, temperature=temperature)
    key = hashlib.sha256(json.dumps([
        settings.ai_base_url, settings.ai_api_key, payload,
    ], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    provider_key = hashlib.sha256(json.dumps([
        settings.ai_base_url, settings.ai_api_key, settings.ai_model,
    ]).encode()).hexdigest()
    with _cache_lock:
        entry = _cache.get(key)
        if settings.ai_response_cache_seconds > 0 and entry and entry[0] > time.monotonic():
            _cache.move_to_end(key)
            result = copy.deepcopy(entry[1])
            result.called, result.cached, result.elapsed_ms = False, True, 0
            return result
        failure = _failures.get(provider_key)
        if settings.ai_failure_cooldown_seconds > 0 and failure and failure[0] > time.monotonic():
            return AiResult.skipped(failure[1] + '；模型服务冷却中，稍后自动重试')
    effective_timeout = timeout or settings.ai_timeout_seconds
    if remaining is not None:
        effective_timeout = min(effective_timeout, max(.1, remaining))
    result = _network_complete_json(messages, max_tokens=max_tokens, temperature=temperature, timeout=effective_timeout)
    with _cache_lock:
        if result.ok:
            _failures.pop(provider_key, None)
        elif result.called and settings.ai_failure_cooldown_seconds > 0 and any(
            marker in (result.error or '') for marker in (
                '超时', 'HTTP 429', 'HTTP 500', 'HTTP 502', 'HTTP 503', 'HTTP 504',
                'HTTP 401', 'HTTP 402', 'HTTP 403', 'ConnectError', 'ProxyError',
            )
        ):
            _failures[provider_key] = (time.monotonic() + settings.ai_failure_cooldown_seconds, result.error or '')
            _failures.move_to_end(provider_key)
            while len(_failures) > 128:
                _failures.popitem(last=False)
    if result.ok and settings.ai_response_cache_seconds > 0:
        with _cache_lock:
            _cache[key] = (time.monotonic() + settings.ai_response_cache_seconds, copy.deepcopy(result))
            while len(_cache) > 128:
                _cache.popitem(last=False)
    return result


def _extract_json(text: str) -> dict[str, Any] | None:
    """把模型回复解析成 dict。解析不出来返回 None。"""
    if not text:
        return None

    candidates: list[str] = []
    fenced = _FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)

    # 最后一招：截取第一个 { 到最后一个 } 之间的内容
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first : last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def build_payload(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """拼一次 Chat Completions 的请求体。

    单独抽出来是为了能测 —— 「换服务商时会不会带上对方不认的字段」
    是这个模块唯一容易翻车的地方，值得有断言盯着。
    """
    payload: dict[str, Any] = {
        "model": settings.ai_model,
        "messages": messages,
        "max_tokens": max_tokens or settings.ai_max_tokens,
        "temperature": (
            settings.ai_temperature if temperature is None else temperature
        ),
        "stream": False,
    }
    # `response_format` 是 OpenAI 的扩展，不是所有「兼容 OpenAI」的服务都实现。
    # 对方不认时会直接 400，而这里**永不抛异常** → 表现为 AI 悄悄降级，
    # 界面照常但少了 AI 味，很难查。所以留一个开关，遇到不支持的服务商
    # 只改 .env（AI_JSON_MODE=false）即可，不用动代码。
    #
    # 关掉也没关系：提示词里本来就要求「请输出 JSON」，而 _extract_json
    # 能容错 ```json 围栏和前后多余的客套话。
    if settings.ai_json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def _network_complete_json(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    timeout: int | None = None,
) -> AiResult:
    """要一次 JSON 回复。

    任何失败（未配置 / 超时 / 非 200 / 不是 JSON）都返回 ok=False，
    并把原因写进 error —— 调用方据此降级。
    """
    if not settings.ai_configured:
        return AiResult.skipped("未配置 AI_API_KEY")

    # 注意拼接方式：AI_BASE_URL 要填到「版本前缀」为止（多数服务需要 /v1）
    url = settings.ai_base_url.rstrip("/") + "/chat/completions"
    payload = build_payload(
        messages, max_tokens=max_tokens, temperature=temperature
    )

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout or settings.ai_timeout_seconds) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code != 200:
            # 不把响应体整段打出来 —— 里面可能带账号信息
            body = response.text[:200].replace("\n", " ")
            logger.warning("AI 调用失败 %s: %s", response.status_code, body)
            return AiResult(
                ok=False,
                elapsed_ms=elapsed_ms,
                model=settings.ai_model,
                error=f"HTTP {response.status_code}",
            )

        data = response.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = _extract_json(text)
        if parsed is None:
            logger.warning("AI 回复不是合法 JSON，前 200 字：%s", text[:200])
            return AiResult(
                ok=False,
                text=text,
                elapsed_ms=elapsed_ms,
                model=settings.ai_model,
                error="回复不是合法 JSON",
            )

        return AiResult(
            ok=True,
            data=parsed,
            text=text,
            elapsed_ms=elapsed_ms,
            model=data.get("model") or settings.ai_model,
        )

    except httpx.TimeoutException:
        return AiResult(
            ok=False,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            model=settings.ai_model,
            error="超时",
        )
    except Exception as exc:  # noqa: BLE001 —— 兜住一切，AI 绝不能让主链路挂掉
        logger.warning("AI 调用异常：%s", exc)
        return AiResult(
            ok=False,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            model=settings.ai_model,
            error=f"{type(exc).__name__}: {exc}",
        )
