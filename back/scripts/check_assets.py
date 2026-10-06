"""检查前端引用的图片资源是否都真的存在。

为什么值得单独查：图片库（`dish_image_library/` / `ingredient_image_library/`）
在 .gitignore 里，没有进仓库。如果 `dish_images.dart` / `ingredient_images.dart`
引用了仓库里不存在的文件，那部署到服务器上就是一堆裂图 ——
而且是本地开发时不一定能发现的那种（本地有、服务器没有）。
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2] / "front" / "mealmind"
REF_PATTERN = re.compile(r"'(assets/[^']+)'")


def main() -> int:
    print("=== assets 目录 ===")
    for name in ("assets", "assets/images"):
        path = ROOT / name
        if not path.exists():
            print(f"  [x] {name} 不存在")
            continue
        files = [f for f in path.rglob("*") if f.is_file()]
        images = [
            f for f in files
            if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        ]
        size = sum(f.stat().st_size for f in files) / 1024 / 1024
        print(f"  {name}: {len(files)} 个文件，其中图片 {len(images)} 个，{size:.1f} MB")

    print("\n=== 代码里引用的图，有没有缺的 ===")
    failed = False
    for rel in ("lib/data/dish_images.dart", "lib/data/ingredient_images.dart"):
        path = ROOT / rel
        if not path.exists():
            print(f"  [--] {rel} 不存在")
            continue
        refs = set(REF_PATTERN.findall(path.read_text(encoding="utf-8")))
        missing = sorted(r for r in refs if not (ROOT / r).exists())
        status = "[ok]" if not missing else "[x] "
        print(f"  {status} {rel}: 引用 {len(refs)} 个，缺 {len(missing)} 个")
        for item in missing[:8]:
            print(f"        [x] {item}")
        if missing:
            failed = True

    print("\n=== 结论 ===")
    if failed:
        print("  有裂图风险：缺的图要么补进仓库，要么把引用改成兜底图。")
        return 1
    print("  引用的图全都在仓库里，部署后不会裂图。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
