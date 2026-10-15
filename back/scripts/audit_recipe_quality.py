"""Read-only catalogue quality audit; export evidence for manual review."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from sqlmodel import Session
from app.core.database import engine
from app.data.dish_images import has_image
from app.utils.recipe_duration import duration_from_text, duration_evidence


def original_duration(raw):
    values = []
    for pattern in (r'(\d+)\s*[-~至到]\s*(\d+)\s*分钟',
                    r'(\d+)\s*分钟', r'(\d+(?:\.\d+)?)\s*个?\s*小时'):
        for match in re.finditer(pattern, raw):
            value = max(float(v) for v in match.groups())
            values.append(value * (60 if '小时' in match[0] else 1))
    return int(min(max(values), 180)) if values else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    with Session(engine) as session:
        rows = session.execute(text('SELECT id, dish_name, instruction_text FROM dishes')).all()
    before = after = images = corrected = 0
    review = []
    for recipe_id, name, raw in rows:
        old, new = original_duration(raw or ''), duration_from_text(raw)
        before += old is not None
        after += new is not None
        images += has_image(name)
        corrected += old != new
        if old != new or new is None or not has_image(name):
            review.append({'id': recipe_id, 'name': name, 'old_minutes': old,
                           'step_minutes': new, 'has_image': has_image(name),
                           'evidence': duration_evidence(raw)})
    result = {'recipes': len(rows), 'with_images': images,
              'previous_explicit_timings': before, 'explicit_timings': after,
              'changed_timings': corrected, 'still_unknown': len(rows) - after,
              'note': 'Steps maximum timing, not total meal duration; source data unchanged.',
              'manual_review': review}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'manual_review'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
