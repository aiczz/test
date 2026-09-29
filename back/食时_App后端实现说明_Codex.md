# 食时 App 后端实现说明（Codex 开发版）

> 项目名称：食时  
> 项目类型：AI + 开源的时令饮食与智能菜谱 App  
> 面向对象：普通大众用户  
> 团队规模：3 人  
> 开发周期：约 1 个月  
> 后端目标：为 Flutter 前端提供稳定、清晰、易联调的 REST API，并支撑时令食材、菜谱、AI 助手、现有食材、菜单规划、购物清单、收藏与用户偏好等核心功能。

---

# 1. 当前产品范围

本版本重点功能：

```text
时令食材推荐
菜谱浏览与详情
AI 助手
现有食材管理
根据现有食材推荐菜谱
今日菜单
三日菜单
购物清单
收藏
历史菜单
家庭人数
忌口与饮食偏好
```

## 已明确取消的功能

后端禁止重新加入：

```text
实时菜价查询
实时价格接口
价格走势图
价格涨跌幅
价格预测
菜价雷达
低价推荐
电商比价
```

当前版本可以保留：

```text
时令知识
季节适宜度
食材标签
营养基础信息
菜谱信息
AI 推荐逻辑
```

但不依赖实时市场价格。

---

# 2. 后端技术栈

后端统一使用：

```text
Python 3.12+
FastAPI
SQLModel
Pydantic
JWT
Uvicorn
PostgreSQL
```

推荐补充：

```text
Alembic
httpx
python-jose
passlib / pwdlib
python-multipart
pydantic-settings
```

AI 模块可选：

```text
Qwen / 兼容 OpenAI API 的大模型服务
Function Calling
RAG（后期）
FAISS（可选）
BGE Embedding（可选）
```

开发测试：

```text
pytest
pytest-asyncio
httpx AsyncClient
```

部署：

```text
Docker
Docker Compose
Nginx（可选）
```

---

# 3. 后端架构

本项目采用：

> **基于 FastAPI + SQLModel 的轻量分层架构**

不要做复杂微服务。

整体调用链：

```text
Flutter
   ↓ HTTP / JSON
FastAPI Router
   ↓
Pydantic 请求校验
   ↓
Service 业务逻辑
   ↓
Repository / SQLModel
   ↓
PostgreSQL
```

AI 请求：

```text
Flutter
   ↓
FastAPI
   ↓
AI Service
   ↓
Tool / Repository
   ├── 时令食材
   ├── 菜谱
   ├── 用户偏好
   └── 现有食材
   ↓
LLM
   ↓
结构化结果
   ↓
Flutter
```

---

# 4. 目录结构

建议采用：

```text
backend/
├── app/
│   ├── main.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   └── dependencies.py
│   │
│   ├── api/
│   │   ├── router.py
│   │   └── routes/
│   │       ├── auth.py
│   │       ├── home.py
│   │       ├── foods.py
│   │       ├── my_foods.py
│   │       ├── recipes.py
│   │       ├── favorites.py
│   │       ├── menus.py
│   │       ├── shopping.py
│   │       ├── ai.py
│   │       └── profile.py
│   │
│   ├── models/
│   │   ├── user.py
│   │   ├── food.py
│   │   ├── recipe.py
│   │   ├── favorite.py
│   │   ├── my_food.py
│   │   ├── menu.py
│   │   ├── shopping.py
│   │   └── history.py
│   │
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── food.py
│   │   ├── recipe.py
│   │   ├── menu.py
│   │   ├── shopping.py
│   │   ├── ai.py
│   │   └── profile.py
│   │
│   ├── repositories/
│   │   ├── food_repository.py
│   │   ├── recipe_repository.py
│   │   ├── user_repository.py
│   │   ├── menu_repository.py
│   │   └── shopping_repository.py
│   │
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── home_service.py
│   │   ├── food_service.py
│   │   ├── recipe_service.py
│   │   ├── menu_service.py
│   │   ├── shopping_service.py
│   │   └── ai_service.py
│   │
│   ├── ai/
│   │   ├── client.py
│   │   ├── prompts.py
│   │   ├── tools.py
│   │   └── planner.py
│   │
│   ├── data/
│   │   ├── seed/
│   │   └── import_data.py
│   │
│   └── utils/
│       └── response.py
│
├── alembic/
├── tests/
├── scripts/
├── .env
├── .env.example
├── alembic.ini
├── requirements.txt
├── Dockerfile
└── README.md
```

---

# 5. 分层职责

## 5.1 Router

负责：

```text
接收请求
解析参数
权限依赖
调用 Service
返回 Response
```

Router 中不要写大量 SQL 和复杂业务逻辑。

## 5.2 Service

负责：

```text
核心业务逻辑
组合多个 Repository
调用 AI
数据转换
菜单生成
购物清单生成
```

## 5.3 Repository

负责：

```text
数据库 CRUD
查询
分页
过滤
```

Repository 不负责 AI 文案生成。

## 5.4 Model

SQLModel 数据库表。

## 5.5 Schema

Pydantic 请求 / 响应结构。

数据库表和 API 返回模型不要全部混在一起。

---

# 6. 配置管理

使用：

```text
pydantic-settings
```

`.env` 示例：

```env
APP_NAME=ShiShi API
APP_ENV=development
DEBUG=true

DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/shishi

JWT_SECRET_KEY=replace_with_real_secret
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

AI_BASE_URL=
AI_API_KEY=
AI_MODEL=
```

禁止把数据库密码、JWT Secret、AI API Key 写死在代码里。

---

# 7. 数据库设计

## 7.1 users

```text
id
username
email
password_hash
nickname
avatar_url
family_size
created_at
updated_at
```

`family_size` 用于默认菜单人数。

## 7.2 user_preferences

```text
id
user_id
taste
diet_style
avoid_foods
favorite_categories
created_at
updated_at
```

简单版本中 `avoid_foods`、`favorite_categories` 可以先使用 JSON 字段。

## 7.3 foods

```text
id
name
category
image_url
description
nutrition_summary
texture
common_methods
is_active
created_at
updated_at
```

category 示例：

```text
vegetable
fruit
meat_egg
aquatic
soy
grain
seasoning
```

## 7.4 food_seasons

```text
id
food_id
region
start_month
end_month
season_name
season_score
description
```

`season_score` 表示应季程度，不是价格评分。

## 7.5 recipes

```text
id
name
image_url
description
duration_minutes
servings
difficulty
category
season_recommendation
tips
created_at
updated_at
```

## 7.6 recipe_ingredients

```text
id
recipe_id
food_id
ingredient_name
amount
unit
is_required
```

## 7.7 recipe_steps

```text
id
recipe_id
step_no
title
description
image_url
```

## 7.8 favorites

```text
id
user_id
recipe_id
created_at
```

联合唯一：

```text
user_id + recipe_id
```

## 7.9 my_foods

```text
id
user_id
food_id
custom_name
amount
unit
expire_hint
created_at
updated_at
```

## 7.10 menu_plans

```text
id
user_id
title
plan_type
people
start_date
days
source
created_at
```

plan_type：

```text
today
three_day
custom
```

source：

```text
manual
ai
```

## 7.11 menu_plan_items

```text
id
menu_plan_id
day_index
meal_type
recipe_id
sort_order
```

meal_type：

```text
breakfast
lunch
dinner
```

## 7.12 shopping_lists

```text
id
user_id
menu_plan_id
title
created_at
updated_at
```

## 7.13 shopping_items

```text
id
shopping_list_id
food_id
name
amount
unit
category
checked
```

---

# 8. 核心数据关系

```text
User
 ├── UserPreference
 ├── MyFood
 ├── Favorite
 ├── MenuPlan
 └── ShoppingList

Food
 ├── FoodSeason
 └── RecipeIngredient

Recipe
 ├── RecipeIngredient
 ├── RecipeStep
 ├── Favorite
 └── MenuPlanItem
```

---

# 9. 首页接口

前端已经确定首页必须同时包含：

```text
食材推荐
+
菜单推荐
```

接口：

```http
GET /api/home
```

Query 可选：

```text
region
month
```

例如：

```http
GET /api/home?region=杭州&month=9
```

建议返回：

```json
{
  "season": {
    "name": "秋季",
    "month": 9,
    "region": "杭州"
  },
  "hero": {
    "title": "今日推荐",
    "subtitle": "应季食材 · 家常菜单 · 轻松安排",
    "image": "/static/banners/autumn.jpg"
  },
  "recommended_foods": [
    {
      "id": 1,
      "name": "莲藕",
      "image": "/static/foods/lotus_root.jpg",
      "season_score": 92,
      "tags": ["秋季当季", "脆嫩清甜"]
    }
  ],
  "recommended_menus": [
    {
      "id": 1,
      "title": "秋日家常菜单",
      "image": "/static/menus/autumn_home.jpg",
      "servings": "3人",
      "tags": ["3菜1汤", "营养均衡"]
    }
  ],
  "ai_tip": "先选当季食材，再搭配家常菜单，做饭更轻松。"
}
```

注意：**不返回价格字段。**

---

# 10. 食材接口

## 10.1 食材列表

```http
GET /api/foods
```

Query：

```text
category
month
region
keyword
page
page_size
```

## 10.2 时令食材

```http
GET /api/foods/seasonal
```

Query：

```text
region
month
limit
```

## 10.3 食材详情

```http
GET /api/foods/{food_id}
```

响应建议：

```json
{
  "id": 1,
  "name": "莲藕",
  "image": "...",
  "category": "vegetable",
  "season": {
    "name": "秋季",
    "score": 92,
    "description": "9月正是莲藕适宜食用的季节。"
  },
  "tags": [
    "富含膳食纤维",
    "清甜爽脆",
    "适合煲汤"
  ],
  "features": {
    "suitable_for": "适合大多数人群",
    "common_methods": "煲汤、清炒、凉拌",
    "texture": "清脆或粉糯"
  },
  "recommended_recipes": []
}
```

---

# 11. 菜谱接口

## 11.1 菜谱列表

```http
GET /api/recipes
```

Query：

```text
category
season
difficulty
max_duration
keyword
page
page_size
```

## 11.2 菜谱搜索

```http
GET /api/recipes/search?q=莲藕
```

支持菜名搜索、食材搜索。

## 11.3 菜谱详情

```http
GET /api/recipes/{recipe_id}
```

响应：

```json
{
  "id": 10,
  "name": "莲藕排骨汤",
  "image": "...",
  "description": "莲藕清甜，排骨鲜香。",
  "duration_minutes": 60,
  "servings": "2-3人份",
  "difficulty": "简单",
  "tags": ["秋日暖汤", "家常", "营养"],
  "ingredients": [
    {
      "name": "莲藕",
      "amount": "500",
      "unit": "g"
    }
  ],
  "steps": [
    {
      "step_no": 1,
      "title": "排骨焯水",
      "description": "...",
      "image": "..."
    }
  ],
  "tips": [
    "莲藕选粉藕，炖汤口感更好。"
  ],
  "is_favorite": false
}
```

---

# 12. 用户认证

接口：

```http
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
```

登录后返回：

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

请求头：

```http
Authorization: Bearer <token>
```

需要登录：

```text
收藏
现有食材
菜单
购物清单
个人偏好
```

公开：

```text
首页
食材
菜谱
```

密码必须 Hash 后保存，禁止明文存储。

---

# 13. 我的现有食材

查询：

```http
GET /api/my-foods
```

添加：

```http
POST /api/my-foods
```

请求：

```json
{
  "food_id": 1,
  "amount": 3,
  "unit": "个"
}
```

修改：

```http
PUT /api/my-foods/{id}
```

删除：

```http
DELETE /api/my-foods/{id}
```

---

# 14. 根据现有食材推荐菜谱

推荐提供：

```http
POST /api/recipes/recommend-by-foods
```

请求：

```json
{
  "food_ids": [1, 2, 3],
  "people": 3
}
```

返回：

```json
{
  "recommended_recipes": [],
  "missing_ingredients": []
}
```

第一版可以先用规则匹配，不需要全部依赖 LLM。

---

# 15. 收藏接口

```http
GET    /api/favorites
POST   /api/favorites/{recipe_id}
DELETE /api/favorites/{recipe_id}
```

重复收藏不要生成重复记录。

---

# 16. 今日菜单

获取：

```http
GET /api/menu/today
```

生成：

```http
POST /api/menu/today/generate
```

请求：

```json
{
  "people": 3,
  "meal_types": [
    "breakfast",
    "lunch",
    "dinner"
  ],
  "preferences": [
    "家常",
    "清淡"
  ]
}
```

返回：

```json
{
  "id": 100,
  "title": "今日菜单",
  "people": 3,
  "meals": {
    "breakfast": [],
    "lunch": [],
    "dinner": []
  }
}
```

---

# 17. 三日菜单

接口：

```http
POST /api/menu/plan
```

请求：

```json
{
  "days": 3,
  "people": 3,
  "preferences": [
    "家常",
    "秋季"
  ]
}
```

返回：

```json
{
  "id": 101,
  "title": "三日菜单",
  "days": [
    {
      "day_index": 1,
      "label": "周一",
      "recipes": []
    }
  ]
}
```

---

# 18. 菜单生成原则

第一版不要把全部逻辑交给 LLM。

建议：

```text
数据库候选筛选
 ↓
季节匹配
 ↓
忌口过滤
 ↓
家庭人数
 ↓
菜品类型去重
 ↓
AI 做最终组合 / 解释
```

数据库负责真实菜谱、真实食材、标签和时令。

AI 负责理解用户、组合菜单、解释推荐原因。

---

# 19. 购物清单

生成：

```http
POST /api/shopping-list/generate
```

请求：

```json
{
  "menu_plan_id": 101
}
```

逻辑：

```text
读取菜单所有菜谱
 ↓
合并相同食材
 ↓
扣除用户已有食材（可选）
 ↓
按类别分组
 ↓
生成购物清单
```

获取：

```http
GET /api/shopping-list
```

勾选：

```http
PUT /api/shopping-list/items/{item_id}
```

请求：

```json
{
  "checked": true
}
```

---

# 20. AI 助手

接口：

```http
POST /api/ai/chat
```

请求：

```json
{
  "message": "三个人今晚吃什么？",
  "conversation_id": null
}
```

推荐响应格式：

```json
{
  "answer": "根据当前秋季时令，我推荐以下家常晚餐。",
  "intent": "meal_recommendation",
  "tools_used": [
    "season_search",
    "preference_check",
    "recipe_search"
  ],
  "recipes": [
    {
      "id": 10,
      "name": "莲藕排骨汤",
      "image": "...",
      "duration_minutes": 60,
      "servings": "3人份",
      "tags": [
        "秋季时令",
        "家常"
      ]
    }
  ],
  "menu": {
    "title": "今晚推荐",
    "summary": "3菜1汤 · 适合3人"
  }
}
```

前端会根据 `recipes`、`menu`、`tools_used` 展示结构化卡片。

---

# 21. AI Tool 设计

建议：

```text
get_seasonal_foods()
search_recipes()
get_recipe_detail()
get_user_preferences()
get_my_foods()
recommend_recipes_by_foods()
create_menu_plan()
```

禁止：

```text
get_live_price()
get_market_price()
predict_price()
```

当前版本没有价格能力。

---

# 22. AI Prompt 原则

System Prompt 要强调：

```text
你是“食时”时令饮食助手。

1. 根据季节推荐适合的食材。
2. 基于真实菜谱数据库推荐菜谱。
3. 尊重用户忌口和偏好。
4. 尽量使用常见家常食材。
5. 不编造实时价格。
6. 不声称拥有实时市场价格。
7. 推荐优先引用工具返回的数据。
8. 输出尽量结构化。
```

---

# 23. Pydantic Schema 示例

```python
class FoodResponse(BaseModel):
    id: int
    name: str
    image: str | None = None
    category: str
    season_score: int | None = None
    tags: list[str] = []
```

AI：

```python
class AiChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
```

菜单：

```python
class MenuGenerateRequest(BaseModel):
    people: int = Field(gt=0, le=20)
    days: int = Field(default=1, ge=1, le=7)
    preferences: list[str] = []
```

---

# 24. SQLModel 注意事项

数据库 Model 示例：

```python
class Food(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    category: str = Field(index=True)
    image_url: str | None = None
    description: str | None = None
```

不要直接把所有 SQLModel table 类暴露给 API。

建议拆：

```text
Food DB Model
FoodCreate Schema
FoodUpdate Schema
FoodResponse Schema
```

---

# 25. PostgreSQL 与 Alembic

数据库名称建议：

```text
shishi
```

开发阶段尽快使用 PostgreSQL。

建议从项目初期接入 Alembic：

```text
修改 Model
 ↓
alembic revision --autogenerate
 ↓
检查 migration
 ↓
alembic upgrade head
```

---

# 26. Seed 数据

第一版必须准备固定基础数据：

```text
30-50 种常用食材
50-100 道家常菜谱
12 个月时令关系
基础标签
```

优先食材：

```text
莲藕
南瓜
白菜
西红柿
土豆
菠菜
青椒
胡萝卜
鸡蛋
猪肉
鸡肉
豆腐
黄瓜
冬瓜
香菇
```

优先菜谱：

```text
莲藕排骨汤
番茄炒蛋
清炒白菜
南瓜粥
香菇炖鸡
青椒土豆丝
凉拌黄瓜
冬瓜汤
土豆烧肉
清炒上海青
```

---

# 27. 静态图片

比赛 Demo 优先稳定。

建议：

```text
前端 assets
或
后端 /static
```

不要让关键首页图片完全依赖第三方图片链接。

---

# 28. API 返回规范

建议统一。

成功：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

失败：

```json
{
  "code": 40001,
  "message": "invalid request",
  "data": null
}
```

也可以使用标准 HTTP 状态码直接返回 data，但全项目必须统一。

---

# 29. HTTP 状态码建议

```text
200 查询成功
201 创建成功
204 删除成功
400 参数问题
401 未登录 / Token失效
403 无权限
404 资源不存在
409 重复资源
422 Pydantic校验错误
500 服务器异常
```

---

# 30. 分页

列表统一：

```text
page
page_size
```

响应：

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 100
}
```

---

# 31. 第一版不建议引入的组件

暂时不要：

```text
Redis
Kafka
RabbitMQ
Elasticsearch
Kubernetes
复杂微服务
复杂推荐神经网络
实时爬虫
价格预测
复杂管理后台
```

三人一个月，核心闭环优先。

---

# 32. 后端开发优先级

## P0 必做

```text
项目初始化
数据库连接
用户认证
食材列表
时令食材
食材详情
菜谱列表
菜谱详情
现有食材
AI聊天
今日菜单
购物清单
首页聚合 API
```

## P1

```text
收藏
三日菜单
历史菜单
用户偏好
家庭人数
```

## P2

```text
拍照识别
复杂 RAG
向量数据库
复杂营养评分
消息通知
```

---

# 33. 一个月后端开发顺序

## 第 1 周

目标：

```text
FastAPI + PostgreSQL 跑起来
Flutter 能接接口
```

完成：

```text
Python 环境
FastAPI
Uvicorn
PostgreSQL
SQLModel
Alembic
基础目录
Food / Recipe Model
Seed 数据
GET /api/foods
GET /api/recipes
GET /api/home
Swagger
```

第一周结束必须跑通：

```text
Flutter
 ↓
Dio
 ↓
FastAPI
 ↓
PostgreSQL
```

## 第 2 周

```text
JWT
注册
登录
/me
Food Detail
Recipe Detail
My Foods CRUD
Favorites
Shopping List 数据模型
```

## 第 3 周

```text
AI Client
AI Prompt
AI Tools
POST /api/ai/chat
POST /api/menu/today/generate
POST /api/menu/plan
POST /api/shopping-list/generate
```

## 第 4 周

停止大量扩功能。

重点：

```text
API稳定
异常处理
AI输出格式稳定
Swagger
前后端联调
Bug
Docker
部署
演示数据
```

---

# 34. Codex 任务顺序

```text
Task 1
初始化 FastAPI 项目

Task 2
创建 config.py / .env

Task 3
配置 PostgreSQL + SQLModel

Task 4
配置 Alembic

Task 5
创建 Food / FoodSeason Model

Task 6
创建 Recipe / RecipeIngredient / RecipeStep Model

Task 7
创建 Seed 数据

Task 8
实现 Food Repository / Service / Router

Task 9
实现 Recipe Repository / Service / Router

Task 10
实现 GET /api/home

Task 11
实现 User / JWT

Task 12
实现 My Foods

Task 13
实现 Favorites

Task 14
实现 MenuPlan

Task 15
实现 Shopping List

Task 16
实现 AI Client

Task 17
实现 AI Tools

Task 18
实现 /api/ai/chat

Task 19
补测试

Task 20
Docker 化
```

---

# 35. Codex 编码规范

必须：

```text
类型注解
清晰命名
Router / Service / Repository 分层
Pydantic 校验
统一异常处理
.env 管配置
JWT 密钥禁止硬编码
密码禁止明文
```

禁止：

```text
一个 main.py 写全项目
Router 直接写大量 SQL
重新加入价格功能
为了展示技术堆 Redis / Kafka / 微服务
AI 直接编造数据库中不存在的菜谱
```

---

# 36. 首页接口设计原则

前端首页已经冻结：

```text
食材推荐
+
菜单推荐
```

所以：

```http
GET /api/home
```

应尽量一次返回首页主体数据。

不要让 Flutter 首页自己拼十几个接口。

---

# 37. AI 与业务逻辑边界

AI 不负责：

```text
用户认证
数据库 CRUD
食材事实数据
菜谱步骤事实存储
购物清单勾选状态
```

AI 负责：

```text
理解用户自然语言
推荐组合
菜单规划
解释原因
生成自然语言回复
```

---

# 38. 比赛 Demo 核心后端路径

Demo 1：

```text
GET /api/home
 ↓
首页展示时令食材
+
菜单推荐
```

Demo 2：

```text
GET /api/foods/{id}
 ↓
查看莲藕
 ↓
返回推荐菜谱
```

Demo 3：

```text
POST /api/ai/chat

“三个人今晚吃什么？”
 ↓
时令筛选
 ↓
菜谱检索
 ↓
用户偏好
 ↓
返回结构化推荐
```

Demo 4：

```text
加入菜单
 ↓
POST /api/shopping-list/generate
 ↓
自动合并食材
 ↓
购物清单
```

---

# 39. 最小依赖建议

`requirements.txt` 初版：

```text
fastapi
uvicorn[standard]
sqlmodel
psycopg[binary]
alembic
pydantic
pydantic-settings
python-jose[cryptography]
passlib[bcrypt]
python-multipart
httpx
pytest
pytest-asyncio
```

版本号在创建项目时锁定。

---

# 40. 最终后端核心闭环

## 路径 A：时令推荐

```text
首页
 ↓
时令食材
 ↓
食材详情
 ↓
推荐菜谱
 ↓
菜谱详情
```

## 路径 B：AI 推荐

```text
AI 助手
 ↓
用户自然语言
 ↓
时令 + 偏好 + 菜谱
 ↓
结构化菜单
 ↓
加入今日菜单
```

## 路径 C：现有食材

```text
我的食材
 ↓
已有食材
 ↓
推荐能做的菜
 ↓
菜谱
 ↓
生成缺少食材
 ↓
购物清单
```

---

# 41. 开发原则

Codex 实现时优先级：

```text
稳定 > 技术炫技
数据真实 > AI编造
API清晰 > 过度抽象
核心闭环 > 功能数量
前后端一致 > 临时发挥
可演示 > 复杂架构
```

最终目标：

> 构建一个稳定、结构清晰、与 Flutter 前端完全对齐的“食时”后端，为时令食材推荐、家常菜谱、AI 菜单规划、现有食材管理和购物清单提供统一 API 服务。
