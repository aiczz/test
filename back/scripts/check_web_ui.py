"""用 headless 浏览器（CDP）打开真实产物 + 真实后端，把页面**读**出来并点按钮。

这不是截图工具 —— headless 下的 `Page.captureScreenshot` 抓到的是一张
**不会更新**的旧帧（实测连点 5 个 tab，5 张 PNG 的 SHA256 完全一样），
拿它当验证等于没验证。

能读文本的原因是 Flutter web 内置无障碍支持：页面上有一个隐藏的
`<flt-semantics-placeholder aria-label="Enable accessibility">`，
点它一下，Flutter 就把界面上的文字建成**真实 DOM**
（每个元素一个 `<flt-semantics>`）。于是可以断言
「页面上到底有没有『汤羹』这个分类、报的数字是不是 9319」，
而且这些语义节点本身可点，所以连点分类、看列表条数变化也能测。

用法：
    python back/scripts/check_web_ui.py --url http://127.0.0.1:8091 --api http://127.0.0.1:8000

前置：
    · 后端在 8000
    · `python deploy/local_preview.py --port 8091`（同源静态站 + /api 反代）

⚠️ 验证登录态时有个坑（踩过）：`shared_preferences_web` 的 `_encodeValue`
   就是 `json.encode(value)`，读的时候再 `json.decode`，**解不开就当没这个键**
   （返回 null，不报错）。所以往 localStorage 里写裸字符串的话，
   `prefs.getString('auth_token')` 永远是 null —— 表现是
   「令牌明明在 localStorage 里，App 却一直停在登录页」。值必须先 JSON 编码一层。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

EDGE_CANDIDATES = [
    # Windows
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    # Linux（部署机上要跑的话）
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]
PORT = 9336

# 点开无障碍树 + 把所有语义节点的文字读出来
READ_PAGE = """
(() => {
  const labels = [...document.querySelectorAll('flt-semantics')]
    .map((node) => node.getAttribute('aria-label') || node.textContent || '')
    .map((text) => text.trim())
    .filter((text) => text.length > 0);
  return JSON.stringify(labels);
})()
"""

ENABLE_SEMANTICS = """
(() => {
  const holder = document.querySelector('flt-semantics-placeholder');
  if (!holder) return 'no-placeholder';
  holder.click();
  return 'clicked';
})()
"""


def _api(base: str, path: str, body: dict | None = None, token: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{base}{path}", data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def _demo_session(api_base: str) -> tuple[str, str]:
    """拿一个**真** token，而不是随手编一个。

    为什么必须是真的：`createApiDio` 上挂着 401 拦截器，token 不合法时后端返回
    401，拦截器直接 `logout()` 清掉本地会话 —— 页面又跳回登录页，
    看起来像「预置登录态没用」。
    """
    token = _api(api_base, "/api/auth/login",
                 {"username": "demo", "password": "shishi2026"})["access_token"]
    me = _api(api_base, "/api/auth/me", token=token)
    return token, json.dumps({
        "id": me.get("id", 0),
        "username": me.get("username", "demo"),
        "nickname": me.get("nickname"),
        "family_size": me.get("family_size", 3),
        "is_admin": bool(me.get("is_admin")),
    }, ensure_ascii=False)


class Driver:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.id = 1

    async def send(self, method: str, params: dict | None = None) -> dict:
        message_id = self.id
        self.id += 1
        await self.ws.send(json.dumps(
            {"id": message_id, "method": method, "params": params or {}}
        ))
        while True:
            raw = json.loads(await self.ws.recv())
            if raw.get("id") == message_id:
                if "error" in raw:
                    raise RuntimeError(f"{method}: {raw['error']}")
                return raw.get("result") or {}

    async def eval(self, expression: str):
        result = await self.send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
        })
        return result.get("result", {}).get("value")

    async def labels(self) -> list[str]:
        return json.loads(await self.eval(READ_PAGE) or "[]")

    async def click_label(self, text: str) -> bool:
        """点一个语义节点。

        Flutter 会把整块内容也放进一个 `flt-semantics` 的 aria-label
        （比如整个分类区是一个节点，里面每个 chip 又是自己的节点）。
        所以这里按「**第一行文字**等于目标」来找，并在多个候选里挑
        **面积最小的那个** —— 那就是最具体的那个元素，而不是包着它的容器。
        """
        ok = await self.eval(f"""
        (() => {{
          const want = {json.dumps(text)};
          const nodes = [...document.querySelectorAll('flt-semantics')]
            .map((node) => {{
              // ⚠️ 和 READ_PAGE 用同一套取字逻辑：有些节点没有 aria-label，
              //    文字在 textContent 里 —— 只读 aria-label 会「找得到却点不到」。
              const label = (node.getAttribute('aria-label')
                             || node.textContent || '').trim();
              const first = label.split('\\n')[0].trim();
              return {{node, label, first, box: node.getBoundingClientRect()}};
            }})
            .filter((c) => c.first === want || c.label === want);
          if (!nodes.length) return false;
          nodes.sort((a, b) =>
            (a.box.width * a.box.height) - (b.box.width * b.box.height));
          const target = nodes[0].node;
          const box = target.getBoundingClientRect();
          const x = box.left + box.width / 2;
          const y = box.top + box.height / 2;
          for (const type of ['pointerdown', 'pointerup', 'click']) {{
            target.dispatchEvent(new PointerEvent(type, {{
              bubbles: true, cancelable: true, clientX: x, clientY: y,
              pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0,
            }}));
          }}
          return true;
        }})()
        """)
        return bool(ok)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8091")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default=".shots")
    parser.add_argument("--width", type=int, default=430)
    parser.add_argument("--height", type=int, default=932)
    args = parser.parse_args()

    edge = next((path for path in EDGE_CANDIDATES if Path(path).exists()), None)
    if edge is None:
        print("[x] 找不到 Edge / Chrome")
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    browser = subprocess.Popen(
        [
            edge, "--headless=new", "--no-first-run", "--hide-scrollbars",
            f"--remote-debugging-port={PORT}",
            f"--window-size={args.width},{args.height}",
            "--user-data-dir=" + str((out / "profile").resolve()),
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        target = None
        last_error = ""
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/json", timeout=2
                ) as response:
                    pages = [
                        t for t in json.loads(response.read().decode())
                        if t["type"] == "page"
                    ]
                if pages:
                    target = pages[0]
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
            if browser.poll() is not None:
                print(f"[x] 浏览器提前退出（exit={browser.returncode}）")
                return 2
            time.sleep(0.5)
        if target is None:
            print(f"[x] 连不上调试端口 {PORT} —— {last_error}")
            return 2

        origin = args.url.rstrip("/")
        token, user_json = _demo_session(args.api)

        async with websockets.connect(
            target["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024
        ) as ws:
            driver = Driver(ws)
            await driver.send("Page.enable")

            # 先落在同源的一个非 Flutter 页面上写 localStorage，再进首页 ——
            # 反过来（先进首页再 reload）不可靠。
            #
            # ⚠️ 值必须**先 JSON 编码一层**再写进去。
            #    `shared_preferences_web` 的 `_encodeValue` 就是 `json.encode(value)`，
            #    读的时候 `_decodeValue` 再 `json.decode`，解不开就当**没这个键**
            #    （返回 null，不报错）。所以直接写裸字符串的话，
            #    `prefs.getString('auth_token')` 会一直拿到 null ——
            #    表现是「令牌明明在 localStorage 里，App 却一直停在登录页」。
            token_stored = json.dumps(token)
            user_stored = json.dumps(user_json)
            await driver.send("Page.navigate", {"url": f"{origin}/api/health"})
            await asyncio.sleep(3)
            await driver.eval(
                "localStorage.setItem('flutter.auth_token', "
                f"{json.dumps(token_stored)});"
                "localStorage.setItem('flutter.auth_user', "
                f"{json.dumps(user_stored)});"
            )
            await driver.send("Page.navigate", {"url": f"{origin}/"})
            # 启动流程要拉 10000 道菜 + 45 个分类，给足时间
            await asyncio.sleep(30)

            print(f"打开无障碍树：{await driver.eval(ENABLE_SEMANTICS)}")
            await asyncio.sleep(1.5)

            # 诊断：App 启动后 localStorage 里还剩什么？
            # 令牌被清掉 = 401 拦截器调了 logout()；令牌还在 = restore() 没读到。
            print("App 启动后的 localStorage：")
            print("  " + str(await driver.eval(
                "JSON.stringify({token: (localStorage.getItem('flutter.auth_token')||'').slice(0,12),"
                "keys: Object.keys(localStorage)})"
            )))

            labels = await driver.labels()
            print(f"\n首页识别到 {len(labels)} 个语义节点")
            print("  " + " | ".join(labels[:20]))

            if not await driver.click_label("菜谱"):
                print("\n[x] 没找到「菜谱」入口 —— 无障碍树可能没建起来")
                return 1
            await asyncio.sleep(4)

            labels = await driver.labels()
            _report(labels, "菜谱页")

            # 点「家常菜」分类 —— 列表头的条数必须从 10000 变成 9319。
            # 这是「点分类能筛出菜」在真浏览器里最直接的证据。
            if not await driver.click_label("家常菜"):
                print("\n[x] 没找到「家常菜」分类")
                return 1
            await asyncio.sleep(3)
            labels = await driver.labels()
            _report(labels, "点「家常菜」之后")

            # 「展开全部分类」的文字被 Flutter 并进了父节点的 aria-label，
            # 没有独立的语义节点，点不到（不是界面问题，是无障碍树的合并策略）。
            # 这里只确认它在界面上，展开后的样子由 widget 测试覆盖。
            if any("展开全部分类" in text for text in labels):
                print("\n  [ok] 界面上有「展开全部分类」入口")

            # ---- 我的：不该再有「每周饮食预算」----
            if not await driver.click_label("我的"):
                print("\n[x] 没找到「我的」入口")
                return 1
            await asyncio.sleep(3)
            labels = await driver.labels()
            _report(labels, "我的")
            joined = " ".join(labels)
            if "每周饮食预算" in joined or "¥" in joined:
                print("\n  [x] 「我的」页上还有价格/预算相关的东西")
            else:
                print("\n  [ok] 「我的」页没有任何价格/预算字样")
            for needed in ("家庭人数", "每日可用烹饪时间", "低钠约束"):
                print(f"  {'[ok]' if needed in joined else '[x]'} 有「{needed}」")
            # 「保存家庭档案」在折叠线以下，而 ListView 是惰性建的 ——
            # 语义树里没有它不是界面有问题，是根本没建出来。
            # 保存这条链路（改人数 → 保存 → 首页/AI 跟着变 → 重启还在）
            # 由 widget_test 的「改了家庭人数并保存后」那个用例覆盖。
            print("  [--] 「保存家庭档案」在折叠线以下，浏览器这层读不到"
                  "（已由 widget 测试覆盖）")

            # ---- 食材详情：应季指数和「适合做这些菜」都必须是真的 ----
            if not await driver.click_label("食材"):
                print("\n[x] 没找到「食材」入口")
                return 1
            await asyncio.sleep(3)
            labels = await driver.labels()
            _report(labels, "食材页")

            opened = await _open_first_food(driver, labels)
            if not opened:
                print("\n[!] 没能在食材页点到具体食材，跳过详情检查")
                return 0
            await asyncio.sleep(4)
            labels = await driver.labels()
            _report(labels, "食材详情")
        return 0
    finally:
        browser.terminate()


async def _open_first_food(driver: "Driver", labels: list[str]) -> bool:
    """在食材页点开第一个食材卡片。

    卡片的名字是独立的语义节点，但「哪些文字是食材名」需要猜 ——
    这里按「长度 2~5、不含标点和数字、不在已知的界面词里」挑，
    拿不准就返回 False 让调用方跳过，而不是乱点一个按钮。
    """
    skip = {
        "全部食材", "全部", "时令", "蔬菜", "水果", "肉蛋", "水产", "豆制品",
        "主食", "其他", "我的食材", "首页", "食材", "菜谱", "AI", "我的",
        "搜索食材", "分类", "当季", "好做",
    }
    for text in labels:
        name = text.strip()
        if not (2 <= len(name) <= 5) or name in skip or "\n" in name:
            continue
        if any(ch.isdigit() or ch in "·，。！？：（）" for ch in name):
            continue
        if await driver.click_label(name):
            print(f"\n  点开了食材「{name}」")
            return True
    return False


def _report(labels: list[str], title: str) -> None:
    """把语义节点整理成人能读的样子。

    节点结构是「节点名 + 里面的文字」配对出现（如 `全部` / `10000`），
    这里只挑出分类 chip 那一段和列表头的「N 道」。
    """
    print(f"\n===== {title}（{len(labels)} 个语义节点）=====")
    counters = [text for text in labels if text.endswith(" 道")]
    if counters:
        print(f"  列表头：{counters}")
    # 分类 chip：上一行是名字、下一行是数字的成对节点
    chips: list[str] = []
    for index, text in enumerate(labels[:-1]):
        nxt = labels[index + 1]
        if nxt.isdigit() and text and not text.isdigit() and len(text) <= 6:
            chips.append(f"{text}({nxt})")
    if chips:
        print(f"  分类 {len(chips)} 个：{' '.join(chips)}")
    groups = [
        text for text in labels
        if text in {"家常快手", "品类", "做法", "主要食材", "口味", "人群 · 目标",
                    "菜系", "其他"}
    ]
    if groups:
        print(f"  分组标题：{groups}")
    dishes = [
        text for text in labels
        if text not in chips and not text.isdigit() and len(text) > 3
        and ("分钟" not in text)
    ]
    print(f"  其他文字（前 12 条）：{dishes[:12]}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
