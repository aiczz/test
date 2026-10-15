"""Offline, read-only intent evaluation. No model or weather network requests."""
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
from app.schemas.ai import AiChatRequest
from app.services.ai_service import _route_smart


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, default=Path(__file__).resolve().parents[1] / 'evaluation/chat_intents.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(args.dataset.read_text(encoding='utf-8'))
    rows, confusion = [], Counter()
    with Session(engine) as session, request_options(enabled=False):
        for case in cases:
            started = time.perf_counter()
            route = _route_smart(session=session, message=case['message'], payload=AiChatRequest(
                message=case['message'], last_intent=case.get('last_intent')))
            correct = route.intent == case['intent'] and bool(route.clarification) == case.get('clarify', False)
            confusion[f"{case['intent']} -> {route.intent}"] += 1
            rows.append({**case, 'actual_intent': route.intent, 'actual_clarify': bool(route.clarification),
                         'correct': correct, 'elapsed_ms': round((time.perf_counter() - started) * 1000, 2)})
    correct = sum(r['correct'] for r in rows)
    false_recommendations = sum(r['intent'] == 'general' and r['actual_intent'] != 'general' for r in rows)
    report = {'dataset': str(args.dataset), 'scope': 'curated offline routing regression; not independent user evaluation or model latency benchmark',
              'total': len(rows), 'correct': correct, 'accuracy': correct / len(rows),
              'general_false_recommendations': false_recommendations,
              'confusion_matrix': dict(confusion), 'cases': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in {'cases', 'confusion_matrix'}}, ensure_ascii=False))
    return 0 if correct == len(rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
