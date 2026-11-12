"""把前端「哪些食材有实拍图」的清单同步到后端。

【为什么需要】
食材配图是**按名字**映射的，那张表在前端（`lib/data/ingredient_images.dart`），
后端只给名字、不认识图片。但食材列表需要「优先展示有图的」——
图库只逐张核对过 1112 个名字，另外几千条扩展食材没有实拍图，
不排序的话列表前几屏会全是通用占位图。

【为什么不干脆让后端也维护一份】
那就成了两个真相来源，改一边忘一边，两边慢慢对不上。
所以这里**只做单向生成**：Dart 那张表是唯一的真相，
这个脚本把它读成 Python 常量，`tests/test_food_images_sync.py` 会盯着两边一致。

用法：
    python sql/scripts/sync_food_image_names.py            # 生成
    python sql/scripts/sync_food_image_names.py --check     # 只校验，不写
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DART = ROOT / "front" / "mealmind" / "lib" / "data" / "ingredient_images.dart"
TARGET = ROOT / "back" / "app" / "data" / "food_images.py"

PATTERN = re.compile(r"'([^']+)'\s*:\s*'assets/")

HEADER = '''"""哪些食材有实拍配图 —— **由脚本生成，不要手改**。

来源：`front/mealmind/lib/data/ingredient_images.dart`（那张才是真相）
生成：`python sql/scripts/sync_food_image_names.py`
校验：`tests/test_food_images_sync.py` 会盯着两边一致

后端拿它做一件事：食材列表按「有实拍图优先」排序。
图库只核对过这些名字的图；没图的食材仍然展示，只是排在后面，
避免列表前几屏全是通用占位图。
"""

from __future__ import annotations

from functools import lru_cache

# 有配图的食材名（{count} 个）
HAS_IMAGE_NAMES: frozenset[str] = frozenset(
    (
{names}
    )
)

# 长名优先 —— 和前端 `_foodImageForName` 的包含匹配口径一致，
# 否则「小白菜」会先被「白菜」抢走、配上错的图。
_NAMES_BY_LENGTH: tuple[str, ...] = tuple(
    sorted(HAS_IMAGE_NAMES, key=len, reverse=True)
)


@lru_cache(maxsize=20000)
def has_image(food_name: str) -> bool:
    """这个食材有实拍配图吗（精确同名，或名字里含已知食材名）。"""
    if not food_name:
        return False
    if food_name in HAS_IMAGE_NAMES:
        return True
    return any(key in food_name for key in _NAMES_BY_LENGTH)
'''


def read_dart_names() -> list[str]:
    text = DART.read_text(encoding="utf-8")
    # dict 里可能同一个名字出现多次，去重后排序，保证生成结果稳定
    return sorted(set(PATTERN.findall(text)))


def render(names: list[str]) -> str:
    body = "\n".join(f'        "{name}",' for name in names)
    return HEADER.format(count=len(names), names=body)


def main() -> int:
    parser = argparse.ArgumentParser(description="同步配图食材名到后端")
    parser.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = parser.parse_args()

    names = read_dart_names()
    print(f"前端 ingredient_images.dart：{len(names)} 个食材名")

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
