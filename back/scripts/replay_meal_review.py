"""Replay saved real AI menus through the new critic, without any model calls."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'back'))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    db, source, output = args.database.resolve(strict=True), args.source.resolve(strict=True), args.output.resolve()
    protocol = json.loads((source / 'protocol.json').read_text(encoding='utf-8'))
    checksum = hashlib.sha256(db.read_bytes()).hexdigest()
    if checksum != protocol['database_sha256']:
        p.error('Snapshot differs from the real-model run; cannot make a paired replay.')
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'records.json').exists():
        p.error('Output already exists; use a new directory.')
    os.environ['DATABASE_URL'] = f'sqlite:///file:{db.as_posix()}?mode=ro&uri=true'
    os.environ['CONTENT_MODE'] = 'compact'
    os.chdir(ROOT / 'back')
    from sqlalchemy import create_engine
    from sqlmodel import Session
    from app.ai import client
    from app.core.config import settings
    from app.schemas.ai import AiRecommendRequest
    from app.services import ai_service, meal_selection, scoring_service
    from app.repositories.catalog_insight_repository import dish_insights
    from app.services.scoring_service import ScoredItem
    from app.services.weather_service import WeatherContext
    settings.ai_enabled = False
    settings.weather_enabled = False
    engine = create_engine(os.environ['DATABASE_URL'])
    frozen = datetime.fromisoformat(protocol['date'] + 'T12:00:00')
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.replace(tzinfo=tz)
    captured = []
    original_score = scoring_service.score_dishes
    def capture(*a, **kw):
        result = original_score(*a, **kw)
        captured.append(result)
        return result
    records = []
    rows = json.loads((source / 'observations.json').read_text(encoding='utf-8'))
    with client.request_options(enabled=False), patch.object(ai_service, 'datetime', FixedDateTime), patch.object(
        ai_service, '_weather_for', return_value=WeatherContext(**protocol['weather'])), patch.object(
        scoring_service, 'score_dishes', side_effect=capture), Session(engine) as session:
        for row in rows:
            if row['version'] != '规则＋AI' or not row.get('valid_pair'):
                continue
            captured.clear()
            payload = AiRecommendRequest(**row['input'])
            rules = ai_service.recommend_recipes(session, None, payload)
            captured_hash = digest([[dict(id=x.item_id, name=x.name, score=x.score, reason=x.reason,
                factors=x.factors, insight=asdict(x.insight) if x.insight else None) for x in batch] for batch in captured])
            if captured_hash != row['candidate_hash']:
                raise RuntimeError(f"Candidate mismatch in scenario {row['scenario']}, repeat {row['repeat']}")
            pool = captured[-1]
            by_id = {c.item_id: c for c in pool}
            before = [by_id[c['id']] for c in row['checks']]
            fixed = [ScoredItem(raw=None, item_id=i, name=v.name, score=0, reason='', insight=v)
                     for i, v in dish_insights(session, payload.menu_recipe_ids).items()]
            after, changes = meal_selection.review(before, pool, existing=fixed,
                requirements=meal_selection.policy(payload.message or '', payload.preferences))
            records.append(dict(scenario=row['scenario'], repeat=row['repeat'], candidate_hash=captured_hash,
                before_ids=[c.item_id for c in before], after_ids=[c.item_id for c in after], changes=changes,
                before=meal_selection.summary(before, set(payload.food_ids)),
                after=meal_selection.summary(after, set(payload.food_ids)), rules=rules.meal_summary))
    if hashlib.sha256(db.read_bytes()).hexdigest() != checksum:
        raise RuntimeError('Read-only snapshot changed')
    metrics = {}
    for version in ('before', 'after', 'rules'):
        groups = [r[version] for r in records]
        metrics[version] = dict(menus=len(groups), vegetable_and_protein=sum(g['vegetable_dishes'] > 0 and g['protein_dishes'] > 0 for g in groups),
            multiple_soups=sum(g['soup_dishes'] > 1 for g in groups))
    summary = dict(network_calls=0, paired_replays=len(records), changed_menus=sum(bool(r['changes']) for r in records),
        replacements=sum(len(r['changes']) for r in records), metrics=metrics,
        source_code_hash=digest([(str(f.relative_to(ROOT)), hashlib.sha256(f.read_bytes()).hexdigest()) for f in sorted((ROOT/'back'/'app').rglob('*.py'))]))
    for filename, data in [('records.json', records), ('analysis.json', summary)]:
        (output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 整餐复核离线回放', '', '使用上一轮真实AI的菜单和同一只读快照，逐组核对候选内容哈希；本次没有模型网络调用。',
        '复核前、复核后、当前规则组合均使用本轮同一套配料分类，不与旧报告的标签分类数值直接比较。', '',
        '| 指标 | AI原菜单（新分类） | AI复核后 | 当前规则 |', '|---|---:|---:|---:|']
    for label, key in [('菜单数', 'menus'), ('同时含蔬菜和蛋白类', 'vegetable_and_protein'), ('多道汤菜单', 'multiple_soups')]:
        lines.append('| ' + label + ' | ' + ' | '.join(str(metrics[v][key]) for v in ('before','after','rules')) + ' |')
    lines += ['', f"调整{summary['changed_menus']}组菜单，共替换{summary['replacements']}道；仅从原合格候选中替换，保留未调整菜品的顺序。",
        '这是保存结果的复核验证，不是新一轮真实AI对照；不推断模型新回复质量、端到端延迟、营养均衡或用户满意度。独立场景数仍为10，重复3次不视为新增独立样本。']
    (output/'复核回放报告.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    engine.dispose()
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    main()
