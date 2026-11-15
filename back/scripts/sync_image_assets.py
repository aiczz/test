"""Sync the bundled name registry; run from any directory."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
result = {}
for kind, filename in [("food", "ingredient_images.dart"), ("recipe", "dish_images.dart")]:
    raw = (root / "front/mealmind/lib/data" / filename).read_text(encoding="utf-8-sig")
    pairs = re.findall(r"'((?:\\.|[^'\\])*)'\s*:\s*'assets/images/([^']+)'", raw)
    result[kind] = {name.replace("\\'", "'").replace("\\\\", "\\"): file for name, file in pairs}
(root / "back/app/data/image_assets.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print({kind: len(items) for kind, items in result.items()})
