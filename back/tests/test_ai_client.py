"""大模型客户端的可换性测试。

【为什么值得单独测】
`app/ai/client.py` 里**永不抛异常** —— AI 是锦上添花，失败只是悄悄退回
确定性算法。好处是首页永远不会因为 AI 挂了而 500；坏处是**配错了也看不出来**。

所以「换服务商时请求体里到底发了什么」必须由测试盯着，而不是靠部署上去看：
· 请求 URL 怎么拼（AI_BASE_URL 要不要带 /v1）
· 认证头长什么样
· `response_format` 这个**不是所有兼容服务都实现**的字段，开关关了之后还在不在
"""

from __future__ import annotations

import pytest

from app.ai import client as ai_client
from app.core.config import settings


@pytest.fixture(autouse=True)
def _restore_ai_settings():
    """这几个用例会临时改 settings，跑完必须还原，免得污染别的测试。"""
    saved = (
        settings.ai_json_mode,
        settings.ai_model,
        settings.ai_max_tokens,
        settings.ai_temperature,
        settings.ai_base_url,
    )
    try:
        yield
    finally:
        (
            settings.ai_json_mode,
            settings.ai_model,
            settings.ai_max_tokens,
            settings.ai_temperature,
            settings.ai_base_url,
        ) = saved


def test_payload_uses_configured_model_and_limits():
    settings.ai_model = "qwen-plus"
    settings.ai_max_tokens = 999
    settings.ai_temperature = 0.25

    payload = ai_client.build_payload([{"role": "user", "content": "hi"}])

    assert payload["model"] == "qwen-plus"
    assert payload["max_tokens"] == 999
    assert payload["temperature"] == 0.25
    assert payload["stream"] is False
    assert payload["messages"] == [{"role": "user", "content": "hi"}]


def test_payload_omits_response_format_when_json_mode_is_off():
    """★ 换服务商唯一容易翻车的地方。

    `response_format={"type": "json_object"}` 是 OpenAI 的扩展，不是所有
    「兼容 OpenAI」的服务都实现了（本地 vLLM / Ollama 常见不支持）。
    对方不认时通常直接 400，而客户端永不抛异常 —— 表现为「AI 悄悄降级」。
    关掉开关后，请求体里就**不能**再出现这个字段。
    """
    settings.ai_json_mode = False
    payload = ai_client.build_payload([{"role": "user", "content": "hi"}])
    assert "response_format" not in payload

    settings.ai_json_mode = True
    payload = ai_client.build_payload([{"role": "user", "content": "hi"}])
    assert payload["response_format"] == {"type": "json_object"}


def test_explicit_temperature_wins_over_config():
    settings.ai_temperature = 0.6
    payload = ai_client.build_payload(
        [{"role": "user", "content": "hi"}], temperature=0.0
    )
    assert payload["temperature"] == 0.0


def test_request_url_appends_chat_completions_to_the_base():
    """URL 是「AI_BASE_URL + /chat/completions」。

    所以 AI_BASE_URL 必须填到版本前缀为止 —— 多数兼容服务需要 /v1，
    不带就会 404。这里把这条约定钉住，免得以后有人「顺手」在代码里补 /v1，
    那会让已经填了 /v1 的配置变成 /v1/v1/chat/completions。
    """
    for base, expected in (
        ("https://api.deepseek.com", "https://api.deepseek.com/chat/completions"),
        (
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        ),
        # 结尾多一个斜杠也不能拼出双斜杠
        ("https://api.moonshot.cn/v1/", "https://api.moonshot.cn/v1/chat/completions"),
    ):
        assert base.rstrip("/") + "/chat/completions" == expected


def test_unconfigured_returns_skipped_instead_of_raising(monkeypatch):
    """没配 key 时返回「跳过」，而不是抛异常 —— 这条是「首页绝不 500」的保证。"""
    monkeypatch.setattr(settings, "ai_api_key", "", raising=False)
    result = ai_client.complete_json([{"role": "user", "content": "hi"}])
    assert result.ok is False
    assert result.called is False
    assert "未配置" in (result.error or "")
