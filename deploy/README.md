# 食时 · 部署（给运维）

目标：**`git pull` + 跑一次 `deploy.sh`，站点就起来。**

---

## 0. 架构（先看这张图，后面都是细节）

```
                     ┌─────────────────────────────────────┐
  浏览器 ──HTTP:80──▶│ nginx                               │
                     │  /        → /opt/web   （前端静态） │
                     │  /api/    → 127.0.0.1:8000（后端）  │
                     └─────────────────────────────────────┘
                                     │
                                     ▼
                     ┌─────────────────────────────────────┐
                     │ uvicorn (systemd: shishi-backend)   │
                     │  工作目录 /opt/test/back            │
                     │  SQLite  /opt/test/back/shishi.db   │
                     └─────────────────────────────────────┘
```

**关键点：前端和接口走同一个来源（都是 80 端口）。**
所以前端产物里**不需要**写服务器 IP —— 换 IP、换域名、上 HTTPS 都不用重新构建。
这也顺带避开了浏览器的 mixed content 限制（HTTPS 页面不能调 http 接口）。

---

## 1. 前置要求

| 需要 | 说明 |
|---|---|
| Linux + systemd | 阿里云 Ubuntu/CentOS 都行，2 核 2G 够 |
| Python 3.10+ | 系统自带即可 |
| nginx | `apt install nginx` 或 `yum install nginx` |
| 公网 IP / 域名 | 安全组要放行 80（要 HTTPS 再放 443） |
| **Flutter SDK** | ❌ **不需要**。前端产物从 GitHub Release 下载现成的 |

---

## 2. 一键部署

```bash
# 代码放哪：默认按 /opt/test 来（下面脚本里的路径都以此为准）
sudo mkdir -p /opt && cd /opt
sudo git clone https://github.com/aiczz/test.git
cd /opt/test

# 配置密钥（下一步会说这两个值怎么来）
sudo cp back/.env.example back/.env
sudo vi back/.env

# 部署
sudo bash deploy/deploy.sh
```

跑完访问 `http://<你的公网IP>/` 即可。

脚本是**幂等**的，改了代码之后重新 `git pull && sudo bash deploy/deploy.sh` 就行。

---

## 3. 两个密钥，必须自己填

编辑 `/opt/test/back/.env`：

```env
# ① 必须换掉！这是 JWT 签名密钥，用默认值的话任何人都能伪造管理员登录
#    生成方法：python3 -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=<换成一串随机值>

# ② AI 大模型的 key（DeepSeek）
#    ⚠️ 这个值不在仓库里，必须单独问项目负责人要，不要提交到 git
AI_API_KEY=<向负责人索取>
AI_MODEL=deepseek-chat
AI_BASE_URL=https://api.deepseek.com
AI_ENABLED=true

# 天气（Open-Meteo，免费且不需要 key），保持 true 即可
WEATHER_ENABLED=true
```

**`AI_API_KEY` 不填也能跑**：首页推荐和 AI 助手会自动退回确定性算法，
只是没有 AI 润色和候选内的智能挑选。所以「忘了配」不是事故，只是少个亮点。

---

## 4. 内容数据（菜谱库）

后端需要内容表（`ingredients` / `dishes` / `dish_ingredients` / 时令三表）。
仓库里带的是**清洗好的 CSV**（`sql/cleaned_v2/*.csv`），`deploy.sh` 会自动导入。

导入后的规模（供核对）：

| 表 | 行数 |
|---|---|
| `ingredients` | 8087（其中 590 个是面向用户展示的核心食材）|
| `dishes` | 10000 |
| `dish_ingredients` | 77886 |
| `seasonal_calendar` / `seasonal_food` / `seasonal_dish_links` | 52 / 544 / 101 |

> 这个导入是**一次性**的：脚本会检测表是否已存在，已导入就跳过。
> 想强制重导：`sudo bash deploy/deploy.sh --reload-data`

导入后后端会自动识别为 `compact` 模式，只读内容表、另建用户业务表
（用户 / 收藏 / 我的食材 / 菜单 / 购物清单 / AI 缓存）。

---

## 5. 前端产物从哪来

服务器上**不装 Flutter**。前端由 GitHub Actions 构建并发布成 Release 附件：

- 工作流：`.github/workflows/build-web.yml`
- 产物：`https://github.com/aiczz/test/releases/download/web-latest/web-build.tar.gz`

`deploy.sh` 会自动下载并解压到 `/opt/web`。

**所以流程是：push 代码 → 等 CI 跑完 → 在服务器上跑 deploy.sh。**
只要前端有改动，就必须等 CI 出新产物，否则页面上看到的是旧版本。

> 为什么不在服务器上构建：Flutter SDK 要 1GB+，还要从境外拉依赖，
> 在一台 2 核 2G 的机器上又慢又容易失败。

---

## 6. HTTPS（可选但建议）

上了域名之后：

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

certbot 会自动改 nginx 配置并续期。
**不需要重新构建前端** —— 因为接口是同源的，`https://域名/api/...` 自动就是 HTTPS。

---

## 7. 常用运维命令

```bash
systemctl status shishi-backend      # 看后端状态
journalctl -u shishi-backend -f      # 看实时日志（AI 调用失败会打在这里）
sudo systemctl restart shishi-backend
sudo nginx -t && sudo systemctl reload nginx

# 自检：后端活着吗
curl -s http://127.0.0.1:8000/api/health          # {"status":"ok"}

# 自检：接口通不通（走 nginx）
curl -s http://127.0.0.1/api/health

# 自检：算法 + AI 是否达到设计要求（29 项断言）
cd /opt/test/back && python3 scripts/verify_ai_features.py --base http://127.0.0.1
```

---

## 8. 排错对照表

| 现象 | 原因 / 处理 |
|---|---|
| 打开是白屏，控制台一堆 404 | `/opt/web` 是空的或解压不全。重跑 `deploy.sh`，确认 Release 里有 `web-build.tar.gz` |
| 页面能开，但数据都是假的 | 前端探测不到后端。`curl http://127.0.0.1/api/health` 确认 nginx 反代生效；再看 `systemctl status shishi-backend` |
| 登录报 500 | `SECRET_KEY` 没换或认证依赖没装。看 `journalctl -u shishi-backend` |
| 首页建议里没有 AI 味（都是模板话） | `AI_API_KEY` 没配或调用失败。看 `/api/home` 返回的 `meta.source`：`ai`=真调了，`algorithm`=降级了；以及 `meta.steps` 里「AI 每日建议」那一步的 detail |
| 推荐菜里出现很长的怪标题 | 那是清洗库里 4.6% 的抓取标题，推荐链路已过滤；若仍出现说明跑的是旧代码 |
| `database is locked` | 别同时跑多个后端实例（两个 uvicorn 指向同一个 SQLite） |
| 改了算法但首页没变 | AI 每日结果是**按天缓存**的。等第二天，或 `curl "http://127.0.0.1/api/home?refresh=true"` |
| 换了服务器/域名，前端连不上 | 不用改代码。确认 nginx 的 `server_name` 和 `/api/` 反代即可（前端是同源的）|

---

## 9. 这个部署里有哪些坑是**已经踩过并绕开**的

- **前端不能写死后端 IP** → 改成同源 + nginx 反代
- **compact 模式下新表不会被建** → 新表必须加进 `back/app/core/database.py` 的
  `STATE_TABLES`，否则 `create_all` 不建它（AI 缓存表就是这么加进去的）
- **AI 调用慢于 nginx 默认超时** → `proxy_read_timeout 120s`
- **`WorkingDirectory` 必须设对** → 否则 `sqlite:///./shishi.db` 会落到别处，
  表现为「每次重启数据都空」
- **前端产物必须是 same-origin 构建** → CI 里已去掉 `--dart-define=API_BASE`
