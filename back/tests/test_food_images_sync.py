"""配图食材清单两边必须一致。

`front/mealmind/lib/data/ingredient_images.dart`（前端，**真相**）负责
「哪张图配哪个食材」，`back/app/data/food_images.py`（后端，**生成物**）
只用来让食材列表知道「哪些食材有实拍图」，从而把有图的排在前面。

两份手工维护一定会漂移 —— 那时候后端以为某个食材有图、前端其实没有，
「有图优先」就白排了。所以这里盯着。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DART = ROOT / "front" / "mealmind" / "lib" / "data" / "ingredient_images.dart"
SYNC = ROOT / "sql" / "scripts" / "sync_food_image_names.py"


def test_backend_image_names_match_the_frontend():
    """跑一次 --check，不一致就报错并说清怎么修。"""
    assert DART.exists(), f"找不到前端的食材配图表：{DART}"
    result = subprocess.run(
        [sys.executable, str(SYNC), "--check"],
        capture_output=True,
        text=True,
        # Windows 默认用 GBK 解码子进程输出，脚本打的是中文 → 会 UnicodeDecodeError
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        "前后端的食材配图清单对不上了。跑一次让它重新生成：\n"
        f"    python sql/scripts/sync_food_image_names.py\n\n{result.stdout}{result.stderr}"
    )


def test_generated_module_is_not_hand_edited():
    """生成物开头必须有「不要手改」的提示 —— 免得有人直接改它。"""
    from app.data import food_images

    source = Path(food_images.__file__).read_text(encoding="utf-8")
    assert "不要手改" in source
    assert "sync_food_image_names.py" in source


def test_has_image_matches_frontend_rules():
    """和前端 `_foodImageForName` 同口径：精确同名，或名字里含已知食材名。"""
    from app.data.food_images import HAS_IMAGE_NAMES, has_image

    assert len(HAS_IMAGE_NAMES) > 500, "配图食材清单不该这么少"
    assert not has_image("")
    assert not has_image("秘制调味料")
    # 图库里的名字必须命中
    assert has_image("土豆")
    # 扩展食材（带修饰词）也能通过「包含」命中，和前端一致
    assert has_image("去皮土豆")


def test_dart_map_is_parseable():
    """前端那张表本身要能被解析出成对的 (食材名, 资源) —— 语法写坏了这里先红。"""
    text = DART.read_text(encoding="utf-8")
    pairs = re.findall(r"'([^']+)'\s*:\s*'(assets/[^']+)'", text)
    assert len(pairs) > 500
    for name, asset in pairs:
        assert name.strip(), "食材名不能是空的"
        assert asset.endswith((".jpg", ".png", ".jpeg", ".webp")), asset
