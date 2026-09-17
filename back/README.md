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

| 地址 | 说明 |
|---|---|
| http://127.0.0.1:8000/docs | **自动生成的接口文档 —— 答辩时直接打开给评委看** |
| http://127.0.0.1:8000/api/health | 健康检查 |

不需要装数据库。默认用 SQLite，`back/shishi.db` 会在首次启动时自动创建，
并灌好 6 种食材 / 4 道菜谱 / 1 个演示账号。

### 跑测试

```powershell
cd back
python -m pytest -q
```

测试用**独立的内存 SQLite**，不会碰 `shishi.db`。

---

## 二、演示账号

| 用户名 | 密码 |
|---|---|
| `demo` | `shishi2026` |

答辩时评委不用注册就能进。种子数据在每次启动时幂等灌入，删掉 `shishi.db`
重启即可恢复初始状态。

---

## 三、接口清单

共 24 个接口。带 🔒 的需要登录（`Authorization: Bearer <token>`）。

### 认证（说明书 §12）

| 方法 | 路径 |
|---|---|
| POST | `/api/auth/register` |
| POST | `/api/auth/login` → `{access_token, token_type}` |
| GET 🔒 | `/api/auth/me` |

### 内容（公开，说明书 §9 / §10 / §11）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/home` | 首页聚合：时令食材 + 菜单推荐（**不返回价格**） |
| GET | `/api/foods` | 食材列表，支持 `category` / `keyword` / 分页 |
| GET | `/api/foods/seasonal` | 时令食材，按应季程度降序 |
| GET | `/api/foods/{id}` | 食材详情（含时令、特征、能做的菜） |
| GET | `/api/recipes` | 菜谱列表，支持 `max_duration` 等筛选 |
| GET | `/api/recipes/search` | 菜名 **或配料名** 搜索 |
| GET | `/api/recipes/{id}` | 菜谱详情（含配料、步骤、是否已收藏） |

### 个人数据（需登录，说明书 §13 / §14 / §15 / §16 / §17 / §19）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST 🔒 | `/api/my-foods` | 我的现有食材（同种食材重复添加会累加，不新增行） |
| PUT/DELETE 🔒 | `/api/my-foods/{id}` | 改数量 / 移除 |
| POST | `/api/recipes/recommend-by-foods` | 按现有食材推荐菜谱 + 还缺什么 |
| GET 🔒 | `/api/favorites` | 我的收藏 |
| POST/DELETE 🔒 | `/api/favorites/{recipe_id}` | 收藏 / 取消（**幂等**） |
| GET 🔒 | `/api/menu/today` | 今日菜单 |
| POST 🔒 | `/api/menu/today/generate` | 生成今日菜单 |
| POST 🔒 | `/api/menu/plan` | 生成多日菜单 |
| POST 🔒 | `/api/shopping-list/generate` | 由菜单生成购物清单 |
| GET 🔒 | `/api/shopping-list` | 最近的购物清单 |
| PUT 🔒 | `/api/shopping-list/items/{id}` | 勾选 / 取消勾选 |

### 其他

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/ai/chat` | AI 助手（登录可选） |
| GET/PUT 🔒 | `/api/profile` | 个人偏好 |
| GET | `/api/health` | 健康检查 |

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
│   │   └── dependencies.py  get_current_user / get_current_user_optional
│   ├── api/
│   │   ├── router.py        汇总路由（⚠️ 路由顺序有意义）
│   │   └── routes/          按业务分文件
│   ├── models/              13 张表（说明书 §7）
│   ├── schemas/             请求 / 响应模型
│   ├── repositories/        数据访问层（说明书 §5.3）
│   ├── services/            业务逻辑层（说明书 §5.2）
│   ├── data/seed.py         种子数据
│   └── utils/time.py
├── tests/                   pytest（54 个用例）
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

### 3. AI 是规则生成，不是真调大模型

`POST /api/ai/chat` 的响应结构与说明书 §20 完全一致（`answer` / `intent` /
`tools_used` / `recipes` / `menu`），但内部是关键词意图识别 + 菜谱检索，
**没有调用任何外部大模型**。

依据是说明书自己的两条要求：§14「第一版可以先用规则匹配，不需要全部依赖 LLM」、
§18「第一版不要把全部逻辑交给 LLM」。好处是零成本、离线可演示、响应稳定；
将来换成真 LLM 时**前端一行都不用改**。

### 4. 首页 `recommended_menus` 的 `id` 固定为 0

说明书 §9 要求首页返回菜单推荐，但库里没有「菜单模板」这种实体（`menu_plans`
是用户自己生成的）。所以这里是按当季菜谱**动态组合**出来的建议，
`id=0` 表示「组合推荐，不是可打开的菜单详情」。

### 5. `recipes.servings` 存数字，响应里是文案

表里是 `int`（说明书 §7.5），响应里按 §11 的要求变成 `"3人份"` 这样的字符串。
转换在 `app/services/recipe_service.py`。

---

## 七、安全上做了什么

| 项 | 做法 |
|---|---|
| 密码 | bcrypt 哈希后存储，**响应模型里根本没有 `password_hash` 字段**，不可能被序列化出去 |
| 用户名枚举 | 「用户不存在」和「密码错误」返回**同一句话** |
| 越权 | 所有按 id 查个人数据的仓储函数**强制带 `user_id`**；别人的记录返回 404 而不是 403（不泄露存在性） |
| 幂等 | 重复收藏不产生重复记录；取消未收藏的菜也不报错 |
| 密钥 | `SECRET_KEY` 走环境变量，`.env` 已在 `.gitignore` 里 |

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
