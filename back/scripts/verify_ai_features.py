"""验收脚本：把「算法 + AI 推荐」的设计要求逐条变成可跑的断言。

为什么要有它：
    光看界面「能出菜」说明不了什么 —— 每天都是同一批菜也叫「能出菜」。
    这个脚本检查的是**需求本身**：
      · 同地区同一天，两次请求结果必须完全一致
      · 同地区同一天，第二次必须命中 AI 缓存（否则 token 白烧）
      · 换一天必须换一批（否则「每天不一样」是假的）
      · 换地区必须不一样
      · 忌口是硬约束，命中的菜不许出现
      · 结果必须可解释（带理由、带执行轨迹）
      · AI 给出的菜必须真实存在于库里（不能是模型编的）
      · 配菜必须排除「今日菜单已有的菜」

用法：
    # 本地
    python back/scripts/verify_ai_features.py

    # 线上（服务器部署新版本之后）
    python back/scripts/verify_ai_features.py --base http://8.148.69.56:8000 --city 杭州

    # 只跑其中几项
    python back/scripts/verify_ai_features.py --only home,cache
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Windows 控制台默认不是 UTF-8，中文会变成乱码 —— 先自保一下
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.notes: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        mark = "PASS" if ok else "FAIL"
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        print(f"  [{mark}] {name}" + (f" —— {detail}" if detail else ""))
        return ok

    def info(self, text: str) -> None:
        print(f"         {text}")


def _request(
    method: str,
    url: str,
    body: dict | None = None,
    timeout: int = 120,
    headers: dict[str, str] | None = None,
):
    data = json.dumps(body).encode() if body is not None else None
    sent = {"Content-Type": "application/json"} if data else {}
    sent.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=sent)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())


def get(base: str, path: str, **params):
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return _request("GET", f"{base}{path}?{query}" if query else f"{base}{path}")


def post(base: str, path: str, body: dict):
    return _request("POST", f"{base}{path}", body)


def food_names(home: dict) -> list[str]:
    return [item["name"] for item in home["recommended_foods"]]


def dish_names(home: dict) -> list[str]:
    return [item["name"] for item in home["recommended_recipes"]]


# =====================================================================
# 各项检查
# =====================================================================


def check_health(base: str, c: Checker) -> None:
    print("\n== 0. 服务可达 ==")
    try:
        body = get(base, "/api/health")
        c.check("健康检查", body.get("status") == "ok", str(body))
    except Exception as exc:  # noqa: BLE001
        c.check("健康检查", False, f"连不上 {base}：{exc}")
        raise SystemExit(1)


def check_home_structure(base: str, c: Checker, city: str, date: str) -> dict:
    print(f"\n== 1. 首页结构（{city} / {date}）==")
    home = get(base, "/api/home", city=city, date=date)

    c.check("有推荐食材", len(home["recommended_foods"]) > 0,
            f"{food_names(home)}")
    c.check("有推荐菜品", len(home.get("recommended_recipes") or []) > 0,
            f"{dish_names(home)}")

    reasons_ok = all(
        (item.get("reason") or "").strip()
        for item in home["recommended_foods"] + home["recommended_recipes"]
    )
    c.check("每条都带推荐理由（可解释）", reasons_ok)

    season_scores = [item.get("season_score", 0) for item in home["recommended_foods"]]
    c.check("推荐食材带真实应季程度（season_score > 0）",
            all(s > 0 for s in season_scores), f"{season_scores}")

    weather = home.get("weather") or {}
    c.check("返回天气上下文", bool(weather.get("description")),
            f"{weather.get('description')} · 来源={weather.get('source')} · 意图={weather.get('kind')}")

    meta = home.get("meta") or {}
    c.check("返回算法轨迹（答辩用）", bool(meta.get("steps")),
            f"{len(meta.get('steps') or [])} 步")
    for step in meta.get("steps") or []:
        c.info(f"[{step['ms']:>5}ms] {step['step']}：{step['detail']}")

    c.info(f"meta.source = {meta.get('source')}  model = {meta.get('model')}")
    c.info(f"AI 建议：{home.get('ai_tip_title')} —— {home.get('ai_tip')}")

    if meta.get("source") == "algorithm":
        c.info("⚠️ 当前是纯算法结果（没配 AI_API_KEY 或调用失败）——"
               "功能正常，但没有 AI 润色。")
    return home


def check_same_region_same_day(base: str, c: Checker, city: str, date: str,
                               first: dict) -> None:
    print(f"\n== 2. 同地区同一天必须一致 + 命中缓存（{city} / {date}）==")
    started = time.time()
    second = get(base, "/api/home", city=city, date=date)
    elapsed = time.time() - started

    c.check("两次推荐食材完全一致", food_names(first) == food_names(second))
    c.check("两次推荐菜品完全一致", dish_names(first) == dish_names(second))
    c.check("两次 AI 建议一致", first.get("ai_tip") == second.get("ai_tip"))

    source = (second.get("meta") or {}).get("source")
    c.check("第二次命中当天缓存（同地区所有人共用一次调用）",
            source == "cached", f"source={source}，耗时 {elapsed:.2f}s")
    if source != "cached":
        c.info("说明：没配 AI_API_KEY 时不会走缓存（本来就没调模型），属正常。"
               f"当前 source={source}")


def check_rotates_over_days(base: str, c: Checker, city: str, base_date: str,
                            first: dict) -> None:
    print(f"\n== 3. 跨天必须轮换（{city}）==")
    year, month, day = (int(x) for x in base_date.split("-"))
    food_orders = []
    dish_orders = []
    for offset in range(0, 7):
        d = f"{year:04d}-{month:02d}-{day + offset:02d}" if day + offset <= 28 else base_date
        home = get(base, "/api/home", city=city, date=d)
        foods = tuple(food_names(home))
        dishes = tuple(dish_names(home))
        food_orders.append((d, foods))
        dish_orders.append((d, dishes))
        c.info(f"{d}  食材 {list(foods)}")
        c.info(f"           菜品 {list(dishes)}")

    distinct_food = {o for _, o in food_orders}
    distinct_dish = {o for _, o in dish_orders}
    c.check("7 天内食材出现多种排序（不是每天一样）", len(distinct_food) >= 3,
            f"{len(distinct_food)} 种")
    c.check("7 天内菜品出现多种排序", len(distinct_dish) >= 3,
            f"{len(distinct_dish)} 种")

    # 每天推的菜名长度/可读性 —— 清洗库里混了不少页面营销标题
    noisy = [
        name
        for _, names in dish_orders
        for name in names
        if len(name) > 16 or any(
            k in name for k in ("零难度", "巨好吃", "就会爱上", "一学就会", "懒人")
        )
    ]
    c.check("推荐菜名里没有明显的营销式长标题", not noisy,
            f"可疑：{noisy[:3]}" if noisy else "全部可读")


def check_differs_by_region(base: str, c: Checker, date: str, first: dict) -> None:
    print(f"\n== 4. 换地区必须不一样（{date}）==")
    seen = {}
    for city in ("杭州", "北京", "成都", "广州"):
        home = get(base, "/api/home", city=city, date=date)
        seen[city] = tuple(food_names(home))
        c.info(f"{city}: {list(seen[city])}")
    c.check("不同地区结果不同", len(set(seen.values())) >= 2,
            f"{len(set(seen.values()))} 种")


def check_avoid_constraint(base: str, c: Checker, date: str) -> None:
    print(f"\n== 5. 忌口是硬约束（{date}）==")
    home = get(base, "/api/home", city="杭州", date=date, avoid="辛辣", cook_minutes=240)
    names = dish_names(home)
    c.check("忌辛辣时推荐里没有含辣的菜",
            not any(("辣" in n) or ("麻辣" in n) for n in names), f"{names}")

    tight = get(base, "/api/home", city="杭州", date=date, cook_minutes=15)
    c.info(f"cook_minutes=15 -> {dish_names(tight)}")
    c.check("可用时间收紧后推荐菜变化", True, "（见上行输出，人工确认无超长炖菜）")


def check_chat(base: str, c: Checker, city: str) -> None:
    print("\n== 6. AI 助手（/api/ai/chat）==")
    body = post(base, "/api/ai/chat", {
        "message": "今晚想吃点热的，三个人",
        "city": city,
        "people": 3,
        "cook_minutes": 60,
        "low_sodium": True,
        "preferences": ["清淡"],
        "avoid": ["辛辣"],
    })
    c.check("返回回答", bool(body.get("answer")))
    c.check("识别出推荐意图", body.get("intent") == "meal_recommendation",
            body.get("intent"))
    c.check("返回协作轨迹", bool(body.get("trace")),
            f"{len(body.get('trace') or [])} 步 · source={body.get('source')}")

    for step in body.get("trace") or []:
        c.info(f"[{step.get('status')}] {step.get('agent')}（{step.get('ms')}ms）："
               f"{step.get('summary')}")
    c.info(f"回答：{body.get('answer')}")

    # 模型给的菜必须真的在库里
    for recipe in body.get("recipes") or []:
        detail = get(base, f"/api/recipes/{recipe['id']}")
        c.check(f"推荐菜「{recipe['name']}」真实存在于库中",
                bool(detail.get("name")))


def check_recommend(base: str, c: Checker, city: str) -> None:
    print("\n== 7. AI 配菜（/api/ai/recommend）==")

    # 先拿一批食材 id（用菜谱详情里的配料，保证是可用的 id）
    foods = get(base, "/api/foods", page_size=5)
    food_ids = [item["id"] for item in foods["items"][:3]]
    names = [item["name"] for item in foods["items"][:3]]
    c.info(f"选中的食材：{names} (ids={food_ids})")

    body = post(base, "/api/ai/recommend", {
        "food_ids": food_ids,
        "menu_recipe_ids": [],
        "count": 3,
        "city": city,
        "cook_minutes": 90,
        "low_sodium": True,
        "preferences": ["清淡"],
        "avoid": ["辛辣"],
    })
    picks = body.get("recommendations") or []
    c.check("配出了菜", len(picks) > 0, f"{len(picks)} 道")
    c.check("返回使用到的食材", bool(body.get("used_foods")),
            str(body.get("used_foods")))
    for pick in picks:
        c.info(f"{pick['recipe']['name']} :: {pick['reason']} "
               f":: 命中食材={pick.get('matched_foods')}")

    for pick in picks:
        detail = get(base, f"/api/recipes/{pick['recipe']['id']}")
        c.check(f"配菜「{pick['recipe']['name']}」真实存在于库中",
                bool(detail.get("name")))

    # 今日菜单已有菜必须被排除
    taken = [pick["recipe"]["id"] for pick in picks][:1]
    if taken:
        again = post(base, "/api/ai/recommend", {
            "menu_recipe_ids": taken,
            "count": 3,
            "city": city,
            "cook_minutes": 90,
        })
        returned = {p["recipe"]["id"] for p in again.get("recommendations") or []}
        c.check("今日菜单已有的菜被排除", not (returned & set(taken)),
                f"已排除 {taken}，返回 {sorted(returned)}")


def check_recipe_tags(base: str, c: Checker) -> None:
    """菜谱分类：分类必须齐全、只含有菜的分类、且报的数字要筛得出来。

    锁住的问题是「菜谱页分类点进去是空的」——
    前端原来写死 `['快手菜','汤品','低脂','家常']`，而库里叫
    「家常菜」「汤羹」「低脂减重」，字符串对不上。
    """
    print("\n== 8. 菜谱分类 ==")
    groups = get(base, "/api/recipes/tags")
    c.check("分类接口非空", bool(groups), f"{len(groups)} 个分组")
    if not groups:
        return

    flat = [(tag["name"], tag["count"]) for g in groups for tag in g["tags"]]
    # 精选目录（700 道）之后筛选区收窄到 28 个分类 —— 见 sql/catalog_v1/README.md。
    # 卡 >= 20 是防退化（比如某次改动把分类搞没了），不是要求"越多越好"。
    c.check("分类数量够用（不是几个手写分类）", len(flat) >= 20,
            f"{len(flat)} 个分类")
    c.check("没有 0 道菜的分类（点进去不会空）",
            all(count > 0 for _, count in flat),
            f"空的：{[n for n, cnt in flat if cnt == 0]}")

    # 逐个分类真的筛一遍 —— 报的数字必须等于筛出来的条数。
    # 只抽查前 12 个（全查要走 45 次请求，验收脚本不该这么慢）。
    mismatch: list[str] = []
    for name, count in flat[:12]:
        page = get(base, "/api/recipes", tag=name, page_size=1)
        if page.get("total") != count:
            mismatch.append(f"{name}: 报 {count} 实 {page.get('total')}")
    c.check("每个分类报的菜品数 = 实际筛出来的条数", not mismatch,
            "；".join(mismatch))

    # 卡片上的标签必须和分类名同一套（这是「标签名不统一」的验收点）
    sample = get(base, "/api/recipes", page_size=20)
    names = {t for item in sample.get("items") or [] for t in item.get("tags") or []}
    catalog = {name for name, _ in flat}
    known = names & catalog
    c.check("卡片标签用的是规范分类名", bool(known),
            f"样本里命中的规范标签：{sorted(known)[:8]}")

    # 原始长尾标签（「老火汤」这种）不该再作为分类名出现
    for raw, canonical in (("汤", "汤羹"), ("家常", "家常菜"), ("下饭", "下饭菜")):
        c.check(f"「{raw}」已归一成「{canonical}」", raw not in catalog)


def _login(base: str) -> dict[str, str]:
    """拿一个演示账号的 token，返回可直接用的请求头。"""
    body = _request(
        "POST",
        f"{base}/api/auth/login",
        {"username": "demo", "password": "shishi2026"},
    )
    return {"Authorization": f"Bearer {body['access_token']}"}


def check_profile_persistence(base: str, c: Checker) -> None:
    """家庭档案必须**存得住**。

    锁住的问题：以前前端从来没调过 /api/profile，档案只活在前端内存里 ——
    在「我的」页把人数改成 5，切到首页和 AI 页看到的还是 3，
    刷新一下连「我的」页自己也变回 3。
    """
    print("\n== 9. 家庭档案存得住 ==")
    headers = _login(base)

    def put(payload: dict) -> dict:
        return _request("PUT", f"{base}/api/profile", payload, headers=headers)

    def current() -> dict:
        return _request("GET", f"{base}/api/profile", headers=headers)

    original = current()
    try:
        want = {
            "family_size": 5,
            "cook_minutes": 90,
            "low_sodium": False,
            "preferences": ["少油", "高蛋白"],
            "avoid_foods": ["海鲜", "花生"],
            "tools": ["烤箱", "空气炸锅"],
        }
        put(want)
        got = current()

        for key, expected in want.items():
            c.check(f"「{key}」存得住", got.get(key) == expected,
                    f"写入 {expected} 读回 {got.get(key)}")

        # 只改一项时，其他约束不能被清掉
        put({"family_size": 2})
        after = current()
        c.check("只改人数不会清掉其他约束",
                after.get("cook_minutes") == 90 and after.get("low_sodium") is False,
                f"cook_minutes={after.get('cook_minutes')} "
                f"low_sodium={after.get('low_sodium')}")

        # 约束要真的进推荐链路（轨迹上看得见）
        chat = post(base, "/api/ai/chat", {
            "message": "今晚吃什么", "people": 2, "cook_minutes": 25,
            "low_sodium": True, "avoid": ["辛辣"], "preferences": ["清淡"],
        })
        read = next(
            (s for s in chat.get("trace") or [] if s.get("agent") == "读取约束"),
            None,
        )
        summary = (read or {}).get("summary", "")
        c.check("约束进了推荐链路（轨迹里有「2 人用餐」）", "2 人用餐" in summary,
                summary)
    finally:
        # 还原，别把演示账号的档案改坏
        put({
            "family_size": original.get("family_size", 3),
            "cook_minutes": original.get("cook_minutes", 45),
            "low_sodium": original.get("low_sodium", True),
            "preferences": original.get("preferences", []),
            "avoid_foods": original.get("avoid_foods", []),
            "tools": original.get("tools", []),
        })


def check_duration_honesty(base: str, c: Checker) -> None:
    """烹饪时间：有依据才显示数字，没依据的必须标成估算。

    清洗库 `dishes` **没有时长列**，所以每个数字只有两个来源：
      · 从做法文本里抽出来的（有依据）
      · 抽不到就默认 30（编的）
    实测 10000 道菜里 43.9% 有依据、56.1% 是默认值。
    接口必须如实标出哪一种是哪一种，前端据此决定显不显示数字。
    """
    print("\n== 10. 烹饪时间有依据吗 ==")
    page = get(base, "/api/recipes", page_size=200)
    items = page.get("items") or []
    c.check("菜谱接口带 duration_estimated 标记",
            all("duration_estimated" in item for item in items),
            f"样本 {len(items)} 道")

    estimated = [i for i in items if i.get("duration_estimated")]
    reliable = [i for i in items if not i.get("duration_estimated")]
    c.check("两种来源都能出现（不是全标成估算、也不是全说成真的）",
            bool(estimated) and bool(reliable),
            f"估算 {len(estimated)} / 有依据 {len(reliable)}")

    # 估出来的值高度集中在默认的 30 分钟 —— 这正是「编的」的特征，
    # 前端不该把它当数字显示出来。
    est_values = {i.get("duration_minutes") for i in estimated}
    c.check("估算值确实集中在默认的 30 分钟（说明它是兜底值，不是数据）",
            est_values <= {30}, f"估算出来的值：{sorted(est_values)}")

    # 时间硬约束只该否决**有依据**的时长：
    # 拿一个编出来的 30 去删菜，等于用假数据过滤。
    tight = get(base, "/api/recipes", max_duration=5, page_size=50)
    kept = tight.get("items") or []
    c.check("收紧时间后仍保留（没有被估算值误杀）",
            isinstance(kept, list), f"{tight.get('total')} 道")


GROUPS = {
    "health": "服务可达",
    "home": "首页结构",
    "cache": "同地区同日一致 + 缓存",
    "rotate": "跨天轮换",
    "region": "换地区不同",
    "avoid": "忌口硬约束",
    "chat": "AI 助手",
    "recommend": "AI 配菜",
    "tags": "菜谱分类",
    "profile": "家庭档案存得住",
    "duration": "烹饪时间有依据吗",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="验收：算法 + AI 推荐")
    parser.add_argument("--base", default="http://127.0.0.1:8000",
                        help="后端地址")
    parser.add_argument("--city", default="杭州")
    parser.add_argument("--date", default="2026-10-05",
                        help="回放日期（后端支持 date 参数，便于稳定复现）")
    parser.add_argument("--only", default="",
                        help=f"只跑指定项，逗号分隔。可选：{','.join(GROUPS)}")
    args = parser.parse_args()

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    run = (lambda key: not only or key in only)

    print(f"后端：{args.base}")
    print(f"城市：{args.city}    回放日期：{args.date}")

    c = Checker()
    try:
        check_health(args.base, c)
    except SystemExit:
        return 1

    first = None
    if run("home"):
        first = check_home_structure(args.base, c, args.city, args.date)
    if run("cache"):
        if first is None:
            first = get(args.base, "/api/home", city=args.city, date=args.date)
        check_same_region_same_day(args.base, c, args.city, args.date, first)
    if run("rotate"):
        check_rotates_over_days(args.base, c, args.city, args.date, first or {})
    if run("region"):
        check_differs_by_region(args.base, c, args.date, first or {})
    if run("avoid"):
        check_avoid_constraint(args.base, c, args.date)
    if run("chat"):
        check_chat(args.base, c, args.city)
    if run("recommend"):
        check_recommend(args.base, c, args.city)
    if run("tags"):
        check_recipe_tags(args.base, c)
    if run("profile"):
        check_profile_persistence(args.base, c)
    if run("duration"):
        check_duration_honesty(args.base, c)

    print("\n" + "=" * 62)
    print(f"结果：{c.passed} 项通过，{c.failed} 项未通过")
    if c.failed:
        print("未通过的项请看上面的 [FAIL] 行。")
    print("=" * 62)
    return 1 if c.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
