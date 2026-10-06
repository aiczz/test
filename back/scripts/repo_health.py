"""交付前的一次体检：确认仓库里没有「没人用的大文件」和敏感的漏网之鱼。

跑法：python back/scripts/repo_health.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".sh", ".md", ".py", ".yml", ".yaml", ".txt", ".json", ".toml"}
# 只有这些文件是「可能没人用的大块头」，值得逐个查引用
SUSPECTS = ["cleaned_v2.zip", "web-build.tar.gz"]


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def main() -> int:
    files = tracked_files()
    print(f"被 git 跟踪的文件：{len(files)} 个\n")

    # ---- 1. 大文件 + 有没有人引用 ----
    sizes: list[tuple[float, str]] = []
    for name in files:
        p = ROOT / name
        if p.is_file():
            sizes.append((p.stat().st_size / 1024 / 1024, name))
    sizes.sort(reverse=True)

    print("=== 最大的 12 个被跟踪文件 ===")
    for mb, name in sizes[:12]:
        print(f"  {mb:>7.2f} MB  {name}")
    print(f"  合计 {sum(mb for mb, _ in sizes):.1f} MB\n")

    print("=== 大块头是否还有人引用 ===")
    for suspect in SUSPECTS:
        hit = [mb for mb, name in sizes if name.endswith(suspect)]
        if not hit:
            print(f"  {suspect}: 已经不在仓库里了")
            continue
        referenced: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if path.suffix not in TEXT_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if suspect in text:
                referenced.append(str(path.relative_to(ROOT)))
        state = "；".join(referenced) if referenced else "没有任何地方引用"
        print(f"  {suspect}（{hit[0]:.1f} MB）→ {state}")

    # ---- 2. 敏感文件 ----
    print("\n=== 敏感文件检查 ===")
    leaks = [
        name
        for name in files
        if name.endswith(".env") or "shishi.db" in name or "sk-" in name
    ]
    print(f"  {'[x] ' + str(leaks) if leaks else '[ok] 没有 .env / 数据库 / 明文 key 进仓库'}")

    # ---- 3. 工作区是否干净 ----
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    print(f"  {'[ok] 工作区干净' if not status else '[!] 还有未提交改动：' + status}")

    # ---- 4. 和远端的关系 ----
    counts = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    if len(counts) == 2:
        behind, ahead = int(counts[0]), int(counts[1])
        ok = behind == 0
        print(
            f"  {'[ok]' if ok else '[x]'} 相对 origin/main：落后 {behind}，领先 {ahead}"
            + ("" if ok else "  ← 落后的话 push 会被拒，要先 pull")
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
