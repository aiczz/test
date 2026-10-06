#!/usr/bin/env python3
"""本地预览：在一台机器上复刻【生产拓扑】。

生产上是 nginx 干两件事（见 deploy/nginx-shishi.conf）：
    浏览器 ─┬─ /      → 前端静态产物
            └─ /api/  → 后端 uvicorn

这个脚本用 Python 标准库做同样的事，好处是**本地就能验证「同源」这条路**：
前端产物里没有写死任何 IP，它调的是「页面所在来源」的 /api。
不这么验证的话，同源逻辑只能等上线才知道对不对。

用法：
    # 终端 1：后端
    cd back && python -m uvicorn app.main:app --port 8000

    # 终端 2：前端产物 + 反代（默认 8080）
    python deploy/local_preview.py

    # 然后浏览器打开 http://127.0.0.1:8080/ —— 页面上所有 /api 请求
    # 都会被这个脚本转给后端，和线上 nginx 的行为一致。

    # 后端不在默认端口时：
    python deploy/local_preview.py --port 8080 --api http://127.0.0.1:8020
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEB = ROOT / "front" / "mealmind" / "build" / "web"


class Handler(http.server.SimpleHTTPRequestHandler):
    """静态文件 + /api 反代。"""

    api_base = "http://127.0.0.1:8000"

    # ---- 反代 ----
    def _proxy(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        target = self.api_base.rstrip("/") + self.path
        request = urllib.request.Request(target, data=body, method=method)
        # 原样转发客户端头（Authorization / Content-Type / Accept 都要）
        for key, value in self.headers.items():
            if key.lower() in {"host", "content-length", "connection"}:
                continue
            request.add_header(key, value)

        try:
            # ★ 超时放到 120s：首页首次生成当天推荐时会真的等一次大模型
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
                status = response.status
                headers = response.headers
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            status = exc.code
            headers = exc.headers
        except Exception as exc:  # noqa: BLE001
            self.send_error(502, f"后端连不上（{self.api_base}）：{exc}")
            return

        self.send_response(status)
        for key, value in headers.items():
            if key.lower() in {"transfer-encoding", "connection", "content-length"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy("GET")
        else:
            super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy("HEAD")
        else:
            super().do_HEAD()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy("POST")
        else:
            self.send_error(405)

    def do_PUT(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy("PUT")
        else:
            self.send_error(405)

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy("DELETE")
        else:
            self.send_error(405)

    # 单页应用：找不到的路径回 index.html（和 nginx 的 try_files 一致）
    def send_head(self):
        try:
            return super().send_head()
        except Exception:  # noqa: BLE001
            self.path = "/index.html"
            return super().send_head()

    def log_message(self, fmt: str, *args) -> None:
        # 只打 /api，静态资源太吵
        if self.path.startswith("/api/"):
            sys.stderr.write("  [api] %s\n" % (fmt % args))


def main() -> int:
    parser = argparse.ArgumentParser(description="本地预览（静态站 + /api 反代）")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--api", default="http://127.0.0.1:8000",
                        help="后端地址，例如 http://127.0.0.1:8020")
    parser.add_argument("--web", default=str(DEFAULT_WEB),
                        help="前端产物目录（flutter build web 的输出）")
    args = parser.parse_args()

    web_dir = Path(args.web)
    if not (web_dir / "index.html").exists():
        print(f"[x] {web_dir} 里没有 index.html —— 先跑：")
        print("    cd front/mealmind && flutter build web --release")
        return 2

    Handler.api_base = args.api
    handler = functools.partial(Handler, directory=str(web_dir))

    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"前端: http://127.0.0.1:{args.port}/   （{web_dir}）")
        print(f"后端: {args.api}  （/api/* 会被转发到这里）")
        print("Ctrl+C 停止")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
