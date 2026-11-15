"""Link existing photos to catalog names and explicit aliases; never guess by substring."""
import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "sql/cleaned_v2"
ASSETS = ROOT / "front/mealmind/assets/images"
DART = ROOT / "front/mealmind/lib/data/ingredient_images.dart"
BEGIN = "  // BEGIN catalog photo aliases\n"
END = "  // END catalog photo aliases\n"


def normalized(name):
    name = unicodedata.normalize("NFKC", name).strip()
    name = re.sub(r"^[\s./_·•－—-]+", "", name)
    # Remove quantities only when the entire remainder is a known ingredient.
    name = re.sub(r"^(?:一丢丢|一小撮|些许|少许|少量|适量|几滴|几粒|一点点|一点|点|酌量|瓷勺|茶勺|调料勺|小撮|三分之|碗|匙|盖|克|量)+", "", name)
    name = re.sub(r"^[一二三四五六七八九十半两数几]+(?:小|大)?(?:碗|杯|勺|茶匙|汤匙|滴|粒|撮|根|片|段|颗|只|块)", "", name)
    name = re.sub(r"(?:少许|适量|少量)$", "", name)
    return name.strip()


def main():
    text = DART.read_text(encoding="utf-8-sig")
    text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), "", text, flags=re.S)
    mapping = dict(re.findall(r"'([^'\n]+)'\s*:\s*'assets/images/([^']+)'", text))
    original = dict(mapping)
    # Unambiguous preparation names and spelling variants, not generic mixtures.
    aliases = {"干辣椒段": "干辣椒", "段桂皮": "桂皮", "火腿片": "火腿", "盐匙盐": "盐", "铺菜籽油": "菜籽油", "据自己口味盐": "盐", "人口味盐": "盐", "黄记煌照烧汁": "照烧汁", "黑椒汁": "黑胡椒酱"}
    for name, canonical in aliases.items():
        if canonical in mapping:
            mapping.setdefault(name, mapping[canonical])
    with (DATA / "ingredient_catalog.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    eligible = [r for r in rows if r["is_edible"] == "1" and r["review_status"] == "verified"]
    # Generated assets are named by catalog id. Existing curated entries take priority.
    for row in eligible:
        filename = f"food-generated-{row['id']}.jpg"
        if row["name"] not in mapping and (ASSETS / filename).is_file():
            mapping[row["name"]] = filename
    # Explicit dataset aliases preserve the ingredient identity.
    with (DATA / "db_ingredients.csv").open(encoding="utf-8-sig") as f:
        foods = list(csv.DictReader(f))
    for _ in range(3):
        before = len(mapping)
        for row in eligible:
            name = row["name"]
            if name not in mapping and normalized(name) in mapping:
                mapping[name] = mapping[normalized(name)]
        for row in foods:
            if row.get("review_status") != "verified" or row.get("is_edible") != "1":
                continue
            photo = mapping.get(row["name"])
            if photo:
                for alias in json.loads(row.get("aliases_json") or "[]"):
                    mapping.setdefault(alias, photo)
        if len(mapping) == before:
            break
    additions = {k: v for k, v in mapping.items() if k not in original}
    def quote(s):
        return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("$", "\\$") + "'"
    block = BEGIN + "".join(f"  {quote(k)}: {quote('assets/images/' + v)},\n" for k, v in sorted(additions.items())) + END
    pos = text.rfind("};")
    assert pos >= 0
    DART.write_text(text[:pos] + block + text[pos:], encoding="utf-8")
    missing_files = sorted({v for v in mapping.values() if not (ASSETS / v).is_file()})
    missing = [{"id": r["id"], "name": r["name"], "usage_count": int(r["usage_count"])} for r in eligible if r["name"] not in mapping]
    report = {"catalog_total": len(rows), "verified_edible_total": len(eligible), "core_total": sum(r["ingredient_type"] == "core_raw" for r in eligible), "core_exact": sum(r["ingredient_type"] == "core_raw" and r["name"] in mapping for r in eligible), "verified_exact": len(eligible) - len(missing), "added_aliases": len(additions), "missing_files": missing_files, "unmapped_verified": missing}
    output = ROOT / "outputs/ingredient-image-mapping-audit.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "unmapped_verified"}, ensure_ascii=True))
    print("Remaining verified names:", len(missing))
    if missing_files:
        raise SystemExit("Mapped image files are missing")


if __name__ == "__main__":
    main()
