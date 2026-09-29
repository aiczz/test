"""Clean delivery CSV files using schema.sql as the sole rule source.

The script deliberately ignores README/Markdown guidance. It preserves the
source ZIP, rewrites only schema-governed CSV values, and emits a new ZIP.
"""

from __future__ import annotations

import argparse
import csv
import decimal
import hashlib
import json
import re
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


ROUNDING = decimal.ROUND_HALF_UP

NUTRIENT_COLUMNS = {
    "可食部%": (6, 1),
    "水分g": (8, 2),
    "能量kcal": (8, 1),
    "能量kJ": (8, 1),
    "蛋白质g": (8, 2),
    "脂肪g": (8, 2),
    "碳水化合物g": (8, 2),
    "膳食纤维g": (8, 2),
    "胆固醇mg": (8, 1),
    "灰分g": (8, 2),
    "维生素A(ugRE)": (10, 1),
    "胡萝卜素(ug)": (10, 1),
    "视黄醇(ug)": (10, 1),
    "硫胺素mg": (8, 3),
    "核黄素mg": (8, 3),
    "烟酸mg": (8, 3),
    "维生素Cmg": (8, 1),
    "维生素E总mg": (8, 2),
    "钙mg": (10, 1),
    "磷mg": (10, 1),
    "钾mg": (10, 1),
    "钠mg": (10, 1),
    "镁mg": (10, 1),
    "铁mg": (10, 2),
    "锌mg": (10, 2),
    "硒(ug)": (10, 2),
    "铜mg": (10, 2),
    "锰mg": (10, 2),
}

DISH_NUTRITION_COLUMNS = {
    "total_weight_g": (10, 1),
    "energy_kcal": (10, 1),
    "protein_g": (10, 2),
    "fat_g": (10, 2),
    "cho_g": (10, 2),
    "dietary_fiber_g": (10, 2),
    "ca_mg": (10, 1),
    "fe_mg": (10, 2),
    "na_mg": (10, 1),
    "matched_ratio": (5, 2),
    "weight_confidence": (5, 2),
}

# These are conservative, literal corrections justified directly by the SQL
# meanings: ingredients are normalized food names, seasonings do not belong in
# ingredients, and excluded_names holds instructions/tools/quantity fragments.
CANONICAL_NAME_MAP = {
    "鸡蛋一个": "鸡蛋",
    "克面粉": "面粉",
    "奶油」": "奶油",
}

EXCLUDED_INGREDIENT_NAMES = {
    "凉开水",
    "饮水",
    "冷开水",
    "凉白开水",
    "克水",
    "就行水",
    "各种食材",
    "其他食材",
    "所需食材",
    "水量水",
    "榨汁机",
    "筷子",
    "棉线",
    "一下",
    "部分食材",
    "食材",
    "牌〉",
    "色面团〗",
}

SEASONING_INGREDIENT_NAMES = {
    "葱姜水",
    "各种香料",
    "调味粉",
    "卤水",
    "其他香料",
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def norm_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").replace("\x00", "").strip()


def norm_key(value: str) -> str:
    return norm_text(value).casefold()


def ingredient_key(name: str) -> str:
    return "ing_" + hashlib.sha1(norm_key(name).encode("utf-8")).hexdigest()[:20]


def clean_decimal(value: str, precision: int, scale: int, audit: Counter) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        number = decimal.Decimal(raw)
    except decimal.InvalidOperation:
        audit[f"decimal_to_null:{raw}"] += 1
        return ""
    if not number.is_finite():
        audit[f"decimal_to_null:{raw}"] += 1
        return ""
    quantum = decimal.Decimal(1).scaleb(-scale)
    rounded = number.quantize(quantum, rounding=ROUNDING)
    if abs(rounded) >= decimal.Decimal(10) ** (precision - scale):
        audit["decimal_overflow_to_null"] += 1
        return ""
    if rounded != number:
        audit["decimal_rounded"] += 1
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def extract_decorated_target(name: str) -> str:
    text = norm_text(name)
    text = re.sub(r"^[°℃]\s*[Cc]?", "", text)
    text = re.sub(r"^[^0-9A-Za-z\u4e00-\u9fff]+", "", text)
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+$", "", text)
    return text.strip()


def verify_schema_rules(schema: str) -> None:
    required = [
        "name           VARCHAR(100) NOT NULL UNIQUE COMMENT '规范食材名'",
        "core=成分表有权威数据 / common=语料引用>=20 / tail=长尾",
        "main=主料 seasoning=调味料 other=其他",
        "explicit/per_unit/category/vague",
        "general/cuisine/season/method/audience",
        "suspect         TINYINT(1) NOT NULL DEFAULT 0",
        "instruction_text MEDIUMTEXT",
    ]
    missing = [item for item in required if item not in schema]
    if missing:
        raise ValueError(f"schema.sql rules changed or missing: {missing}")


def clean_package(input_zip: Path, output_zip: Path) -> dict[str, int]:
    audit: Counter = Counter()
    with tempfile.TemporaryDirectory(prefix="sql_clean_") as temp_dir:
        root = Path(temp_dir)
        with zipfile.ZipFile(input_zip) as archive:
            archive.extractall(root)

        schema_path = root / "schema.sql"
        schema = schema_path.read_text(encoding="utf-8-sig")
        verify_schema_rules(schema)

        # Lookup tables used by SQL foreign keys and exclusion semantics.
        _, seasoning_rows = read_csv(root / "excluded_seasonings.csv")
        seasoning_names = {norm_key(row["name"]) for row in seasoning_rows}
        junk_fields, junk_rows = read_csv(root / "excluded_junk.csv")
        junk_names = {norm_key(row["name"]) for row in junk_rows}

        ingredient_fields, ingredients = read_csv(root / "main_ingredient.csv")
        by_name = {norm_key(row["name"]): row for row in ingredients}
        id_remap: dict[str, str | None] = {row["id"]: row["id"] for row in ingredients}
        removed_ids: set[str] = set()

        # The SQL requires a normalized unique ingredient name. Only perform
        # deterministic punctuation cleanup: merge with an existing canonical
        # name, map an already-excluded term out, or remove a leading '&'.
        for row in ingredients:
            original = row["name"]
            cleaned = extract_decorated_target(original)
            if cleaned == norm_text(original):
                continue
            cleaned_key = norm_key(cleaned)
            existing = by_name.get(cleaned_key)
            if existing and existing["id"] != row["id"]:
                id_remap[row["id"]] = existing["id"]
                existing["usage_count"] = str(
                    int(existing["usage_count"] or 0) + int(row["usage_count"] or 0)
                )
                removed_ids.add(row["id"])
                audit["ingredient_names_merged"] += 1
            elif cleaned_key in junk_names or cleaned_key in seasoning_names:
                id_remap[row["id"]] = None
                removed_ids.add(row["id"])
                if norm_key(original) not in junk_names:
                    junk_rows.append({"name": original, "reason": "SQL规范名清洗"})
                    junk_names.add(norm_key(original))
                audit["ingredient_names_excluded"] += 1
            elif original.startswith("&") and cleaned:
                row["name"] = cleaned
                by_name[cleaned_key] = row
                audit["ingredient_names_renamed"] += 1

        current_by_name = {
            norm_key(row["name"]): row
            for row in ingredients
            if row["id"] not in removed_ids
        }
        for source_name, target_name in CANONICAL_NAME_MAP.items():
            source = current_by_name.get(norm_key(source_name))
            if not source:
                continue
            target = current_by_name.get(norm_key(target_name))
            if target and target["id"] != source["id"]:
                id_remap[source["id"]] = target["id"]
                target["usage_count"] = str(
                    int(target["usage_count"] or 0) + int(source["usage_count"] or 0)
                )
                removed_ids.add(source["id"])
                audit["ingredient_names_merged"] += 1
            else:
                source["name"] = target_name
                current_by_name[norm_key(target_name)] = source
                audit["ingredient_names_renamed"] += 1

        for source_name in EXCLUDED_INGREDIENT_NAMES:
            source = current_by_name.get(norm_key(source_name))
            if not source or source["id"] in removed_ids:
                continue
            id_remap[source["id"]] = None
            removed_ids.add(source["id"])
            if norm_key(source_name) not in junk_names:
                junk_rows.append({"name": source_name, "reason": "SQL非食材清洗"})
                junk_names.add(norm_key(source_name))
            audit["ingredient_names_excluded"] += 1

        for source_name in SEASONING_INGREDIENT_NAMES:
            source = current_by_name.get(norm_key(source_name))
            if not source or source["id"] in removed_ids:
                continue
            id_remap[source["id"]] = None
            removed_ids.add(source["id"])
            if norm_key(source_name) not in seasoning_names:
                seasoning_rows.append(
                    {
                        "name": source_name,
                        "usage_count": source["usage_count"],
                        "reason": "SQL调味料清洗",
                    }
                )
                seasoning_names.add(norm_key(source_name))
            audit["ingredient_names_to_seasonings"] += 1

        # Resolve merge chains, e.g. a decorated name merged into a generic
        # term that was subsequently classified as excluded.
        def resolve_id(value: str | None) -> str | None:
            seen: set[str] = set()
            while value is not None and value in id_remap and id_remap[value] != value:
                if value in seen:
                    raise ValueError("ingredient id remap cycle")
                seen.add(value)
                value = id_remap[value]
            return value

        id_remap = {key: resolve_id(value) for key, value in id_remap.items()}

        ingredients = [row for row in ingredients if row["id"] not in removed_ids]
        for row in ingredients:
            row["name"] = norm_text(row["name"])[:100]
            row["stable_key"] = ingredient_key(row["name"])
            row["usage_count"] = str(max(0, int(row["usage_count"] or 0)))
            for column, (precision, scale) in NUTRIENT_COLUMNS.items():
                row[column] = clean_decimal(row[column], precision, scale, audit)
            # SQL is explicit: common requires usage_count >= 20.
            row["quality"] = (
                "core"
                if row.get("nutrition_source_name", "").strip()
                else "common"
                if int(row["usage_count"]) >= 20
                else "tail"
            )
        stable_keys = [row["stable_key"] for row in ingredients]
        names = [norm_key(row["name"]) for row in ingredients]
        if len(stable_keys) != len(set(stable_keys)) or len(names) != len(set(names)):
            raise ValueError("ingredient normalization created duplicate unique keys")
        write_csv(root / "main_ingredient.csv", ingredient_fields, ingredients)
        write_csv(root / "excluded_junk.csv", junk_fields, junk_rows)
        seasoning_fields = ["name", "usage_count", "reason"]
        write_csv(root / "excluded_seasonings.csv", seasoning_fields, seasoning_rows)

        # Remap ingredient foreign keys and preserve composite-key uniqueness.
        for filename, second_key in [
            ("ingredient_effects.csv", "effect_id"),
            ("ingredient_groups.csv", "group_id"),
        ]:
            fields, relation_rows = read_csv(root / filename)
            seen: set[tuple[str, str]] = set()
            cleaned_rows = []
            for row in relation_rows:
                mapped = id_remap.get(row["ingredient_id"], row["ingredient_id"])
                if mapped is None:
                    audit[f"{filename}:dropped"] += 1
                    continue
                row["ingredient_id"] = mapped
                key = (mapped, row[second_key])
                if key in seen:
                    audit[f"{filename}:deduplicated"] += 1
                    continue
                seen.add(key)
                cleaned_rows.append(row)
            write_csv(root / filename, fields, cleaned_rows)

        # Clean detail enum values and foreign keys according to SQL comments.
        detail_fields, details = read_csv(root / "dish_ingredients.csv")
        detail_counts: Counter = Counter()
        linked_grams: dict[str, decimal.Decimal] = defaultdict(decimal.Decimal)
        valid_grams_sources = {"", "explicit", "per_unit", "category", "vague"}
        for row in details:
            row["raw_name"] = norm_text(row["raw_name"])[:255]
            row["raw_text"] = (row["raw_text"] or "").replace("\x00", "")[:255]
            row["quantity"] = norm_text(row["quantity"])[:100]
            old_id = row["ingredient_id"].strip()
            mapped = id_remap.get(old_id, old_id) if old_id else ""
            row["ingredient_id"] = mapped or ""
            row["role"] = (
                "main"
                if row["ingredient_id"]
                else "seasoning"
                if norm_key(row["raw_name"]) in seasoning_names
                else "other"
            )
            if row["grams_source"] not in valid_grams_sources:
                audit[f"grams_source_to_default:{row['grams_source']}"] += 1
                row["grams_source"] = ""
            row["grams"] = clean_decimal(row["grams"], 10, 1, audit)
            detail_counts[row["dish_id"]] += 1
            if row["ingredient_id"] and row["grams"]:
                linked_grams[row["dish_id"]] += decimal.Decimal(row["grams"])
        write_csv(root / "dish_ingredients.csv", detail_fields, details)

        # Reconcile denormalized counts/weight with the SQL-governed detail.
        dish_fields, dishes = read_csv(root / "dishes.csv")
        dish_weight: dict[str, str] = {}
        for row in dishes:
            row["dish_name"] = norm_text(row["dish_name"])[:255]
            row["description"] = (row["description"] or "").replace("\x00", "")
            row["cuisine"] = norm_text(row["cuisine"])[:50]
            row["ingredient_text"] = (row["ingredient_text"] or "").replace("\x00", "")
            row["instruction_text"] = (row["instruction_text"] or "").replace("\x00", "")
            row["ingredient_count"] = str(detail_counts[row["id"]])
            total = linked_grams[row["id"]].quantize(decimal.Decimal("0.1"), rounding=ROUNDING)
            new_weight = format(total, ".1f")
            if row["total_weight_g"] != new_weight:
                audit["dish_total_weight_reconciled"] += 1
            row["total_weight_g"] = new_weight
            dish_weight[row["id"]] = new_weight
        write_csv(root / "dishes.csv", dish_fields, dishes)

        nutrition_fields, nutrition_rows = read_csv(root / "dish_nutrition.csv")
        for row in nutrition_rows:
            for column, (precision, scale) in DISH_NUTRITION_COLUMNS.items():
                row[column] = clean_decimal(row[column], precision, scale, audit)
            if row["dish_id"] in dish_weight:
                row["total_weight_g"] = dish_weight[row["dish_id"]]
            for column in ("explicit_count", "estimated_count", "vague_count"):
                row[column] = str(max(0, int(row[column] or 0)))
            row["suspect"] = row["suspect"] if row["suspect"] in {"0", "1"} else "1"
        write_csv(root / "dish_nutrition.csv", nutrition_fields, nutrition_rows)

        # Keep the SQL comment synchronized with the valid FK-backed dictionary.
        _, subcategories = read_csv(root / "ingredient_subcategories.csv")
        schema = re.sub(r"食材子类（\d+ 个）", f"食材子类（{len(subcategories)} 个）", schema)
        schema_path.write_text(schema, encoding="utf-8")

        output_zip.parent.mkdir(parents=True, exist_ok=True)
        if output_zip.exists():
            output_zip.unlink()
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())

    return dict(sorted(audit.items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = clean_package(args.input, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
