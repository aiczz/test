"""配图清单两边必须一致。

`front/mealmind/lib/data/dish_images.dart`（前端，**真相**）负责「哪道菜用哪张图」，
`back/app/data/dish_images.py`（后端，**生成物**）只用来让推荐排序知道
「这道菜有没有图」。

两份手工维护一定会漂移 —— 那时候后端会以为某道菜有图、前端其实没有，
排序偏好就白做了。所以这里盯着。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DART = ROOT / "front" / "mealmind" / "lib" / "data" / "dish_images.dart"
SYNC = ROOT / "sql" / "scripts" / "sync_dish_image_names.py"


def test_backend_image_names_match_the_frontend():
    """跑一次 --check，不一致就报错并说清怎么修。"""
    assert DART.exists(), f"找不到前端的配图表：{DART}"
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
        "前后端的配图清单对不上了。跑一次让它重新生成：\n"
        f"    python sql/scripts/sync_dish_image_names.py\n\n{result.stdout}{result.stderr}"
    )


def test_generated_module_is_not_hand_edited():
    """生成物开头必须有「不要手改」的提示 —— 免得有人直接改它。"""
    from app.data import dish_images

    source = Path(dish_images.__file__).read_text(encoding="utf-8")
    assert "不要手改" in source
    assert "sync_dish_image_names.py" in source


def test_has_image_is_exact_not_fuzzy():
    """按**完整菜名**精确匹配，不能是包含关系。

    配图是按完整菜名索引的。要是用了模糊匹配，「红烧肉」这种短名字
    就会把「红烧肉末茄子」也算成有图 —— 多算一道，推荐就会推出一个没有图的菜。
    """
    from app.data.dish_images import HAS_IMAGE_NAMES, has_image

    assert len(HAS_IMAGE_NAMES) > 100, "配图清单不该这么少"
    assert not has_image("")

    sample = max(HAS_IMAGE_NAMES, key=len)  # 取最长的那个当样本
    assert has_image(sample)
    # 多一个字符、少一个字符、多个空格，都不该再匹配上
    assert not has_image(sample + "x")
    assert not has_image(sample.rstrip() + " ")


def test_dart_map_is_parseable():
    """前端那张表本身要能被解析出成对的 (菜名, 资源) —— 语法写坏了这里先红。"""
    text = DART.read_text(encoding="utf-8")
    pairs = re.findall(r"'([^']+)'\s*:\s*'(assets/[^']+)'", text)
    assert len(pairs) > 100
    for name, asset in pairs:
        assert name.strip(), "菜名不能是空的"
        assert asset.endswith((".jpg", ".png", ".jpeg", ".webp")), asset
