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

    @staticmethod
    def skipped(reason: str) -> AiResult:
        return AiResult(ok=False, error=reason, called=False)


def is_configured() -> bool:
    return settings.ai_configured


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


def complete_json(
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

    url = settings.ai_base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": settings.ai_model,
        "messages": messages,
        "max_tokens": max_tokens or settings.ai_max_tokens,
        "temperature": (
            settings.ai_temperature if temperature is None else temperature
        ),
        "stream": False,
        # DeepSeek 支持 JSON 输出模式。注意：用它时提示词里必须出现 "json" 字样，
        # 否则服务端会直接报错 —— prompts.py 里的提示词都带了。
        "response_format": {"type": "json_object"},
    }

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
