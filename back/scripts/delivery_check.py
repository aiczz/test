"""交付前的最终检查：仓库状态 + 文档齐全 + 服务可达。

跑法：python back/scripts/delivery_check.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]

REQUIRED_DOCS = [
    "VERSION",
    "CHANGELOG.md",
    "README.md",
    "LICENSE",
    "docs/交付说明.md",
    "docs/算法与AI设计.md",
    "deploy/README.md",
    "deploy/deploy.sh",
    "deploy/nginx-shishi.conf",
    "deploy/shishi-backend.service",
    ".github/workflows/build-web.yml",
    ".github/workflows/backend-tests.yml",
]


def main() -> int:
    print("=" * 56)
    print(" 交付前最终检查")
    print("=" * 56)

    print("\n--- 1. 交付文档是否齐全 ---")
    missing = []
    for name in REQUIRED_DOCS:
        ok = (ROOT / name).exists()
        print(f"  {'[ok]' if ok else '[x] '} {name}")
        if not ok:
            missing.append(name)
    print(f"  VERSION = {(ROOT / 'VERSION').read_text(encoding='utf-8').strip()}")

    print("\n--- 2. git 状态 ---")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    print(f"  {'[ok] 工作区干净' if not status else '[!] 还有未提交改动：' + status}")
    counts = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    behind, ahead = int(counts[0]), int(counts[1])
    print(f"  {'[ok]' if behind == 0 else '[x]'} 相对 origin/main：落后 {behind}、领先 {ahead}")

    print("\n--- 3. 本地服务（可选） ---")
    for label, url in (
        ("后端 8000", "http://127.0.0.1:8000/api/health"),
        ("同源 8091", "http://127.0.0.1:8091/api/recipes/tags"),
    ):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
            detail = data.get("status") if isinstance(data, dict) else f"{len(data)} 组"
            print(f"  [ok] {label}：{detail}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [--] {label} 没在跑（{type(exc).__name__}）—— 不影响交付")

    print("\n" + "=" * 56)
    if missing:
        print(f" 缺 {len(missing)} 个文件，先补上再 push")
        return 1
    print(" 结论：可以 push。下一步就是 `git push origin main`，")
    print("       然后等 GitHub Actions 跑完再叫运维部署。")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
