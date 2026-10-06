# 食时 · 后端

FastAPI + SQLModel 实现，严格按 [`食时_App后端实现说明_Codex.md`](食时_App后端实现说明_Codex.md) 落地。

回答两个问题：**今天吃什么**、**该买什么菜**。

---

## 一、快速开始

```powershell
cd back

# 1. 装依赖（国内网络加镜像）
python -m pip install -r requirements.txt
# 慢的话：
# python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 起服务（首次启动会自动建表 + 灌种子数据）
python -m uvicorn app.main:app --reload --port 8000
```

起来之后：

| 地址                             | 说明                                             |
| -------------------------------- | ------------------------------------------------ |
| http://127.0.0.1:8000/docs       | **自动生成的接口文档 —— 答辩时直接打开给评委看** |
| http://127.0.0.1:8000/api/health | 健康检查                                         |

不需要装数据库。默认用 SQLite，`back/shishi.db` 会在首次启动时自动创建，
并灌好 6 种食材 / 4 道菜谱 / 1 个演示账号。

### 跑测试

```powershell
cd back
python -m pytest -q
```

测试用**独立的内存 SQLite**，不会碰 `shishi.db`。

---

## 一、五、和前端联调（有几个坑，先看这里）

### 后端地址是自动选的

`front/mealmind/lib/services/api_config.dart` 按运行平台自动决定：

| 跑在哪                         | 用的地址                                                    |
| ------------------------------ | ----------------------------------------------------------- |
| `flutter run -d chrome` / 桌面 | `http://127.0.0.1:8000`                                     |
| Android 模拟器                 | `http://10.0.2.2:8000`（模拟器里的 127.0.0.1 指模拟器自己） |
| Android 真机                   | 要改成电脑的局域网 IP，如 `http://192.168.1.5:8000`         |

App 启动时会探测一次 `/api/health`：**通了就用真后端，不通就静默走本地演示数据**，
界面不会弹错误。所以"没起后端"和"起了后端"两种状态都能正常演示。

### ⚠️ 线上 PWA 连不上你本机的后端（浏览器限制，不是 bug）

线上是 `https://aiczz.github.io/...`（HTTPS），本地后端是 `http://`。
浏览器会直接拦掉 HTTPS 页面发出的 http 请求（mixed content）。
**要演示前后端打通，请用 `flutter run -d chrome`，或者打包成 APK。**

### ⚠️ Windows 上 `flutter test` 和 `build apk` 需要开发者模式

`shared_preferences` 带原生插件，Windows 构建插件时要创建符号链接。
没开开发者模式会直接失败：

```
Building with plugins requires symlink support.
Please enable Developer Mode in your system settings.
```

开一次就好（设置 → 隐私和安全性 → 开发者选项 → 开发人员模式），或者：

```powershell
start ms-settings:developers
```

> `flutter build web` **不受影响** —— Web 目标不用原生插件，
> 所以 CI 和线上发布一直是正常的。

---

## 二、演示账号

| 用户名  | 密码          | 身份                                         |
| ------- | ------------- | -------------------------------------------- |
| `demo`  | `shishi2026`  | 普通用户                                     |
| `admin` | `admin123456` | **管理员** —— 封禁账号 / 看统计 / 看登录记录 |

答辩时评委不用注册就能进。种子数据在每次启动时幂等灌入，删掉 `shishi.db`
重启即可恢复初始状态。

> ⚠️ 这两个密码是**演示用**的，写进文档是为了省事。
> 真实部署前必须改掉 —— 见第七节。

---

## 三、接口清单

共 **32 个接口**（32 条路径，`@router.*` 装饰器计数）。带 🔒 的需要登录
（`Authorization: Bearer <token>`）。

### 认证（说明书 §12）

| 方法   | 路径                                             |
| ------ | ------------------------------------------------ |
| POST   | `/api/auth/register`                             |
| POST   | `/api/auth/login` → `{access_token, token_type}` |
| GET 🔒 | `/api/auth/me`                                   |

### 内容（公开，说明书 §9 / §10 / §11）

| 方法 | 路径                  | 说明                                            |
| ---- | --------------------- | ----------------------------------------------- |
| GET  | `/api/home`           | 首页聚合：时令食材 + 菜单推荐（**不返回价格**） |
| GET  | `/api/foods`          | 食材列表，支持 `category` / `keyword` / 分页    |
| GET  | `/api/foods/seasonal` | 时令食材，按应季程度降序                        |
| GET  | `/api/foods/{id}`     | 食材详情（含时令、特征、能做的菜）              |
| GET  | `/api/recipes`        | 菜谱列表，支持 `tag` / `max_duration` 等筛选    |
| GET  | `/api/recipes/tags`   | 菜谱分类（分组 + 每个分类的菜品数）             |
| GET  | `/api/recipes/search` | 菜名 **或配料名** 搜索                          |
| GET  | `/api/recipes/{id}`   | 菜谱详情（含配料、步骤、是否已收藏）            |

> **`/api/recipes/tags` 是菜谱页分类筛选区的唯一数据源。**
> 清洗库的 `dishes.tags_json` 有 985 个零散标签（「汤」「汤羹」「老火汤」…），
> 后端归一成 **45 个规范分类**、分成 8 组下发，并且**只返回有菜的分类** ——
> 所以界面上每个分类点进去都真的有菜。前端**不要**再写死分类名：
> 之前写死的 `['快手菜','汤品','低脂','家常']` 和库里的
> 「家常菜」「汤羹」「低脂减重」对不上，结果每个分类点进去都是空的。
> 归一规则见 `app/data/dish_tags.py`，量化自检见
> `python scripts/measure_dish_tags.py`（实测 10000 道菜里 9996 道可被筛到）。

### 个人数据（需登录，说明书 §13 / §14 / §15 / §16 / §17 / §19）

| 方法           | 路径                              | 说明                                             |
| -------------- | --------------------------------- | ------------------------------------------------ |
| GET/POST 🔒    | `/api/my-foods`                   | 我的现有食材（同种食材重复添加会累加，不新增行） |
| PUT/DELETE 🔒  | `/api/my-foods/{id}`              | 改数量 / 移除                                    |
| POST           | `/api/recipes/recommend-by-foods` | 按现有食材推荐菜谱 + 还缺什么                    |
| GET 🔒         | `/api/favorites`                  | 我的收藏                                         |
| POST/DELETE 🔒 | `/api/favorites/{recipe_id}`      | 收藏 / 取消（**幂等**）                          |
| GET 🔒         | `/api/menu/today`                 | 今日菜单                                         |
| POST 🔒        | `/api/menu/today/generate`        | 生成今日菜单                                     |
| POST 🔒        | `/api/menu/plan`                  | 生成多日菜单                                     |
| POST 🔒        | `/api/shopping-list/generate`     | 由菜单生成购物清单                               |
| GET 🔒         | `/api/shopping-list`              | 最近的购物清单                                   |
| PUT 🔒         | `/api/shopping-list/items/{id}`   | 勾选 / 取消勾选                                  |

### 管理员（需管理员身份）

说明书里没有这一节，属于**本次新增**的后台管理功能。

| 方法    | 路径                          | 说明                                                                                            |
| ------- | ----------------------------- | ----------------------------------------------------------------------------------------------- |
| GET 🔒  | `/api/admin/stats`            | 用户统计：总数 / 管理员数 / 封禁数 / 今日新增 / 总登录次数 / 今日登录 / 今日失败 / 今日活跃用户 |
| GET 🔒  | `/api/admin/users`            | 用户列表，分页 + 按用户名/昵称搜索，含每人成功登录次数                                          |
| POST 🔒 | `/api/admin/users/{id}/ban`   | 封禁                                                                                            |
| POST 🔒 | `/api/admin/users/{id}/unban` | 解封                                                                                            |
| GET 🔒  | `/api/admin/logins`           | 登录记录，含失败尝试（`only_failed=true`），可按用户名搜                                        |

### 其他

| 方法       | 路径                | 说明                                                       |
| ---------- | ------------------- | ---------------------------------------------------------- |
| POST       | `/api/ai/chat`      | AI 助手对话（登录可选）                                    |
| POST       | `/api/ai/recommend` | **AI 配菜**：已选食材 + 今日菜单已有菜 + 硬约束 → 推荐菜品 |
| GET/PUT 🔒 | `/api/profile`      | 家庭档案（人数 / 烹饪时间 / 限钠 / 口味偏好 / 忌口 / 厨具） |
| GET        | `/api/health`       | 健康检查                                                   |

`GET /api/home` 也扩了参数（全部可选，不传就是旧行为）：

```
/api/home?city=杭州&lat=30.27&lon=120.16&date=2026-10-05
          &people=3&cook_minutes=45&low_sodium=true&avoid=辛辣&refresh=false
```

> **家庭档案必须存在服务器上，不能只留前端内存。**
> `/api/profile` 是那套约束的持久化出口：前端登录后启动时拉一次、保存时推一次，
> 另外本机也留一份缓存。
> 踩过的坑：前端原先**从来没调过这个接口** —— 在「我的」页把人数从 3 改成 5，
> 切到首页和 AI 页看到的还是 3，刷新一下连「我的」页自己也变回 3。
> `user_preferences` 新增的 `low_sodium` / `cook_minutes` / `tools` /
> `diet_preferences` 四列，靠 `create_db_and_tables()` 里的增量 `ALTER TABLE`
> 补到已有库上（`create_all` 不会给已存在的表加列）。

---

## 四、数据库：SQLite 现在，PostgreSQL 随时

本机没有 PostgreSQL 也没有 Docker，而比赛演示需要"clone 下来就能跑"，
所以默认用 SQLite。**切换 PostgreSQL 只改一行**：

```bash
# .env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/shishi
```

再装驱动即可（`requirements.txt` 里已注释好）：

```powershell
python -m pip install "psycopg[binary]"
```

代码里只有 `app/core/database.py` 需要区分两种数据库（SQLite 要
`check_same_thread=False`），其余分层完全不感知。切到 PostgreSQL 后
建议改用 Alembic 迁移（说明书 §25），`create_all()` 可以留着，它是幂等的。

---

## 五、目录结构

```
back/
├── app/
│   ├── main.py              FastAPI 实例 + CORS + lifespan（建表 & 灌种子）
│   ├── core/
│   │   ├── config.py        pydantic-settings 配置
│   │   ├── database.py      引擎与会话（唯一区分 SQLite/PG 的地方）
│   │   ├── security.py      bcrypt 哈希 + JWT 签发/校验
│   │   └── dependencies.py  get_current_user / _optional / get_current_admin
│   ├── api/
│   │   ├── router.py        汇总路由（⚠️ 路由顺序有意义）
│   │   └── routes/          按业务分文件
│   ├── models/              14 张表（说明书 §7）
│   ├── schemas/             请求 / 响应模型
│   ├── repositories/        数据访问层（说明书 §5.3）
│   ├── services/            业务逻辑层（说明书 §5.2）
│   ├── data/seed.py         种子数据
│   └── utils/time.py
├── tests/                   pytest（71 个用例，CI 里会真的跑）
├── requirements.txt
├── .env.example
└── pytest.ini
```

分层照说明书 §5：Router → Service → Repository → Model / Schema。

---

## 六、和说明书不一致的地方（都是有意为之，逐条说明）

### 1. `foods.tags` / `recipes.tags` 是新增的 JSON 列

说明书 §10 / §11 的**响应**里有 `tags` 数组（前端卡片要展示「润燥养胃」这类标签），
但 §7.3 / §7.5 的**表定义**里没有任何字段能承载它。所以补了一个 JSON 列，
而不是在响应里硬拼字符串。

### 2. 响应不做 `{code, message, data}` 包装

说明书 §28 给了两种方案并说「全项目必须统一」。本项目统一选**标准 HTTP 状态码
直接返回 data** —— 前端 Dio 处理更直接，`/docs` 里的响应结构也更清楚。

### 3. AI 的分工：**算法选、AI 说**（本次已接真大模型）

`POST /api/ai/chat` 与 `POST /api/ai/recommend` 都接上了 DeepSeek，但**不是**
把库丢给大模型让它自由生成。分工是：

```
综合打分算法（app/services/scoring_service.py）
   从我们自己的清洗库里按 时令 / 天气 / 营养 / 标签 / 热度 打分筛候选
        ↓  候选集（8 个）
大模型（app/ai/client.py）
   只在候选集内挑选与解释 —— 不在候选集里的 id 一律丢弃
        ↓
用户硬约束再收口一次（忌口 / 限钠 / 可用时间）
```

**为什么必须这么设计**：清洗库有 590 个核心食材、10000 道菜。直接让模型
「推荐几道」，它一定会编出不存在的菜名，或者推荐一道要炖三小时、而家里
只有 45 分钟的菜。现在的做法保证：接口返回的每一道菜都真实存在于库里，
每一步都能被验证（`trace` 里能看到召回了多少候选、哪些菜被否决）。

没配 `AI_API_KEY`、超时、返回的不是 JSON —— 任何一种都会退回**确定性算法**，
响应结构完全不变。所以 AI 挂了不会让接口 500，评委席上断网也照样能演示。

> 说明书 §14「第一版可以先用规则匹配」、§18「第一版不要把全部逻辑交给 LLM」
> 这两条现在有了更强的落地：规则不再是「第一版的妥协」，而是**硬约束的执行者**
> 和 AI 幻觉的安全网。

### 4. 首页 `recommended_menus` 的 `id` 固定为 0

说明书 §9 要求首页返回菜单推荐，但库里没有「菜单模板」这种实体（`menu_plans`
是用户自己生成的）。所以这里是按当季菜谱**动态组合**出来的建议，
`id=0` 表示「组合推荐，不是可打开的菜单详情」。

### 5. `recipes.servings` 存数字，响应里是文案

表里是 `int`（说明书 §7.5），响应里按 §11 的要求变成 `"3人份"` 这样的字符串。
转换在 `app/services/recipe_service.py`。

---

## 七、安全上做了什么

| 项               | 做法                                                                                                        |
| ---------------- | ----------------------------------------------------------------------------------------------------------- |
| 密码             | bcrypt 哈希后存储，**响应模型里根本没有 `password_hash` 字段**，不可能被序列化出去                          |
| 用户名枚举       | 「用户不存在」和「密码错误」返回**同一句话**                                                                |
| 越权             | 所有按 id 查个人数据的仓储函数**强制带 `user_id`**；别人的记录返回 404 而不是 403（不泄露存在性）           |
| 幂等             | 重复收藏不产生重复记录；取消未收藏的菜也不报错                                                              |
| 密钥             | `SECRET_KEY` 走环境变量，`.env` 已在 `.gitignore` 里                                                        |
| **封禁**         | 被封禁的账号不能登录；**已经签发的 token 也会立刻失效** —— 否则「封禁」只挡得住新登录，挡不住已经在线的会话 |
| **管理员自保**   | 不能封禁自己、也不能封禁其他管理员 —— 两个都会把系统锁死到没人能解封                                        |
| **登录日志**     | 成功和失败都记（含 IP / User-Agent / 失败原因）。失败也记是有意的：反复试密码的行为在日志里一眼能看出来     |
| **封禁校验时机** | 放在密码校验**之后** —— 否则不看密码就能试出「这个账号存在且被封了」，又是一个枚举入口                      |

生产部署前必须把 `SECRET_KEY` 换成随机值：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 八、已知边界

- `food_seasons` 只处理 `start_month <= month <= end_month` 的普通区间，
  跨年区间（如 11 月–次年 2 月）还没支持，需要时在 `food_repository.list_seasonal` 补一个 OR 分支。
- 图片仍是前端的本地 asset 路径（`assets/images/*.jpg`），没有走说明书 §27 的
  后端静态托管 —— 前端图片是打包进 App 的，从后端再拉一遍反而更慢。
- 没有 Alembic 迁移（SQLite 阶段用 `create_all` 足够）。
- 清洗库的 `dishes` 表**没有烹饪时长列**，所以 compact 模式下
  `duration_minutes` 是按标签数估的（10~60 分钟），只用来说明和排序，
  不参与「今天来得及做吗」的硬筛。真实时长只有旧演示表（`recipes`）才有。
- 清洗库的 `dishes.cuisine` 列目前 100% 为空，所以按菜系筛菜筛不出东西
  （这是数据的问题，不是代码的）。

---

## 九、算法 + AI 的推荐是怎么算的

### 9.1 首页（`GET /api/home`）

```
定位城市 ──→ 天气（Open-Meteo，免费无 key）
                │  取不到就按月份的时令气候估算；再不行当「无天气信息」
时令（数据库）──┤
营养 / 标签   ──┼──→ 综合打分算法 ──→ 候选集（各 8 个）
家庭硬约束    ──┘         ▲                    │
                          │                    ▼
                          │        每天每地区【只问一次】大模型
                          │        （结果按 地区+日期+季节+天气 落库缓存）
                          │                    │
                          └──── 用户忌口/限钠/时间 在这里收口 ──→ 最终 3 + 3
```

权重集中在 `app/services/scoring_service.py` 顶部，改权重不用翻代码：

| 因子 | 权重 | 说明 |
| --- | --- | --- |
| 时令 | 3.0 | **主序** —— 应季程度是档位，轮换只在档位内部发生 |
| 天气 | 1.6 | 冷→温热 / 热→清爽 / 雨→祛湿 / 燥→润肺 |
| 营养 | 1.2 | 蔬菜蛋白搭配、膳食纤维；限钠时压低高钠食材 |
| 偏好 | 1.8 | 命中家庭成员口味偏好 |
| 热度 | 0.8 | 食材被多少道菜用到；菜名过长（清洗库里的营销标题）降权 |
| 每日轮换 | 0.9 | `sha256(地区 + 日期 + 条目名)` → 0~1 |

**「同地区同一天一样、跨天不一样」是怎么保证的**：
轮换因子是**确定性**的 —— 同地区 + 同日期永远算出同一个值，
所以那天所有用户拿到的顺序完全一致（也正因此，那一次 AI 调用可以按地区共享）；
日期一变，因子全变，排序就换了。

⚠️ 一个刻意的取舍：轮换因子只在**同一应季档位内**参与排序，不会把 9 月 95 分的
莲藕挤到 90 分的南瓜后面。线上清洗库里同档位有几十个候选（10 月有 46 个
`season_score=100` 的时令食材），轮换效果很明显；本地演示种子只有 6 个食材、
分数各不相同，轮换看不出来 —— 那是数据量差异，不是算法没生效。

### 9.2 AI 配菜（`POST /api/ai/recommend`）

请求里带三样东西：用户勾选的食材（`food_ids`）、今日菜单已有的菜
（`menu_recipe_ids`，会被排除）、家庭硬约束。后端：

1. 按食材从 `dish_ingredients` 召回候选（同时匹配核心食材，
   点「鸡肉」也能召回用「鸡胸肉」的菜）；
2. 用上面的综合打分排序，**忌口与可用时间在这一步硬筛掉**；
3. 取前 8 道喂给大模型，让它挑 3 道并写理由；
4. 校验返回的 id 是否都在候选集内 —— 不在的一律丢弃（幻觉防线）。

### 9.3 知识库来自哪里（**原创性与开源性的落点**）

AI 的每一句话都建立在下面这些**我们自己的、已清洗的**数据上，
不是模型的通用常识：

| 来源表 | 内容 | 规模 |
| --- | --- | --- |
| `ingredients` | 每 100g 营养（能量/蛋白/脂肪/碳水/纤维/钠/钙/维C）、功效标签、中医宜忌、适宜人群 | 8087 行（590 个核心食材） |
| `dishes` | 整菜营养（已按配料克重算好）、标签、营养置信度 | 10000 行 |
| `dish_ingredients` | 配料与克重 | 77886 行 |
| `seasonal_calendar` | **时令知识原文**，如「秋季（9月-11月）的应季蔬菜共 24 种：白萝卜、大白菜、山药、莲藕…」 | 52 行 |
| `seasonal_food` | 逐条时令食材与推荐理由 | 544 行 |

提示词里会把这些**原文**贴给模型（见 `app/services/ai_daily_service.py` 的
`_build_messages`），并要求它引用。所以界面上看到的
「10月应季蔬菜含山药、莲藕，秋季润肺这样吃抗病魔」是**我们的数据**说出来的，
不是模型的记忆。

### 9.4 部署：AI 的 key 怎么给

**⚠️ 不要把 key 提交进仓库。** `.env` 已在 `.gitignore` 里，这是有意的 ——
仓库是公开的，提交进去几分钟内就会被爬走盗刷。

服务器上（`/opt/test/back/.env`）：

```env
AI_ENABLED=true
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=<把 key 单独发给运维同学，不要走 git>
AI_MODEL=deepseek-chat
AI_DAILY_CACHE_ENABLED=true
WEATHER_ENABLED=true
```

**key 不填也能跑** —— 首页与 AI 助手会自动退回确定性算法，
只是少了 AI 润色和候选内的智能挑选。所以「忘了配 key」不是一次事故。

### 9.5 排错

| 现象 | 原因 |
| --- | --- |
| `meta.source` 一直是 `algorithm` | 没配 `AI_API_KEY`，或调用失败。看 `meta.steps` 里「AI 每日建议」那一步的 detail |
| 每次刷新 `ai_ms` 都不为 0（没命中缓存） | `ai_daily_cache` 表没建出来。compact 模式下新表必须加进 `app/core/database.py` 的 `STATE_TABLES`，否则 `create_all` 不会建它 |
| 同一天换了城市，推荐没变 | 前端没把 `city/lat/lon` 传上来；或 `HomeFeedStore` 的签名没变（改了城市名一定会变） |
| 推荐的菜明显不合理 | 先看 `seasonal_food` / `dishes` 里那几行数据本身对不对 —— 算法只对库里的数据负责 |
| 想强制重算当天缓存 | `/api/home?...&refresh=true` |

---

# 连接清洗后的 MySQL 数据库

后端可以直接读取 `sql/cleaned_v2` 导入后的六张内容表，不复制、不重编号，
也不会在启动时向这些表灌演示数据。复制 `.env.example` 为 `.env`，填写：

```env
DATABASE_URL=mysql+pymysql://用户名:密码@127.0.0.1:3306/数据库名?charset=utf8mb4
CONTENT_MODE=compact
```

先按 `sql/cleaned_v2/schema.sql` 和 `sql/cleaned_v2/load_to_mysql.py` 完成导入。
`compact` 模式会检查六张表是否齐全；缺任何一张都会停止启动，避免误连空库。
后端只会另外创建登录、偏好、收藏、我的食材、菜单和购物清单等用户业务表。

- 前端已在 `lib/services/auth_store.dart` 里用 `createApiDio()` 统一处理 401：
  token 过期或账号被封禁时自动清登录态、回到登录页。后端这边不需要额外配合，
  但**新加的接口层必须走这个工厂**，自己 `new Dio()` 会漏掉这一步。
