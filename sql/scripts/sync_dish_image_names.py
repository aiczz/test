"""把前端「哪道菜有配图」的清单同步到后端。

【为什么需要】
配图是**按菜名**映射的，那张表在前端（`lib/data/dish_images.dart`），
后端只给菜名、不认识图片。但推荐排序需要知道「这道菜有没有图」——
精选目录里 700 道有 481 道配了图，同等条件下优先推有图的，
首页和 AI 助手就不会一片「暂无配图」。

【为什么不干脆让后端也维护一份】
那就成了两个真相来源，改一边忘一边，两边慢慢对不上。
所以这里**只做单向生成**：Dart 那张表是唯一的真相，
这个脚本把它读成 Python 常量，`tests/test_dish_images_sync.py` 会盯着两边一致。

用法：
    python sql/scripts/sync_dish_image_names.py            # 生成
    python sql/scripts/sync_dish_image_names.py --check     # 只校验，不写
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DART = ROOT / "front" / "mealmind" / "lib" / "data" / "dish_images.dart"
TARGET = ROOT / "back" / "app" / "data" / "dish_images.py"

PATTERN = re.compile(r"'([^']+)'\s*:\s*'assets/")

HEADER = '''"""哪道菜有配图 —— **由脚本生成，不要手改**。

来源：`front/mealmind/lib/data/dish_images.dart`（那张才是真相）
生成：`python sql/scripts/sync_dish_image_names.py`
校验：`tests/test_dish_images_sync.py` 会盯着两边一致

后端拿它做一件事：推荐排序时「同等条件下优先有图的菜」——
精选目录里 {total} 道有 {with_image} 道配了图，
不优先的话首页常常推出一屏「暂无配图」，观感很差。
"""

from __future__ import annotations

# 有配图的菜名（{count} 个）
HAS_IMAGE_NAMES: frozenset[str] = frozenset(
    (
{names}
    )
)


def has_image(dish_name: str) -> bool:
    """这道菜有配图吗。"""
    return dish_name in HAS_IMAGE_NAMES
'''


def read_dart_names() -> list[str]:
    text = DART.read_text(encoding="utf-8")
    # dict 里可能同一个菜名出现多次，去重后排序，保证生成结果稳定
    return sorted(set(PATTERN.findall(text)))


def render(names: list[str]) -> str:
    body = "\n".join(f'        "{name}",' for name in names)
    return HEADER.format(
        total=700, with_image=len(names), count=len(names), names=body
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="同步配图菜名到后端")
    parser.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = parser.parse_args()

    names = read_dart_names()
    print(f"前端 dish_images.dart：{len(names)} 个菜名")

    if args.check:
        if not TARGET.exists():
            print(f"[x] {TARGET} 不存在，先生成一次")
            return 1
        current = set(re.findall(r'^\s+"([^"]+)",', TARGET.read_text(encoding="utf-8"), re.M))
        if current == set(names):
            print("[ok] 两边一致")
            return 0
        print(f"[x] 不一致：后端多 {sorted(current - set(names))[:5]}，"
              f"少 {sorted(set(names) - current)[:5]}")
        return 1

    TARGET.write_text(render(names), encoding="utf-8")
    print(f"已写入 {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
