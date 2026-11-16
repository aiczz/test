"""打自托管部署包（交给运维的那一份）。

为什么需要这个脚本：
    直接把整个项目目录压缩发出去，会把 back/.env 一起带走 ——
    里面是真实的 AI / embedding 密钥。本脚本只收录「部署真正需要」的文件，
    并在打包后做一次密钥自检，不通过就删包报错。

用法：
    python deploy/package_release.py

产物：
    _release/shishi-deploy-<时间戳>.tar.gz
    _release/shishi-deploy-<时间戳>.tar.gz.sha256
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "_release"

# 永远不进包：密钥、本地库、缓存、编辑器/工具目录
EXCLUDE_NAMES = {".env", "shishi.db", ".DS_Store", "start.log", "Thumbs.db"}
EXCLUDE_DIR_PARTS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules",
    ".dart_tool", ".trae", ".vscode", ".idea", "_release", ".screenshots",
}
# 这份是给第三方的内容交付包，脚手架部署用不到，省 17 MB
# 前端源码不参与部署（服务器不装 Flutter）；它的 assets/images 和 build/web
# 里的图片是同一批，两份都打进去会白白多出 230 MB。
EXCLUDE_PREFIXES = (
    "sql/菜谱数据库_交付_20260918 (1)/",
    "front/mealmind/",
)
# 上面排除了整个前端目录，但构建产物是部署要用的，单独放行
KEEP_PREFIXES = ("front/mealmind/build/web/",)

# 构建产物不入 git，但离线部署要用，单独补进来
EXTRA_DIRS = ("front/mealmind/build/web",)

# 自检：这些扩展名里出现疑似密钥即判定失败
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".yaml", ".yml", ".json", ".dart", ".conf",
    ".service", ".sh", ".bat", ".css", ".html", ".js", ".env", ".example",
    ".toml", ".ini", ".cfg",
}
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_.-]{16,}|sk-ws-[A-Za-z0-9_.-]{16,}|"
                       r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,})")
# 生成的构建产物没必要逐字扫（十几 MB 的压缩 JS，扫了只会变慢）
SKIP_SCAN_PREFIXES = ("front/mealmind/build/",)
SCAN_MAX_BYTES = 512 * 1024


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def extra_files() -> list[str]:
    found: list[str] = []
    for rel in EXTRA_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                found.append(path.relative_to(ROOT).as_posix())
    return found


def keep(rel: str) -> bool:
    parts = rel.split("/")
    if any(part in EXCLUDE_DIR_PARTS for part in parts):
        return False
    if parts[-1] in EXCLUDE_NAMES:
        return False
    forced = any(rel.startswith(prefix) for prefix in KEEP_PREFIXES)
    if not forced and any(rel.startswith(prefix) for prefix in EXCLUDE_PREFIXES):
        return False
    return (ROOT / rel).is_file()


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    arc_root = f"shishi-deploy-{stamp}"
    out_path = OUT_DIR / f"{arc_root}.tar.gz"

    candidates = sorted(set(tracked_files()) | set(extra_files()))
    selected = [rel for rel in candidates if keep(rel)]
    # back/.env 不在 git 里，但磁盘上有真实密钥；这里显式告诉用户它被跳过了
    skipped_secret = [
        rel.relative_to(ROOT).as_posix()
        for rel in (ROOT / "back" / ".env",)
        if rel.exists()
    ]

    leaked: list[str] = []
    with tarfile.open(out_path, "w:gz", compresslevel=6) as tar:
        for rel in selected:
            src = ROOT / rel
            data = src.read_bytes()
            suffix = src.suffix.lower()
            scannable = (
                (suffix in TEXT_SUFFIXES or src.name.startswith(".env"))
                and len(data) <= SCAN_MAX_BYTES
                and not rel.startswith(SKIP_SCAN_PREFIXES)
            )
            if scannable:
                text = data.decode("utf-8", errors="ignore")
                for match in SECRET_RE.finditer(text):
                    leaked.append(f"{rel}: {match.group(0)[:12]}…")
            info = tar.gettarinfo(str(src), arcname=f"{arc_root}/{rel}")
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            tar.addfile(info, io.BytesIO(data))

    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    (OUT_DIR / f"{arc_root}.tar.gz.sha256").write_text(f"{digest}  {out_path.name}\n", encoding="utf-8")

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"包      : {out_path}")
    print(f"大小    : {size_mb:.1f} MB")
    print(f"文件数  : {len(selected)}")
    print(f"SHA256  : {digest}")
    print(f"已排除  : {', '.join(skipped_secret) or '无'}")
    print(f"补入构建: {', '.join(d for d in EXTRA_DIRS if (ROOT / d).exists()) or '无'}")

    if leaked:
        out_path.unlink(missing_ok=True)
        (OUT_DIR / f"{arc_root}.tar.gz.sha256").unlink(missing_ok=True)
        print("\n[失败] 包内发现疑似密钥，已删除产物：", file=sys.stderr)
        for item in leaked:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("\n密钥自检通过：包内无明文密钥。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
