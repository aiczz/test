"""Read-only quality checklist for the content catalogue."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlmodel import Session
from app.core.database import engine
from app.repositories import recipe_repository
from app.services import recipe_service
from app.services.ingredient_quality import is_ingredient, positive_amount


def audit(session):
    recipes, total = recipe_repository.list_recipes(session, limit=10000)
    rows = []
    for recipe in recipes:
        detail = recipe_service.get_detail(session, recipe.id)
        raw = recipe_repository.list_ingredients(session, recipe.id)
        rows.append({
            'id': recipe.id, 'name': recipe.name,
            'ingredient_count': len(detail.ingredients),
            'unknown_quantity_count': sum(i.amount is None for i in detail.ingredients),
            'ignored_header_count': sum(not is_ingredient(i.ingredient_name, i.amount) for i in raw),
            'invalid_numeric_quantity_count': sum(i.amount is not None and not positive_amount(i.amount) for i in raw),
            'step_count': len(detail.steps), 'duration_source': detail.duration_source,
            'notes': detail.quality_notes,
        })
    return {'scope': '当前内容目录，仅做数据完整性检查，不代表配方或烹饪时长经过人工验证',
            'catalogue_total': total, 'audited_count': len(rows),
            'recipes_without_ingredients': sum(r['ingredient_count'] == 0 for r in rows),
            'recipes_without_steps': sum(r['step_count'] == 0 for r in rows),
            'recipes_with_unknown_quantities': sum(r['unknown_quantity_count'] > 0 for r in rows),
            'recipes_with_unknown_duration': sum(r['duration_source'] == 'unknown' for r in rows),
            'review_queue': sorted((r for r in rows if r['notes']),
                                   key=lambda r: (-int(not r['step_count']), -int(not r['ingredient_count']), -r['unknown_quantity_count'], r['id']))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with Session(engine) as session:
        if engine.dialect.name == 'sqlite':
            session.connection().exec_driver_sql('PRAGMA query_only=ON')
        result = audit(session)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'review_queue'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
