"""Rebuild a self-contained, reproducible delivery package.

This intentionally does not overwrite the source ZIP.  It keeps the source
row-order ids for backward compatibility, adds an explicit stable key, fills
the role field, and restores instruction text that was truncated by the
previous 60,000-character export cap when the original corpus contains the
full value.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import tempfile
import unicodedata
import zipfile
from pathlib import Path


def csv_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh)


def stable_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).strip().casefold()
    return "ing_" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:20]


def rewrite_main(path: Path) -> tuple[dict[int, int], dict[str, int]]:
    rows = list(csv_rows(path))
    keys = [stable_key(row["name"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("stable ingredient key collision")
    fieldnames = ["id", "stable_key"] + [k for k in rows[0] if k not in {"id", "stable_key"}]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for idx, (row, key) in enumerate(zip(rows, keys), 1):
            row = dict(row)
            row["id"] = str(idx)
            row["stable_key"] = key
            writer.writerow(row)
    return {idx: idx for idx in range(1, len(rows) + 1)}, {key: idx for idx, key in enumerate(keys, 1)}


def rewrite_roles(path: Path, seasonings: set[str]) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = []
        changed = 0
        for row in reader:
            if not row.get("role", "").strip():
                role = "main" if row.get("ingredient_id", "").strip() else (
                    "seasoning" if row.get("raw_name", "").strip() in seasonings else "other"
                )
                row["role"] = role
                changed += 1
            rows.append(row)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return changed


def restore_instructions(dishes_path: Path, aic_zip: Path) -> int:
    """Restore only source-backed prefixes; never invent or rewrite text."""
    with dishes_path.open("r", encoding="utf-8-sig", newline="") as fh:
        dishes = list(csv.DictReader(fh))
    targets = {
        int(row["id"]): row["instruction_text"]
        for row in dishes
        if len(row.get("instruction_text", "")) >= 60000
    }
    if not targets:
        return 0
    source: dict[int, str] = {}
    with zipfile.ZipFile(aic_zip) as archive:
        corpus_name = next(name for name in archive.namelist() if name.endswith("recipe_corpus_full.json"))
        with archive.open(corpus_name) as fh:
            for idx, raw in enumerate(fh, 1):
                if idx > max(targets):
                    break
                if idx not in targets:
                    continue
                obj = json.loads(raw)
                instructions = obj.get("recipeInstructions") or []
                if isinstance(instructions, list):
                    # The delivery builder prefixes each source instruction
                    # item with its 1-based step number.  Recreate that exact
                    # reversible transformation before comparing prefixes.
                    source[idx] = "\n".join(
                        f"{step_no}. {item}"
                        for step_no, item in enumerate(instructions, 1)
                    )
                else:
                    source[idx] = str(instructions)
    changed = 0
    for row in dishes:
        idx = int(row["id"])
        current = row.get("instruction_text", "")
        original = source.get(idx, "")
        if original and len(original) > len(current) and original.startswith(current):
            row["instruction_text"] = original
            changed += 1
    with dishes_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=dishes[0].keys())
        writer.writeheader()
        writer.writerows(dishes)
    return changed


def update_schema(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")
    old = "    id             INT PRIMARY KEY AUTO_INCREMENT,\n    name           VARCHAR(100) NOT NULL UNIQUE"
    new = (
        "    id             INT PRIMARY KEY AUTO_INCREMENT,\n"
        "    stable_key     CHAR(24) NOT NULL UNIQUE COMMENT '由规范食材名生成的稳定键',\n"
        "    name           VARCHAR(100) NOT NULL UNIQUE"
    )
    if old not in text:
        raise ValueError("ingredients schema anchor not found")
    path.write_text(text.replace(old, new, 1).replace("61 个子类", "71 个子类"), encoding="utf-8")


def update_loader(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")
    old = '"cols": ([(' + '"name", "name"), ("usage_count", "usage_count"),'
    new = '"cols": ([(' + '"id", "id"), ("stable_key", "stable_key"),\n                  ("name", "name"), ("usage_count", "usage_count"),'
    if old not in text:
        raise ValueError("loader ingredients mapping anchor not found")
    text = text.replace(old, new, 1).replace(
        '"ignore": False,\n        # 营养素列',
        '"ignore": False,\n        "explicit_id": True,\n        # 营养素列',
        1,
    )
    text = text.replace('"numeric": [cn for _, cn in NUTRI_MAP] + ["usage_count"],',
                        '"numeric": ["id"] + [cn for _, cn in NUTRI_MAP] + ["usage_count"],', 1)
    path.write_text(text, encoding="utf-8")


def update_docs(root: Path) -> None:
    checklist = root / "交付清单_给开发.md"
    with checklist.open("a", encoding="utf-8") as fh:
        fh.write(
            "\n\n### 修正版变更（本包）\n\n"
            "- `main_ingredient.csv` 增加显式 `id` 与 `stable_key`，导入后不再依赖隐式自增顺序。\n"
            "- `dish_ingredients.role` 已补齐：`main` / `seasoning` / `other`。\n"
            "- 对照 AIC 原始语料恢复可验证的做法文本截断；未能从原文恢复的内容不改写。\n"
            "- 本包仍需整库导入，不要与旧版 CSV 混用。\n"
        )
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8-sig")
    banner = (
        "> ✅ 当前修正版快照：主食材 16,693 行、菜品 200,000 行、菜品-食材 1,372,579 行。\n"
        "> `main_ingredient.csv` 含显式 `id` / `stable_key`；关联表请整库重建。\n\n"
    )
    if "当前修正版快照" not in text:
        readme.write_text(banner + text, encoding="utf-8")


def build(input_zip: Path, aic_zip: Path, output_zip: Path) -> dict[str, int]:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="delivery_rebuild_") as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(input_zip) as archive:
            archive.extractall(root)
        rewrite_main(root / "main_ingredient.csv")
        seasoning_names = {row["name"] for row in csv_rows(root / "excluded_seasonings.csv")}
        role_count = rewrite_roles(root / "dish_ingredients.csv", seasoning_names)
        restored = restore_instructions(root / "dishes.csv", aic_zip)
        update_schema(root / "schema.sql")
        update_loader(root / "load_to_mysql.py")
        update_docs(root)
        report = root / "修正版审计说明.md"
        report.write_text(
            "# 修正版审计说明\n\n"
            "本包由 `菜谱数据库_交付_20260918 (1).zip` 生成，未覆盖源包。\n\n"
            f"- `dish_ingredients.role` 补齐：{role_count:,} 行\n"
            f"- 从 AIC 原始语料恢复做法截断：{restored} 行\n"
            "- 食材关联的原数字 id 保持不变，同时新增 `stable_key`。\n"
            "- 仍建议在导入前对主食材长尾名做业务人工复核。\n",
            encoding="utf-8",
        )
        if output_zip.exists():
            output_zip.unlink()
        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
    return {"roles_filled": role_count, "instructions_restored": restored}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--aic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.input, args.aic, args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
