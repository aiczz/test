"""将同环境原始记录整理为可审查的Markdown结果表，不生成主观用户评分。"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import statistics


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    args = p.parse_args()
    folder = args.directory.resolve()
    raw = json.loads((folder / "observations.json").read_text(encoding="utf-8"))
    protocol = json.loads((folder / "protocol.json").read_text(encoding="utf-8"))
    expected = protocol["scenario_count"] * protocol["repeats"]
    pairs = {}
    for row in raw:
        pairs.setdefault((row["scenario"], row["repeat"]), {})[row["version"]] = row
    valid = {key: rows for key, rows in pairs.items()
             if set(rows) == {"纯规则", "规则＋AI"} and all(r.get("valid_pair", False) for r in rows.values())}
    executed = {v: [rows[v] for rows in valid.values()] for v in ("纯规则", "规则＋AI")}
    checks = {v: [c for row in rows for c in row["checks"]] for v, rows in executed.items()}
    stats = {}
    for version, rows in executed.items():
        c = checks[version]
        times = sorted(r["elapsed_ms"] for r in rows)
        stats[version] = dict(requests=len(rows), recipes=len(c),
            avoid_hits=sum(bool(x["avoid_hits"]) for x in c), time_over=sum(x["duration_over"] for x in c),
            time_known_ok=sum(not x["duration_unknown"] and not x["duration_over"] for x in c),
            time_unknown=sum(x["duration_unknown"] for x in c), invalid=sum(not x["valid"] for x in c),
            repeated=sum(x["repeated"] for x in c), inventory_matches=sum(len(x["matched_foods"]) for r in rows if r["scenario"] == 9 for x in r["checks"]),
            median_ms=round(statistics.median(times),1) if times else None,
            p95_ms=times[math.ceil(len(times)*.95)-1] if times else None)
    same_sets = sum({c["id"] for c in r["纯规则"]["checks"]} == {c["id"] for c in r["规则＋AI"]["checks"]} for r in valid.values())
    consistent = {}
    for version, rows in executed.items():
        grouped = {}
        for row in rows:
            grouped.setdefault(row["scenario"], []).append(tuple(c["id"] for c in row["checks"]))
        consistent[version] = sum(len(values) == protocol["repeats"] and len(set(values)) == 1 for values in grouped.values())
    models = sorted({r["response"].get("model") for r in executed["规则＋AI"] if r["response"].get("model")})
    def table(headers, records):
        return ["| " + " | ".join(map(str,headers)) + " |", "|"+"---|"*len(headers),
                *["| " + " | ".join(map(str,row)) + " |" for row in records]]
    metrics = [("有效配对请求数", "requests"),("推荐记录数", "recipes"),("完整配料忌口命中数", "avoid_hits"),
               ("有依据且超时", "time_over"),("有依据且符合时间", "time_known_ok"),("时长估计／不详", "time_unknown"),
               ("不存在或名称不符的菜", "invalid"),("重复已选菜", "repeated"),("已有食材场景匹配次数", "inventory_matches"),
               ("请求耗时中位数（ms）", "median_ms"),("请求耗时P95（ms）", "p95_ms")]
    text = ["# 食时真实AI同环境对照报告", "", f"日期：{protocol['date']}；{protocol['scenario_count']}组场景，每组重复{protocol['repeats']}次。",
            f"有效同输入、同候选配对：{len(valid)}/{expected}。实际响应模型：{'、'.join(models) or '未调用成功'}。", "", "## 汇总", ""]
    text += table(["指标", "纯规则", "规则＋AI"], [[label, stats["纯规则"][key], stats["规则＋AI"][key]] for label,key in metrics])
    text += ["", f"两版菜品集合相同：{same_sets}/{len(valid)}组有效配对。重复请求菜品及顺序完全一致的场景：规则{consistent['纯规则']}/10，AI{consistent['规则＋AI']}/10。", "",
             "食材匹配次数是逐菜的匹配数之和，不是不同食材总数。P95采用最近秩分位法。重复请求是稳定性观测，不是新的独立场景。", "", "## 场景明细", ""]
    detail = []
    for row in raw:
        c = row.get("checks", [])
        detail.append([row["scenario"], row["name"], row["repeat"], row["version"], row["status"], "是" if row.get("valid_pair") else "否",
                       "；".join(x["name"] for x in c), sum(bool(x["avoid_hits"]) for x in c), sum(x["duration_unknown"] for x in c), row.get("elapsed_ms", "未测")])
    text += table(["编号", "场景", "重复", "版本", "状态", "有效配对", "菜品", "忌口命中", "时长不详", "耗时ms"], detail)
    base, ai = stats["纯规则"], stats["规则＋AI"]
    text += ["", "## 可支持的结论", ""]
    if len(valid) == expected:
        text.append("本轮实现了同一代码、同一只读数据库、同一日期与天气、同一候选集的开关对照，避免了前次跨环境差异。")
    else:
        text.append("本轮没有完成全部有效配对；失败与回退保留在原始记录中，不能作为已完成AI对比。")
    if len(valid):
        text.append(f"两版完整配料忌口命中分别为{base['avoid_hits']}和{ai['avoid_hits']}，有依据超时分别为{base['time_over']}和{ai['time_over']}。这是限定场景的数据检查，不代表医学安全。")
        text.append(f"时长不详记录从规则的{base['time_unknown']}条变为AI的{ai['time_unknown']}条；仅能说明本轮所选菜谱的时长信息完整性差异，不证明实际烹饪更快。")
        text.append(f"已有食材场景匹配次数为规则{base['inventory_matches']}、AI{ai['inventory_matches']}。不能推广到其他库存或其他用户。")
        text.append(f"AI请求中位耗时{ai['median_ms']}ms，规则为{base['median_ms']}ms；模型外部服务和网络延迟包含在AI侧。")
    text += ["", "## 尚不能声称", "", "没有真人盲评，不能声称AI更合口味、更好吃、解释更清楚或用户满意度更高。",
             "营养估计可能漏计调味料，本轮不证明实际低钠或营养改善。10个场景、3次重复不支持总体优势或统计显著结论。",
             "模型生成解释属于实际功能，但解释质量需要独立评审，不能把描述更长等同于更好。", "", "## 原始证据与盲评", "",
             "protocol.json记录源码与数据库哈希、日期、天气、温度参数；observations.json保留每次输入、来源、候选哈希、菜品配料和返回。",
             "human-review-pairs.json是每个场景第一次有效重复的随机A/B盲评材料；human-review-template.json的评分为null，表示未开展。",
             "blind-key.json仅给组织者，不交给评分者。旧报告保留，服务器没有部署本地修复。"]
    (folder / "真实AI对照报告.md").write_text("\n".join(text)+"\n",encoding="utf-8")
    summary = dict(valid_pairs=len(valid), expected_pairs=expected, same_recipe_sets=same_sets, consistency=consistent, models=models, metrics=stats,
                   human_evaluation="未开展")
    (folder / "analysis.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
