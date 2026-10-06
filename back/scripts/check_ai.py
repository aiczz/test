"""换大模型服务商之后，用它验证「配对了没有」。

为什么要有这个脚本：
    `app/ai/client.py` 里**永不抛异常** —— AI 是锦上添花，任何失败都只是
    悄悄退回确定性算法。好处是首页永远不会因为 AI 挂了而 500；
    坏处是**配置写错了也看不出来**：界面照常能开、菜照样有，
    只是没有 AI 润色那一段。换服务商时最容易踩的就是这个。

    所以换完 key / 地址 / 模型名，跑一下这个脚本，它会把「到底发生了什么」
    直接打出来，并给出该改哪一项。

用法：
    cd back
    python scripts/check_ai.py                     # 用 .env 里的配置
    python scripts/check_ai.py --model qwen-plus   # 临时试别的模型
    python scripts/check_ai.py --base https://dashscope.aliyuncs.com/compatible-mode/v1

它做三件事：
    1. 打印当前生效的配置（key 打码）
    2. 真的发一次请求（要花一点点 token）
    3. 按结果给出结论和下一步
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402

# 用一句能触发 JSON 输出的最小请求
PROBE_MESSAGES = [
    {"role": "system", "content": "只输出 JSON，不要任何多余文字。"},
    {
        "role": "user",
        "content": '请输出 JSON：{"ok": true, "note": "连接正常"}',
    },
]


def _mask(key: str) -> str:
    if not key:
        return "（空）"
    if len(key) <= 12:
        return key[:3] + "***"
    return f"{key[:6]}…{key[-4:]}（长度 {len(key)}）"


def main() -> int:
    parser = argparse.ArgumentParser(description="验证大模型配置是否可用")
    parser.add_argument("--base", help="临时覆盖 AI_BASE_URL")
    parser.add_argument("--model", help="临时覆盖 AI_MODEL")
    parser.add_argument("--key", help="临时覆盖 AI_API_KEY（一般不用）")
    parser.add_argument("--json-mode", choices=["on", "off"],
                        help="临时覆盖 AI_JSON_MODE")
    args = parser.parse_args()

    if args.base:
        settings.ai_base_url = args.base
    if args.model:
        settings.ai_model = args.model
    if args.key:
        settings.ai_api_key = args.key
    if args.json_mode:
        settings.ai_json_mode = args.json_mode == "on"

    print("=" * 62)
    print(" 大模型配置自检")
    print("=" * 62)
    print(f"  AI_ENABLED   = {settings.ai_enabled}")
    print(f"  AI_BASE_URL  = {settings.ai_base_url}")
    print(f"  AI_MODEL     = {settings.ai_model}")
    print(f"  AI_API_KEY   = {_mask(settings.ai_api_key)}")
    print(f"  AI_JSON_MODE = {settings.ai_json_mode}")
    print(f"  超时         = {settings.ai_timeout_seconds}s")
    print(f"  完整 URL     = {settings.ai_base_url.rstrip('/')}/chat/completions")
    print()

    if not settings.ai_configured:
        print("  [x] 没配好 —— AI_API_KEY 为空，或 AI_ENABLED=false。")
        print("      现在跑起来不会报错，但首页和 AI 助手会全部走确定性算法")
        print("      （界面照常，只是没有 AI 润色和候选内的智能挑选）。")
        print()
        print("      改 back/.env 里的 AI_ENABLED / AI_API_KEY 再跑一次。")
        return 1

    # 延迟 import：上面可能刚改过 settings
    from app.ai import client as ai_client

    print("  正在真的发一次请求（会消耗一点点 token）…")
    result = ai_client.complete_json(PROBE_MESSAGES, max_tokens=64, timeout=30)

    print()
    if result.ok:
        print(f"  [ok] 连接正常，耗时 {result.elapsed_ms} ms，实际模型 {result.model}")
        print(f"       返回：{json.dumps(result.data, ensure_ascii=False)[:120]}")
        print()
        print("  可以用了。换服务商的话，把 back/.env 里这三行改成对应的值就行：")
        print("      AI_BASE_URL / AI_API_KEY / AI_MODEL")
        print("  （服务器上改完要 sudo systemctl restart shishi-backend）")
        return 0

    print(f"  [x] 调用失败：{result.error}")
    print()
    print("  按这个顺序排查：")
    print(f"    1. key 对不对 —— 当前用的是 {_mask(settings.ai_api_key)}")
    print(f"    2. 地址要不要带 /v1 —— 现在是")
    print(f"       {settings.ai_base_url.rstrip('/')}/chat/completions")
    print("       多数兼容 OpenAI 的服务是 `https://<域名>/v1`；")
    print("       填错通常报 404。")
    print(f"    3. 模型名存不存在 —— 现在是 `{settings.ai_model}`")
    print("       写错通常报 400 或 404。")
    if "HTTP 400" in (result.error or "") and settings.ai_json_mode:
        print("    4. ★ 很可能是对方不支持 response_format=json_object：")
        print("       在 back/.env 里加一行 AI_JSON_MODE=false 再试。")
        print("       （这是唯一一处不是所有「兼容 OpenAI」的服务都实现的东西）")
    if "HTTP 401" in (result.error or "") or "HTTP 403" in (result.error or ""):
        print("    4. 401/403 = key 无效或没权限；也可能是余额不足。")
    if "超时" in (result.error or ""):
        print("    4. 超时 —— 国内访问境外服务常见。可以调大 AI_TIMEOUT_SECONDS，")
        print("       或者换一个国内的服务商。")
    print()
    print("  想临时试别的配置（不改 .env）：")
    print("      python scripts/check_ai.py --base https://xxx/v1 --model xxx")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
