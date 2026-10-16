"""同代码、同只读快照、同候选集的配菜消融测试。

cd back
python scripts/benchmark_recommendations.py --database ../tmp/validation/catalog-snapshot-v2.sqlite

真实模型配置从 back/.env 读取；没有密钥时明确输出 skipped，绝不把回退算作AI。
默认10组场景各重复3次，配置模型后最多30次模型调用。不会调用线上业务接口。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
from datetime import datetime
from unittest.mock import patch
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "back"))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "controlled-validation-20261012")
    parser.add_argument("--date", default="2026-10-12")
    parser.add_argument("--repeats", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    database = args.database.resolve(strict=True)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "observations.json").exists():
        parser.error("输出目录已有测试记录。请用--output指定新目录，不覆盖历史证据。")
    frozen = datetime.fromisoformat(args.date + "T12:00:00")
    # 只读URI：推荐代码即使意外尝试写入，也会失败；不启动应用lifespan。
    os.environ["DATABASE_URL"] = f"sqlite:///file:{database.as_posix()}?mode=ro&uri=true"
    os.environ["CONTENT_MODE"] = "compact"
    os.chdir(ROOT / "back")
    from sqlalchemy import create_engine, text
    from sqlmodel import Session
    from app.core.config import settings
    from app.ai import client as ai_client
    from app.schemas.ai import AiRecommendRequest
    from app.services import ai_service, scoring_service, recipe_service, weather_service

    engine = create_engine(os.environ["DATABASE_URL"])
    available = bool(settings.ai_api_key.strip() and settings.ai_base_url.strip()) and not args.baseline_only
    settings.ai_temperature = 0
    # Repeated timings must represent fresh requests, not successful-response cache hits.
    settings.ai_response_cache_seconds = 0
    ai_client.clear_cache()
    ai_client.clear_failure_cooldowns()
    settings.weather_enabled = False
    weather = weather_service.current_weather(city=None, month=frozen.month, today=args.date)
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.replace(tzinfo=tz)

    with Session(engine) as session:
        foods = session.execute(text("SELECT id,name FROM ingredients WHERE name IN ('鸡蛋','番茄','西红柿') ORDER BY id")).all()
    food_ids = [int(i) for i, _ in foods][:3]
    common = dict(people=3, cook_minutes=45, low_sodium=False, preferences=[], avoid=[],
                  city=None, food_ids=[], menu_recipe_ids=[], meal="dinner", message="推荐家庭晚餐", count=3)
    cases = [
        ("普通家庭晚餐", {}),
        ("15分钟快手晚餐", dict(cook_minutes=15, message="只有15分钟做晚餐")),
        ("清淡偏好", dict(preferences=["清淡"], message="推荐清淡晚餐")),
        ("高蛋白偏好", dict(preferences=["高蛋白"], message="推荐高蛋白晚餐")),
        ("花生忌口", dict(avoid=["花生"], message="不能吃花生，请推荐晚餐")),
        ("海鲜忌口", dict(avoid=["海鲜"], message="不能吃海鲜，请推荐晚餐")),
        ("低钠", dict(low_sodium=True, message="推荐低钠晚餐")),
        ("多重忌口", dict(avoid=["花生", "海鲜", "乳制品", "香菜"], message="不能吃花生、海鲜、乳制品和香菜")),
        ("已有食材", dict(food_ids=food_ids, message="优先利用我选择的食材")),
        ("排除已选菜", dict(message="已选菜不要重复，推荐其他晚餐")),
    ]
    # 独立详情核查，不直接用被测试的过滤函数作为正确性判据。
    avoid_terms = {"海鲜": ["虾", "蟹", "贝", "蛤", "蚝", "鱿鱼", "章鱼", "鲍", "海参"],
                   "花生": ["花生"], "乳制品": ["牛奶", "奶油", "黄油", "芝士", "奶酪"], "香菜": ["香菜", "芫荽"]}
    observations = []
    blind_pairs = []
    blind_key = []
    excluded = []
    original_score = scoring_service.score_dishes
    candidate_runs = []
    model_calls = []
    original_complete = ai_client.complete_json
    def capture_model(*a, **kw):
        result = original_complete(*a, **kw)
        model_calls.append(dict(ok=result.ok, called=result.called, cached=result.cached,
                                elapsed_ms=result.elapsed_ms,
                                error=ai_client.failure_message(result) if not result.ok else None))
        return result
    def capture_candidates(*a, **kw):
        candidates = original_score(*a, **kw)
        candidate_runs.append([dict(id=x.item_id, name=x.name, score=x.score,
                                    reason=x.reason, factors=x.factors, insight=asdict(x.insight) if x.insight else None) for x in candidates])
        return candidates
    source_files = sorted((ROOT / "back" / "app").rglob("*.py"))
    source_hash = digest([(str(p.relative_to(ROOT)), hashlib.sha256(p.read_bytes()).hexdigest()) for p in source_files])
    meta = dict(date=args.date, repeats=args.repeats, scenario_count=len(cases), database_sha256=hashlib.sha256(database.read_bytes()).hexdigest(),
                code_sha256=source_hash, weather=asdict(weather), model=settings.ai_model,
                benchmark_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                real_ai_available=available, temperature=0, ai_call_limit=len(cases)*args.repeats,
                response_cache_seconds=0, failure_cooldown_seconds=settings.ai_failure_cooldown_seconds,
                safety_scope="详情配料词匹配，不证明医学安全或数据完整性", human_review="未开展")
    def save(name, value):
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    save("protocol.json", meta)
    rng = random.Random(20261012)
    with patch.object(ai_service, "datetime", FixedDateTime), patch.object(ai_service, "_weather_for", return_value=weather), patch.object(scoring_service, "score_dishes", side_effect=capture_candidates), patch.object(ai_client, 'complete_json', side_effect=capture_model):
        for number, (name, changes) in enumerate(cases, 1):
            payload = AiRecommendRequest(**{**common, **changes, **({"menu_recipe_ids": excluded} if number == 10 else {})})
            for repeat in range(1, args.repeats+1):
                paired = []
                # 交替请求顺序，避免所有AI请求只在后半段发生。
                order = [False, True] if repeat % 2 else [True, False]
                for enabled in order:
                    version = "规则＋AI" if enabled else "纯规则"
                    if enabled and not available:
                        row = dict(scenario=number, name=name, repeat=repeat, version=version, status="skipped", reason="未配置本地模型密钥或指定baseline-only", input=payload.model_dump())
                        observations.append(row)
                        continue
                    settings.ai_enabled = enabled
                    candidate_runs.clear()
                    model_calls.clear()
                    started = time.perf_counter()
                    with Session(engine) as session:
                        result = ai_service.recommend_recipes(session, None, payload).model_dump()
                        elapsed = round((time.perf_counter()-started)*1000, 1)
                        checks = []
                        for pick in result["recommendations"]:
                            r = pick["recipe"]
                            detail = recipe_service.get_detail(session, r["id"])
                            ingredients = [i.name for i in detail.ingredients] if detail else []
                            haystack = " ".join([r["name"], *ingredients])
                            hits = [word for word in payload.avoid if any(term in haystack for term in avoid_terms.get(word, [word]))]
                            checks.append(dict(id=r["id"], name=r["name"], ingredients=ingredients, avoid_hits=hits,
                                               valid=bool(detail and detail.name==r["name"]),
                                               duration_minutes=r["duration_minutes"], duration_unknown=r["duration_estimated"] or not r["duration_minutes"],
                                               duration_over=not r["duration_estimated"] and r["duration_minutes"]>payload.cook_minutes,
                                               repeated=r["id"] in payload.menu_recipe_ids,
                                               reason=pick["reason"], matched_foods=pick["matched_foods"]))
                    source = result["source"]
                    row = dict(scenario=number, name=name, repeat=repeat, version=version,
                               status="ok" if not enabled or source=="ai" else "fallback",
                               source=source, input=payload.model_dump(), response=result,
                               candidate_hash=digest(candidate_runs), candidates=[x["id"] for batch in candidate_runs for x in batch],
                               elapsed_ms=elapsed, checks=checks, model_calls=list(model_calls))
                    row["candidate_valid"] = all(p["id"] in row["candidates"] for p in checks)
                    observations.append(row)
                    paired.append(row)
                    print(f"{number:02d}/{len(cases)} 重复{repeat} {version}: {row['status']} {len(checks)}道", flush=True)
                    if number==1 and repeat==1 and not enabled:
                        excluded = [c["id"] for c in checks]
                if len(paired)==2:
                    valid = all(x["status"]=="ok" and x["candidate_valid"] for x in paired) and paired[0]["candidate_hash"]==paired[1]["candidate_hash"]
                    for row in paired:
                        row["valid_pair"] = valid
                    if valid:
                        shuffled = paired.copy(); rng.shuffle(shuffled)
                        key = f"S{number:02d}-R{repeat}"
                        blind_pairs.append(dict(pair_id=key, input=payload.model_dump(), A=[{k:c[k] for k in ("name","reason","ingredients")} for c in shuffled[0]["checks"]],
                                                B=[{k:c[k] for k in ("name","reason","ingredients")} for c in shuffled[1]["checks"]]))
                        blind_key.append(dict(pair_id=key,A=shuffled[0]["version"],B=shuffled[1]["version"]))
                save("observations.json", observations)
    save("blind-pairs.json", blind_pairs)
    save("blind-key.json", blind_key)
    # 人工评价每个独立场景只取第一次有效重复，不把重复模型调用当新增场景。
    review_pairs = [p for p in blind_pairs if p["pair_id"].endswith("-R1")]
    save("human-review-pairs.json", review_pairs)
    save("human-review-template.json", [dict(reviewer_id=f"P{person:02d}", pair_id=p["pair_id"],
         fit_A=None, fit_B=None, reason_A=None, reason_B=None, preference=None)
         for person in range(1,6) for p in review_pairs])
    rows = ["# 同环境推荐对照结果", "", f"日期：{args.date}。10组场景，各重复{args.repeats}次。", "",
            "| 版本 | 已执行 | 回退 | 未测 | 推荐记录 | 忌口命中 | 有依据超时 | 时长不详 | 无效菜谱 | 重复菜 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for version in ("纯规则", "规则＋AI"):
        group = [r for r in observations if r["version"]==version]
        executed = [r for r in group if "checks" in r]
        checks = [c for r in executed for c in r["checks"]]
        metrics = [len(checks),sum(bool(c["avoid_hits"]) for c in checks),sum(c["duration_over"] for c in checks),sum(c["duration_unknown"] for c in checks),sum(not c["valid"] for c in checks),sum(c["repeated"] for c in checks)] if executed else ["未测"]*6
        stats = [version,len(executed),sum(r["status"]=="fallback" for r in group),sum(r["status"]=="skipped" for r in group),*metrics]
        rows.append("| "+" | ".join(map(str,stats))+" |")
    valid_pairs = sum(r.get("valid_pair",False) for r in observations)//2
    rows += ["", f"有效同候选集配对：{valid_pairs}/{len(cases)*args.repeats}。", "",
             "输入、代码哈希、只读快照哈希、日期和天气已固定；没有有效配对的结果不能用于AI优劣判断。",
             "同一日期的重复请求不是新的独立场景。模型temperature=0也不能保证每次相同。",
             "时长不详不计为达标。低钠是模型/规则输入，但营养数据不完整，未作实际低钠效果证明。",
             "没有模拟真人评分。blind-pairs.json仅包含真实且候选一致的配对；blind-key.json仅给组织者，不给评分者。",
             "AI选菜和生成解释的耗时一起计入，和规则同在进程内测量；仍可能受模型网络服务波动影响。"]
    if not available:
        rows += ["", "本轮真实AI未测：本地模型密钥未配置。规则回退没有被计作AI，没有生成虚构盲评材料。"]
    (args.output / "结果汇总.md").write_text("\n".join(rows)+"\n", encoding="utf-8")
    if hashlib.sha256(database.read_bytes()).hexdigest() != meta["database_sha256"]:
        raise RuntimeError("数据库快照发生变化，本轮证据无效。")
    engine.dispose()
    print(f"保存到 {args.output}；有效配对 {valid_pairs}", flush=True)
    return 0 if available and valid_pairs==len(cases)*args.repeats else 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
