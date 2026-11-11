"""真实模型意图验收；只读取菜谱库，不调用天气或推荐生成。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlmodel import Session
from app.ai.client import request_options
from app.core.database import engine
from app.core.config import settings
from app.schemas.ai import AiChatRequest, AiConversationState
from app.services.ai_service import _route_smart


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, default=Path(__file__).resolve().parents[1] / 'evaluation/chat_intents.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live', action='store_true', help='显式允许真实模型调用；每次理解仍受后端超时与合同校验约束')
    args = parser.parse_args()
    if not args.live:
        parser.error('语义质量必须用真实模型验收，请显式传入 --live；离线不可用结果不能算作语义准确率。')
    if not settings.ai_configured:
        parser.error('尚未配置可用的模型服务，未执行验收。')
    cases = json.loads(args.dataset.read_text(encoding='utf-8'))
    rows, confusion = [], Counter()
    with Session(engine) as session, request_options(enabled=True):
        for case in cases:
            started = time.perf_counter()
            state = AiConversationState.model_validate(case['state']) if case.get('state') else None
            route = _route_smart(session=session, message=case['message'], payload=AiChatRequest(
                message=case['message'], last_intent=case.get('last_intent'),
                conversation_state=state,
            ))
            confusion[f"{case['intent']} -> {route.intent}"] += 1
            understanding = route.understanding
            actual_slots = understanding.slots.model_dump(mode='json') if understanding else {}
            actual_reference = understanding.reference.model_dump(mode='json') if understanding and understanding.reference else {}
            # 自然语言可能本身有歧义：备选标准只允许预先审查过的安全结果，不能事后随意改答案。
            expectations = [case, *[{**case, **alternative} for alternative in case.get('alternatives', [])]]
            variants = []
            for expectation in expectations:
                checks = {
                    'intent': route.intent == expectation['intent'],
                    'clarify': bool(route.clarification) == expectation.get('clarify', False),
                }
                if 'operation' in expectation:
                    checks['operation'] = understanding is not None and understanding.operation == expectation['operation']
                if 'slots' in expectation:
                    checks['slots'] = understanding is not None and all(
                        actual_slots.get(key) == value for key, value in expectation['slots'].items()
                    )
                if 'reference' in expectation:
                    checks['reference'] = understanding is not None and all(
                        actual_reference.get(key) == value for key, value in expectation['reference'].items()
                    )
                if 'detail_kind' in expectation:
                    checks['detail_kind'] = understanding is not None and understanding.detail_kind == expectation['detail_kind']
                variants.append(checks)
            correct = any(all(checks.values()) for checks in variants)
            checks = max(variants, key=lambda item: sum(item.values()))
            rows.append({
                **case, 'actual_intent': route.intent, 'actual_clarify': bool(route.clarification),
                'actual_operation': understanding.operation if understanding else None,
                'actual_confidence': understanding.confidence if understanding else None,
                'actual_slots': actual_slots if understanding else None,
                'actual_reference': actual_reference if understanding else None,
                'actual_detail_kind': understanding.detail_kind if understanding else None,
                'actual_clarification': route.clarification, 'source': route.source,
                'checks': checks, 'correct': correct,
                'elapsed_ms': round((time.perf_counter() - started) * 1000, 2),
            })
    correct = sum(r['correct'] for r in rows)
    check_failures = Counter(
        name for row in rows for name, passed in row['checks'].items() if not passed
    )
    false_recommendations = sum(
        r['intent'] == 'general' and not r['actual_clarify']
        and r['actual_intent'] in {'meal_recommendation', 'recommend_foods', 'cook_with_my_foods'}
        for r in rows
    )
    report = {'dataset': str(args.dataset), 'mode': 'live_model', 'model': settings.ai_model,
              'scope': 'curated live-model intent regression; not independent user evaluation or a guarantee of perfect semantics',
              'total': len(rows), 'correct': correct, 'accuracy': correct / len(rows),
              'general_false_recommendations': false_recommendations,
              'check_failures': dict(check_failures),
              'confusion_matrix': dict(confusion), 'cases': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in {'cases', 'confusion_matrix'}}, ensure_ascii=False))
    return 0 if correct == len(rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
