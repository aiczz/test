#!/usr/bin/env python3
"""本地预览：在一台机器上复刻【生产拓扑】。

生产上是 nginx 干两件事（见 deploy/nginx-shishi.conf）：
    浏览器 ─┬─ /      → 前端静态产物
            └─ /api/  → 后端 uvicorn

这个脚本用 Python 标准库做同样的事，好处是**本地就能验证「同源」这条路**：
前端产物里没有写死任何 IP，它调的是「页面所在来源」的 /api。
不这么验证的话，同源逻辑只能等上线才知道对不对。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【端口约定】对外只有一个：8091。记住这一个就够了。

    浏览器  →  127.0.0.1:8091   ← 你只需要记这个
                   │
                   └─ /api/*  → 127.0.0.1:8000（后端，**只绑本机**，不是给你手动开的）

8000 存在是拓扑的要求（线上是 nginx:80 → uvicorn:8000），不是你多开了一个服务。
它只监听 127.0.0.1，局域网里别人访问不到，你也不用直接开它。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

用法：
    # ★ 推荐：一条命令把后端和静态站都起来（Ctrl+C 一起停，不留孤儿进程）
    python deploy/local_preview.py --port 8091 --start-backend

    # 然后浏览器开 http://127.0.0.1:8091/

    # 后端你自己已经在别处跑着（比如调试时想单独看 uvicorn 的日志）：
    python deploy/local_preview.py --port 8091

    # 后端在别的端口：
    python deploy/local_preview.py --port 8091 --api http://127.0.0.1:8020

⚠️ 换构建产物之后**不用换端口**：同一个地址按 Ctrl+Shift+R 强制刷新就行。
   以前换端口是为了绕浏览器的 service worker 缓存，代价是每换一次
   就多一个「这个端口到底还活着吗」的心智负担 —— 不划算。
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEB = ROOT / "front" / "mealmind" / "build" / "web"
BACKEND_DIR = ROOT / "back"


def _spawn_backend(port: int) -> subprocess.Popen:
    """把后端拉起来（和线上 `shishi-backend.service` 跑的是同一个命令）。

    输出直接继承到当前终端 —— 调试时最想看的就是 uvicorn 的报错，
    重定向到文件反而要多开一个窗口去 tail。
    """
    return subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "warning",
        ],
        cwd=str(BACKEND_DIR),
    )


def _wait_backend(port: int, timeout: float = 40.0) -> bool:
    """等后端真的能应答再开始服务静态页。

    不等的话，先刷出来的首页会因为 /api 502 而显示「本地演示数据」，
    看着像后端坏了，其实只是慢了两秒。
    """
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False



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
    parser.add_argument("--port", type=int, default=8091,
                        help="对外唯一的端口，记这个就行（默认 8091）")
    parser.add_argument("--api", default="http://127.0.0.1:8000",
                        help="后端地址，例如 http://127.0.0.1:8020")
    parser.add_argument("--web", default=str(DEFAULT_WEB),
                        help="前端产物目录（flutter build web 的输出）")
    parser.add_argument("--start-backend", action="store_true",
                        help="顺手把后端也起来（一条命令搞定，Ctrl+C 一起停）")
    args = parser.parse_args()

    web_dir = Path(args.web)
    if not (web_dir / "index.html").exists():
        print(f"[x] {web_dir} 里没有 index.html —— 先跑：")
        print("    cd front/mealmind && flutter build web --release")
        return 2

    backend: subprocess.Popen | None = None
    if args.start_backend:
        backend_port = urllib.parse.urlsplit(args.api).port or 80
        print(f"启动后端：uvicorn app.main:app --port {backend_port}")
        backend = _spawn_backend(backend_port)
        if not _wait_backend(backend_port):
            print(f"[x] 后端 {backend_port} 起不来。先单独跑一下看报错：")
            print("    cd back && python -m uvicorn app.main:app --port "
                  f"{backend_port}")
            backend.terminate()
            return 3
        print(f"后端就绪：{args.api}（只绑 127.0.0.1，不用手动开）")

    Handler.api_base = args.api
    handler = functools.partial(Handler, directory=str(web_dir))

    # Ctrl+C 也要把后端一起收掉，否则会留一个「端口被占用」的孤儿进程 ——
    # 下一个进来的人得先去查 PID 才能再起来，这就是「端口越开越乱」的来源。
    def _shutdown(_signum=None, _frame=None):
        if backend is not None and backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend.kill()
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        with http.server.ThreadingHTTPServer(
            ("127.0.0.1", args.port), handler
        ) as httpd:
            print()
            print(f"  ★ 打开这个就行：http://127.0.0.1:{args.port}/")
            print(f"    静态产物：{web_dir}")
            print(f"    /api/* 转发到：{args.api}")
            print("    Ctrl+C 停止（后端会一起停）")
            print()
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        signal.signal(signal.SIGINT, previous)
        if backend is not None and backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
