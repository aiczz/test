# 发版 Runbook（照抄即可）

> 这份是**操作清单**，只管「按顺序敲什么、看到什么才算对」。
> 为什么要这么设计、每个坑的成因，见 [README.md](README.md)。
>
> 目标：每次发版都在可核对的数字上往前走，**不靠"看起来正常了"**。

---

## 0. 为什么不能直接 `git pull && bash deploy.sh`

这三件事都真的发生过：

| 踩过的坑 | 后果 |
|---|---|
| 服务器直连 GitHub 只有 **18–23 KB/s** | 61 MB 的前端包要 42 分钟，容易以为卡死 |
| `deploy.sh` 默认优先用 `front/mealmind/build/web` | `/opt/web` 被**装回旧前端**，后端却是新的，最难查 |
| `curl -C -` 续传上一次的包 | 新包更小 → `HTTP 416`，而**磁盘上还是旧包**，sha256 一验才发现 |

所以下面每一步都带一个**硬门槛**：数字不对就停，不往下走。

---

## 1. 发版前：确认 CI 已经把前端重新构建好

前端改动必须等 CI 出新的 `web-build.tar.gz`，否则装上去的是上一版。

```bash
curl -sI https://github.com/aiczz/test/releases/download/web-latest/web-build.tar.gz \
  | grep -iE 'content-length|last-modified'
```

门槛：**`Last-Modified` 必须晚于这次要发的提交时间**。

然后下载一次，记下两个数字（后面的门槛要用）：

```bash
curl -fL --connect-timeout 20 -o /tmp/wb.tgz \
  https://gh-proxy.com/https://github.com/aiczz/test/releases/download/web-latest/web-build.tar.gz
sha256sum /tmp/wb.tgz
stat -c %s /tmp/wb.tgz
tar -xzOf /tmp/wb.tgz main.dart.js | wc -c
```

记成一张小表，等会儿在服务器上逐项对：

```
SHA256    = ................
TGZ_BYTES = ................
JS_BYTES  = ................
```

---

## 2. 服务器：看现场

```bash
sudo -i
date
git -C /opt/test log -1 --oneline
git -C /opt/test status --short
ss -lntp | grep ':8000'
```

门槛：

- `status` **只允许出现未跟踪文件**（`NUL`、`back/.env.bak*`、`back/shishi.db.bak*`）。
  出现已跟踪文件被改动 → **停下**，先查清是谁改的。
- `8000` 必须是 `0.0.0.0`（APK 靠它，见 README）。

## 3. 留回滚点

```bash
git -C /opt/test rev-parse --short HEAD | tee /root/pre_deploy_head.txt
cp -a /opt/web "/opt/web.bak-$(date +%m%d-%H%M)"
du -sh /opt/web.bak-*
```

## 4. 拉代码

```bash
cd /opt/test
git pull
git log -1 --oneline
```

门槛：输出 `Fast-forward`，HEAD 等于这次要发的提交。
出现 `Need to specify how to reconcile divergent branches` → 服务器分支和
GitHub 不同源了，**别硬 merge**，先 `git branch server-old-$(git rev-parse --short HEAD)`
备份再 `git reset --hard origin/main`（会丢服务器上的手工改动，先确认没有）。

## 5. 下载前端（走镜像）

```bash
rm -f /tmp/web.tgz
curl -fL --connect-timeout 20 -o /tmp/web.tgz \
  https://gh-proxy.com/https://github.com/aiczz/test/releases/download/web-latest/web-build.tar.gz
sha256sum /tmp/web.tgz
stat -c %s /tmp/web.tgz
```

门槛：两个数字与第 1 步记录的 `SHA256`、`TGZ_BYTES` **完全一致**。

- **不要加 `-C -`**。续传目标是上一次的包时，新包更小就会 `HTTP 416`
  并且磁盘上留着旧文件，很容易被当成"下载过了"。
- 镜像不通时换 `https://ghfile.geekertao.top/<同样的 GitHub 路径>`。

## 6. 换上前端

```bash
find /opt/web -mindepth 1 -maxdepth 1 -exec rm -rf {} +
tar -xzf /tmp/web.tgz -C /opt/web
stat -c '%s bytes' /opt/web/main.dart.js
```

门槛：`main.dart.js` 等于第 1 步记录的 `JS_BYTES`。

> 先清空再解包，是为了清掉上一版留下的多余文件；
> 直接覆盖会让新旧文件混在一起。

## 7. 部署后端 + nginx

```bash
bash /opt/test/deploy/deploy.sh --no-web
```

用 `--no-web` 的原因：前端第 6 步已经用镜像装好了，让 `deploy.sh` 再去
GitHub 下载就白等 40 分钟；而**不带** `--no-web` 的话它会优先用
`front/mealmind/build/web`（服务器上那份旧产物），把新前端盖回去。

门槛：`4/7` 打印的监听地址必须是 `0.0.0.0:8000`。

末尾那句 `[!] 首页接口没响应` 是脚本误报（`| head -c` 打断 curl 导致退出码 23），
**新版本脚本已修**；仍看到的话核对 `7/7` 里「后端直连」「经 nginx」两行是否 ok。

## 8. 验证（四类，一类都不能省）

```bash
# ① 进程与监听
systemctl is-active shishi-backend
ss -lntp | grep ':8000'

# ② 两个入口都活着
curl -s http://127.0.0.1:8000/api/health; echo
curl -s http://127.0.0.1/api/health; echo

# ③ 产物真的换了
stat -c '%s bytes' /opt/web/main.dart.js
curl -sI http://127.0.0.1/canvaskit/canvaskit.wasm | grep -i content-type

# ④ 功能验收（49 项）
cd /opt/test/back && .venv/bin/python scripts/verify_ai_features.py --base http://127.0.0.1
```

必须同时满足：

| 检查 | 期望 |
|---|---|
| `is-active` | `active` |
| `ss` | `0.0.0.0:8000`（**不能是 127.0.0.1**） |
| 两个 health | 都是 `{"status":"ok"}` |
| `main.dart.js` | 等于 `JS_BYTES` |
| `canvaskit.wasm` | `Content-Type: application/wasm` |
| 验收脚本 | `49 项通过，0 项未通过` |

## 9. 从外网再验一遍（不能只听服务器自己说）

在本机（不登录服务器）跑：

```bash
curl -sI http://<服务器IP>/main.dart.js | grep -iE 'HTTP/|content-length'
curl -sI http://<服务器IP>/canvaskit/canvaskit.wasm | grep -i content-type
curl -s http://<服务器IP>/api/health; echo
curl -s http://<服务器IP>:8000/api/health; echo
```

再用**无痕窗口**打开站点（普通窗口有 7 天静态缓存，会看到旧界面甚至旧的白屏）。
改动集中在 AI 页 / 食材页时，重点看这两页。

---

## 10. 回滚

```bash
cd /opt/test
git reset --hard "$(cat /root/pre_deploy_head.txt)"

# 前端回到备份（换成实际那个目录名）
cp -a /opt/web.bak-*/. /opt/web/

bash deploy/deploy.sh --no-web
```

---

## 附：这次发版（1926ca2 → 2026-10-17）的实际数字

留个样本，下次好对照量级：

```
SHA256    = 64ff90cae902c1d50a0a7dc7a47cf5a942feb14294435d691250f8daf52b7ac2
TGZ_BYTES = 61090008
JS_BYTES  = 3343276
```

镜像实测 21.6 MB/s（2 秒下完），同一时刻服务器直连 GitHub 是 18 KB/s。
