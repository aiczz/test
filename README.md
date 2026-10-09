# 食时 · 顺应时令的智慧饮食助手

> 全球校园人工智能算法精英大赛 · AI + 开源赛道
>
> **版本 v1.0.0** · 状态：可交付 · 更新日志见 [`CHANGELOG.md`](CHANGELOG.md)

「食时」是一款结合 AI 的时令饮食助手：从**当季食材**出发，推荐菜谱与菜单，管理家中现有食材，
生成购物清单，并由 AI 助手持续给出个性化建议。

回答两个问题：**今天吃什么**、**该买什么菜**。

---

## 〇、谁该看哪份文档

| 你是 | 看这个 |
|---|---|
| **要 push 代码的人** | [`docs/交付说明.md`](docs/交付说明.md) —— 一条命令 + push 前体检 |
| **要部署到服务器的人（运维）** | [`deploy/README.md`](deploy/README.md) —— 完整运维手册 |
| 想看算法 / AI 怎么设计的 | [`docs/算法与AI设计.md`](docs/算法与AI设计.md) |
| 想看这次改了什么 / 部署要注意什么 | [`CHANGELOG.md`](CHANGELOG.md) |
| 想知道哪些还没做（如实清单） | 本文档「六、当前进度」末尾 |

**交付状态**（截至 v1.0.0）：

| 检查 | 结果 |
|---|---|
| 后端 `python -m pytest` | 190 passed |
| 后端 `ruff --select F821,F811,F401,F841` | 干净 |
| 前端 `dart analyze lib test` | 干净 |
| 前端 `flutter test` | 10 passed |
| 验收脚本（49 项断言，逐条对应设计要求） | 全过 |
| 仓库体检 `python back/scripts/repo_health.py` | 无密钥泄漏、工作区干净 |

---

## 一、仓库结构

```
.
├── front/                                  ★ 前端
│   ├── mealmind/                             Flutter App（交付形态，能装到手机上）
│   │   ├── lib/                                Dart 源码
│   │   │   ├── main.dart                         入口 + 底部导航（5 个 tab）
│   │   │   ├── theme.dart                        设计 token（配色 / 圆角 / 阴影）
│   │   │   ├── state/app_state.dart            ★ 家庭档案共享状态（跨页流动）
│   │   │   ├── data/mock.dart                    内容假数据
│   │   │   ├── models/                           数据模型
│   │   │   ├── pages/                            页面
│   │   │   └── services/                         接口层 + 本地约束派生
│   │   ├── test/widget_test.dart               交互测试（CI 里会真的跑）
│   │   ├── assets/                             图片素材 + 菜单假数据
│   │   ├── web/ · android/ · ios/ …            各平台工程
│   │   └── README.md                           前端开发说明
│   ├── dist/                                 静态网页原型（HTML/CSS/JS，早期版本）
│   ├── docs/                                 项目文档（方案 / 接口契约 / 环境搭建）
│   ├── goat/front指南.txt                      需求与页面结构原始说明（1643 行）
│   ├── mock/plan.json                        菜单假数据（与 assets/mock/ 同源）
│   ├── scripts/                              环境安装脚本 + 图标生成脚本
│   ├── image/                                设计过程截图
│   └── README.md                             前端子目录的详细说明
│
├── back/                                  ★ 后端（可运行，不是"只有文档"）
│   ├── app/                                  FastAPI 应用
│   │   ├── main.py                             入口 + CORS + 建表 & 灌种子
│   │   ├── core/                               配置 / 数据库 / 安全 / 依赖注入
│   │   ├── api/routes/                         38 个接口，按业务分文件
│   │   ├── models/                             16 张表（SQLModel）
│   │   ├── schemas/ · repositories/ · services/ 响应模型 / 数据访问层 / 业务逻辑层
│   │   ├── ai/                               ★ 大模型客户端（DeepSeek / OpenAI 兼容）
│   │   └── data/seed.py                        种子数据（幂等）
│   ├── tests/                                120 个 pytest 用例 —— CI 里真的会跑
│   ├── scripts/verify_ai_features.py         ★ 验收脚本（49 项断言，给运维自检用）
│   ├── data_tools/                           数据清洗辅助脚本
│   ├── requirements.txt · README.md
│   └── 食时_App后端实现说明_Codex.md            后端实现说明（技术栈 / 表设计 / 接口规范 / 排期）
│
├── sql/                                  菜谱数据库的数据清洗交付（MySQL schema + CSV）
│
├── deploy/                                ★ 部署套件（给运维，照着跑就行）
│   ├── README.md                             部署手册（含排错对照表）
│   ├── deploy.sh                             一键部署脚本（幂等）
│   ├── nginx-shishi.conf                     静态站 + /api 反代（同源）
│   ├── shishi-backend.service                systemd 单元
│   └── local_preview.py                      本地复刻生产拓扑（验证同源用）
│
└── .github/workflows/
    ├── deploy-pages.yml                  CI：构建 Flutter Web 并发布到 GitHub Pages
    ├── build-web.yml                     CI：构建给自托管用的网页产物（同源，不含 IP）
    ├── build-apk.yml                     CI：构建安卓安装包（含后端地址）
    └── backend-tests.yml                 CI：跑后端 pytest


---

## 二、仓库里有三个部分，不要混淆

| | `front/mealmind/`（Flutter App） | `front/dist/`（网页原型） | `back/`（后端） |
|---|---|---|---|
| 技术 | Flutter + Dart | 静态 HTML/CSS/JS | Python / FastAPI + SQLModel |
| 定位 | **交付形态**，能装到手机 | 设计原型 / 交互参考 | 服务端 |
| 状态 | 开发中，可运行 | 早期版本，已定型 | **已实现**：14 张表 / 32 个接口 / 71 个测试 |
| 数据 | 读后端数据，后端离线时静默降级到本地 | 全部硬编码 | SQLite 开箱即跑，改一行 `DATABASE_URL` 切 PostgreSQL |

> **视觉与文案以 `dist/` 为准**，`mealmind/lib/theme.dart` 里的颜色值是从 `dist/styles.css`
> 的 `:root` 逐字抄过来的 —— 两边必须保持一致。

---

## 三、快速开始

### 环境要求

Flutter 3.47+ / Dart 3.13+ / Android SDK。

**首次搭建环境**（含国内镜像与 5 个常见坑的解法）：

```powershell
powershell -ExecutionPolicy Bypass -File "front/scripts/setup-flutter.ps1"
```

详见 [`front/docs/环境搭建踩坑记录.md`](front/docs/环境搭建踩坑记录.md)。

### 运行 App

```powershell
cd front/mealmind
flutter pub get
flutter run                 # 插上手机（需开 USB 调试）
flutter run -d chrome       # 或先在浏览器里看，不用等编译
```

### 跑测试

```powershell
cd front/mealmind
flutter test
```

### 打包

```powershell
flutter build apk --release                    # 安卓安装包
flutter build web --release --base-href "/test/"   # 网页版（演示保底）
```

---

## 四、开发约定

1. **假数据先行** —— 后端未就绪时不阻塞：`lib/data/mock.dart` 提供内容数据，
   `assets/mock/plan.json` 提供菜单数据。后端好了只改
   `lib/services/api.dart` 里的 `useMock = false`。
2. **组件化** —— 不要把页面写成几百行。重复元素抽组件
   （`FoodCard` / `RecipeCard` / `SectionHeader` / `TagChip`）。
3. **不引入状态管理框架** —— 当前规模用 `setState` 足够。
4. **接口失败不能白屏** —— 必须有错误提示 + 重试。
5. **颜色不要写死** —— 一律用 `lib/theme.dart` 里的常量。

---

## 五、文档索引

| 文档 | 内容 |
|---|---|
| [`deploy/README.md`](deploy/README.md) | **★ 部署手册**（运维照这份做：一键脚本 / nginx / systemd / 排错对照表） |
| [`front/README.md`](front/README.md) | 前端子目录详细说明（结构 / 启动 / 进度 / 部署） |
| [`front/goat/front指南.txt`](front/goat/front指南.txt) | 需求与页面结构（原始版，1643 行） |
| [`back/README.md`](back/README.md) | 后端说明（接口清单 / 算法 + AI 分工 / 知识库来源 / 排错） |
| [`back/食时_App后端实现说明_Codex.md`](back/食时_App后端实现说明_Codex.md) | 后端实现说明（表设计 + 接口规范 + 排期） |
| [`front/docs/项目方案.md`](front/docs/项目方案.md) | 技术方案：架构、算法、评测、排期 |
| [`front/docs/接口契约.md`](front/docs/接口契约.md) | 前后端接口约定（**待与现有接口合并**） |
| [`front/docs/环境搭建踩坑记录.md`](front/docs/环境搭建踩坑记录.md) | 新人照这份装环境，含 5 个坑的解法 |
| [`front/docs/前端-零基础上手路线.md`](front/docs/前端-零基础上手路线.md) | 前端 4 周实施路线 |

---

## 六、当前进度

> 更新于 **v1.0.0**（2026-10-06）。状态：**可交付** —— 后端 190 个测试、
> 前端 10 个测试、验收脚本 49 项断言全过（见 `CHANGELOG.md`）。

- [x] 环境搭建（Flutter + Android 工具链）
- [x] 应用骨架：底部导航 5 个 tab
- [x] 首页（Hero 轮播 + 家庭约束条 + 食材推荐 + 按条件能做的菜 + AI 建议 + 快捷入口）
- [x] 今日菜单 + 购物清单（按人数换算采购**数量**，不涉及价格）
- [x] 食材页 / 现有食材管理 / 食材详情
- [x] 菜谱页 / 菜谱详情（45 个归一化分类，点进去都有菜）
- [x] AI 助手（对话 + **推荐流程轨迹**）
- [x] 家庭档案（人数 / 每日可用烹饪时间 / 限钠 / 口味偏好 / 忌口 / 厨具）
- [x] ★ 家庭档案 **真的存得住**（本次）
      —— 内存 + 本机缓存 + 账号（`PUT /api/profile`）三层都写。
      以前只写内存，前端连 `/api/profile` 都没调过：在「我的」页把人数
      改成 5，切到首页 / AI 页看到的还是 3，刷新一下连「我的」页自己也变回 3。
- [x] ★ 家庭档案 → 菜单 / 购物清单 / 首页推荐 / AI 助手 **联动闭环**
      （改人数 / 限钠 / 忌口，切回各页会真的重算 —— 约束不是摆设；
      AI 请求里带的硬约束可以在轨迹的「读取约束」那一步看见）
- [x] 品牌应用图标（自适应图标，非 Flutter 默认蓝色图标）+ PWA 清单
- [x] 交互测试接入 CI（`flutter test` 是真实门禁，不是摆设）
- [x] ★ **后端**：FastAPI + SQLModel，**15 张表、37 个接口、190 个测试**
      （SQLite 开箱即跑，改一行 `DATABASE_URL` 即可切 PostgreSQL；
      后端测试在 CI 里真的会跑 —— 见 `backend-tests.yml`）
- [x] ★ **登录闭环**：注册 / 登录 / 手机验证码 / 演示账号一键登录 / token 持久化；
      **登录门禁** —— 未登录先看到登录页。
      （「演示账号一键登录」不受门禁影响，评委仍然一步就能进）
- [x] ★ **管理员后台**：用户统计 / 封禁与解封 / 登录记录（含失败尝试）
      —— 说明书里没有这一节，属于本次新增
- [x] ★ **前端业务数据接入后端，并保留静默降级**
      （后端不在线就用本地演示数据，界面照常能用、不弹错误；
      「我的食材」登录后同步到 `/api/my-foods`）
- [x] ★ **AI 助手接 `/api/ai/chat`**：回答由后端生成，后端离线时回落本地文案
- [x] ★ **首页推荐接「综合打分算法 + AI」**
      —— 后端按 **当天时令 + 定位城市天气 + 营养/标签 + 每日轮换因子** 从清洗库
      打分筛候选，再让大模型**在候选集内**挑选与解释。
      同地区同一天所有人看到的完全一致，**每天轮换**；
      AI 结果按 `(地区, 日期, 季节, 天气)` 落库缓存，**一个地区一天只调一次模型**。
      后端离线时首页自动退回本地规则，界面照常可用。
- [x] ★ **导航栏 AI 模块接上 AI**
      —— 「用我的食材配这一餐」：把你勾选的食材 + 今日菜单里已有的菜 +
      人数/可用时间/限钠/口味/忌口一起交给后端，
      后端先按食材召回候选（含硬约束过滤），再让大模型在候选内挑 3 道并写理由，
      一键加入今日菜单。
- [x] ★ **知识库就是我们的清洗库**
      —— AI 的解释全部建立在 `ingredients`（每 100g 营养 / 功效标签 / 中医宜忌）、
      `dishes`（整菜营养 / 标签）、`seasonal_calendar`（时令知识原文，
      如「秋季润肺，这样吃抗病魔！」）之上，不是模型的通用常识。
- [x] ★ **AI 不能凭空生成**
      —— 模型返回的 id 不在候选集里一律丢弃；忌口与可用时间由确定性代码
      在 AI **之前**硬筛，安全性不依赖模型。
      没配 `AI_API_KEY` 时全部退回算法，接口结构不变、不会 500。
- [x] ★ **token 失效自动登出**：任何接口返回 401（token 过期 / 账号被封禁）都会
      清掉本地登录态、回到登录页并说明原因，不会再卡在
      「显示着已登录、却什么都做不了」的状态
- [x] ★ **清洗数据已导入服务器**：线上 `ingredients` 8087 行（590 个核心食材）、
      `dishes` 10000 行、`dish_ingredients` 77886 行、时令表 596 行
- [x] ★ **菜谱分类归一化**（本次）
      —— 清洗库 985 个零散标签（「汤」「汤羹」「老火汤」…）归一成 **45 个规范分类**，
      分 8 组下发、只返回有菜的分类并带菜品数。
      10000 道菜里 **9996 道（99.96%）** 可被筛到。
      原先前端写死 `['快手菜','汤品','低脂','家常']`，和库里的
      「家常菜」「汤羹」对不上，所以点分类一道菜都筛不出来。
- [x] ★ **不再展示没有数据支撑的数字**（本次）
      —— 拿掉了三处「编出来的数据」：
      ① 价格（清洗库没有任何价格数据，原先的 ¥296 来自手写的 mock，
         却被标成「本地公示价格 · 置信度：高」）；
      ② 烹饪时长（`dishes` 没有时长列，43.9% 能从做法文本抽出、56.1% 是兜底的
         30 分钟 —— 现在没依据的显示「时长不详」而不是一个数字）；
      ③ 份量（`dishes` 没有份量列，原先每道菜都写死「3人份」，
         改家庭人数它一动不动）。

### 还没做（如实列出）

- [ ] 真 CP-SAT 求解器（当前由 `lib/services/local_estimator.dart` 本地派生顶上）
- [ ] 菜单 / 购物清单接 `/api/menu/*`（当前走 `services/api.dart` 的本地分支）
      —— ⚠️ 后端 `/api/menu/plan` 的响应结构与前端 `Plan.fromJson` 并不一致，
      直接改 `useMock = false` 会得到一张**空白菜单页**（字段全部回落到默认值），
      接它需要先写适配层
- [x] ~~价格管道~~ —— **明确不做**：清洗库里没有任何价格数据，
      要做得先有真实价格源。相关界面已全部移除，不做假的。
- [ ] 厨具（`tools`）存下来了但还没参与筛选 ——
      基准数据里没有「这道菜需要什么厨具」这个字段，硬造一条规则反而更假


### 关于「联动」是怎么实现的

`lib/state/app_state.dart` 是一个**零第三方依赖**的共享状态层（Flutter 自带的
`ChangeNotifier`），不违背上面第 4 节「不引入状态管理框架」的约定 ——
但家庭档案是**求解器的输入**，必须跨页面流动，`setState` 管不到别的页面。

```
profile.dart「保存」
   → AppState.saveProfile()
   → notifyListeners()
   → menu.dart  监听到 → 按新约束重算菜单与购物清单
   → home.dart  监听到 → 按新约束重挑首页推荐
   → ai.dart    下次提问时 → 协作轨迹读到的就是新档案
```

三个消费者用的都是**确定性规则**，不是 AI，也不假装是：

| 文件 | 规则 |
|---|---|
| `services/local_estimator.dart` | 人数缩放采购量与价格、限钠收紧钠上限、忌口过滤菜品 |
| `services/recommender.dart` → `pickForHome()` | 烹饪时间筛掉超时的菜、忌口过滤、低钠与口味偏好调序 |
| `services/recommender.dart` → `agentTraceFor()` | 用真实档案填充协作轨迹的「档案读取」「营养校验」两步 |

所以在默认档案（45 分钟 / 忌辛辣 / 低钠）下，首页的「按你的条件能做」
会把 60 分钟的「莲藕排骨汤」筛掉，并写明「已筛掉 1 道」—— 约束在首页是**看得见**的。

菜单页的求解结果**不是求解器也不是 AI**，界面上如实标注为
「本地估算（待接 CP-SAT 求解器）」。

---

## 六点五、算法 + AI 是怎么分工的

> 详细版（权重表、排错表、知识库来源）在 [`back/README.md` 第九节](back/README.md)。

**一句话：算法负责「选什么」，大模型负责「怎么说」。**

```
定位城市 ──→ 天气（Open-Meteo，免费无 key）
                │
时令（数据库）──┤
营养 / 标签   ──┼──→ 综合打分算法 ──→ 候选集（各 8 个）
家庭硬约束    ──┘         ▲                    │
                          │                    ▼
                          │         每天每地区【只问一次】大模型
                          │       （结果按 地区+日期+季节+天气 落库缓存）
                          └── 忌口/限钠/时间 在这里收口 ──→ 最终 3 + 3
```

**为什么不让 AI 直接从库里生成**：清洗库有 590 个核心食材、10000 道菜。
直接让模型「推荐几道」，它一定会编出不存在的菜名，或者推一道要炖三小时、
而家里只有 45 分钟的菜。现在的做法保证接口返回的每一道菜都真实存在于库里。

**「同地区同一天一样、跨天不一样」怎么做到的**：
每日轮换因子是 `sha256(地区 + 日期 + 条目名)` —— 确定性函数。
同地区 + 同日期永远算出同一个值，所以那天所有人看到的顺序完全一致
（也正因此，那一次 AI 调用可以按地区共享，token 省下来）；
日期一变，因子全变，排序就换了。

**AI 的知识库就是我们自己的数据**（这是原创性与开源性的落点）：

| 来源 | 内容 |
|---|---|
| `ingredients` | 每 100g 营养、功效标签、中医宜忌、适宜人群（8087 行 / 590 个核心食材）|
| `dishes` | 整菜营养（已按配料克重算好）、标签（10000 行）|
| `seasonal_calendar` | **时令知识原文**：「秋季（9月-11月）的应季蔬菜共 24 种…」「秋季润肺，这样吃抗病魔！」|
| `seasonal_food` | 逐条时令食材与推荐理由（544 行）|

### ⚠️ 部署时 AI 的 key 怎么给

**不要把 key 提交进仓库。** 仓库是公开的，提交进去几分钟内就会被爬走盗刷。
`back/.env` 已在 `.gitignore` 里，这是有意的。

服务器上（`/opt/test/back/.env`）：

```env
AI_ENABLED=true
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=<把 key 单独发给运维同学，不要走 git>
AI_MODEL=deepseek-chat
AI_JSON_MODE=true
WEATHER_ENABLED=true
```

**key 不填也能跑** —— 首页与 AI 助手会自动退回确定性算法，
只是少了 AI 润色和候选内的智能挑选。所以「忘了配 key」不是一次事故。

#### 以后要换 AI 服务商

后端走的是 **OpenAI Chat Completions 协议**，所以通义千问 / 智谱 / Kimi /
本地 Ollama 这些兼容服务都只是**改 `.env` 三行**（`AI_BASE_URL` /
`AI_API_KEY` / `AI_MODEL`），代码一行不用动：

| 服务商 | `AI_BASE_URL` | 模型名示例 |
|---|---|---|
| DeepSeek（当前） | `https://api.deepseek.com` | `deepseek-chat` |
| 阿里通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| 月之暗面 Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` |

两个坑：

- **`AI_BASE_URL` 要填到「版本前缀」为止** —— 代码是拿它拼
  `{AI_BASE_URL}/chat/completions`，多数服务少了 `/v1` 会 404。
- **本地部署的模型一般要把 `AI_JSON_MODE` 设成 `false`** ——
  `response_format={"type":"json_object"}` 是 OpenAI 的扩展，不是所有
  「兼容 OpenAI」的实现都支持；对方不认时直接 400，而客户端不抛异常
  → 表现为「AI 悄悄降级」，很难查。

**改完一定先自检**（会真的发一次请求，失败时直接告诉你该改哪一项）：

```bash
cd back && python scripts/check_ai.py
```

> 为什么必须自检：客户端**永不抛异常** —— AI 失败只是悄悄退回算法
> （首页不能因为 AI 挂掉而 500）。代价是配错了界面上看不出来：
> 页面照常开、菜照样有，只是少了 AI 润色那一段。
>
> 换模型后首页的每日缓存会**自动失效**（缓存键里带了模型名），不用手工清。

---

## 七、部署到公网（GitHub Pages）

CI 已配好：push 到 `main` 会自动跑 analyze → test → build，并发布到 GitHub Pages。
本地不用装任何工具链。

**预期地址**：`https://aiczz.github.io/test/`

### 首次启用（只需做一次）

1. Settings → General → 拉到底 → **Change visibility → Make public**
   —— 免费版组织的私有仓库**不能**用 GitHub Pages。
2. Settings → Pages → **Source 选 "GitHub Actions"**。
3. 推一次 `main`，或在 Actions 页手动运行 `Deploy Web`。

### 改了仓库名怎么办

`.github/workflows/deploy-pages.yml` 里的 `--base-href "/test/"` 要同步改成新仓库名。
GitHub Pages 项目站点发在 `/<仓库名>/` 这个**子路径**下，不是域名根路径 ——
**这一行不改，页面就是白屏**，而且控制台只会报一堆 404，很难查。

### 排错

| 现象 | 原因 |
|---|---|
| 页面全白 + 控制台一堆 404 | `--base-href` 和仓库名不一致 |
| deploy 报 `Pages site not found` | Settings → Pages 里没选 "GitHub Actions" |
| build 报仓库不可用 | 仓库还是 private |
| 首次打开白屏较久 | Flutter Web 首次要下约 10MB（`main.dart.js` + `canvaskit.wasm`），之后走缓存 |
| build 挂在 test 这一步 | `flutter test` 没过。测试是真的门禁，去 Actions 日志看是哪条断言失败 |

> ⚠️ GitHub Pages 那份**没有后端**（Pages 只发静态文件），所以它靠前端的
> 「静默降级」跑本地演示数据。要真正跑通前后端，用下面这节的自托管部署。

---

## 七点五、部署到自己的服务器（自托管 · 交付给运维）

**完整手册在 [`deploy/README.md`](deploy/README.md)**，这里只给结论。

### 运维要做的就两行

```bash
cd /opt/test && sudo git pull
sudo bash deploy/deploy.sh
```

`deploy.sh` 是幂等的，会自动做完：装依赖 → 建库 → 导入菜谱内容数据 →
注册 systemd 服务 → 下载前端产物 → 配 nginx → 自检。

### ★ 前端走「同源」，产物里不含任何 IP

这是本次为了让「pull 下来就能用」成立做的关键改动：

```
浏览器 ─┬─ /       → 前端静态产物
        └─ /api/   → 后端 uvicorn（nginx 反代）
```

前端调的是**页面所在来源**的 `/api`，不再把服务器 IP 编进包里。所以：

- 换服务器 / 换 IP / 换域名 / 上 HTTPS —— **都不用重新构建前端**
- 天然没有 mixed content（页面和接口同源）

> 以前 `build-web.yml` 里写死了 `--dart-define=API_BASE=http://8.148.69.56:8000`，
> 换个 IP 就得改这行再构建一次，是个很容易忘的坑。现在这行已经删掉了。
>
> **APK 不一样**：原生应用没有「页面来源」，必须把绝对地址编进包里，
> 所以 `build-apk.yml` 里那个 `--dart-define` 是必要的 —— 换服务器时要改。

### 那两个必须人工填的值

| 值 | 怎么来 |
|---|---|
| `SECRET_KEY` | `deploy.sh` 会自动换成随机值（默认值能被人伪造管理员登录）|
| `AI_API_KEY` | **不在仓库里**，必须单独问项目负责人要，填进服务器上的 `back/.env` |

`AI_API_KEY` 不填也能跑，只是首页推荐和 AI 助手会退回确定性算法。

### 本地复刻生产拓扑（改前端时用）

不用装 nginx 也能在本地验证同源这条路：

```bash
# 终端 1
cd back && python -m uvicorn app.main:app --port 8000
# 终端 2
python deploy/local_preview.py            # 打开 http://127.0.0.1:8080
```

它做的就是 nginx 那两件事（静态站 + `/api` 反代），行为一致。

---

## 八、开源许可证

本项目采用 [MIT 许可证](LICENSE)。
