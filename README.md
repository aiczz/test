# 食时 · 顺应时令的智慧饮食助手

> 全球校园人工智能算法精英大赛 · AI + 开源赛道

「食时」是一款结合 AI 的时令饮食助手：从**当季食材**出发，推荐菜谱与菜单，管理家中现有食材，
生成购物清单，并由 AI 助手持续给出个性化建议。

回答两个问题：**今天吃什么**、**该买什么菜**。

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
├── back/                                  后端
│   └── 食时_App后端实现说明_Codex.md           后端实现说明（技术栈 / 表设计 / 接口规范 / 排期）
│
└── .github/workflows/deploy-pages.yml     CI：构建 Flutter Web 并发布到 GitHub Pages
```

---

## 二、仓库里有三个部分，不要混淆

| | `front/mealmind/`（Flutter App） | `front/dist/`（网页原型） | `back/`（后端） |
|---|---|---|---|
| 技术 | Flutter + Dart | 静态 HTML/CSS/JS | Python / FastAPI（**仅说明文档**） |
| 定位 | **交付形态**，能装到手机 | 设计原型 / 交互参考 | 服务端 |
| 状态 | 开发中，可运行 | 早期版本，已定型 | 待实现 |
| 数据 | 先读假数据，后端就绪后切真接口 | 全部硬编码 | — |

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
| [`front/README.md`](front/README.md) | 前端子目录详细说明（结构 / 启动 / 进度 / 部署） |
| [`front/goat/front指南.txt`](front/goat/front指南.txt) | 需求与页面结构（原始版，1643 行） |
| [`back/食时_App后端实现说明_Codex.md`](back/食时_App后端实现说明_Codex.md) | 后端实现说明（13 张表 + 32 节接口规范 + P0/P1 排期） |
| [`front/docs/项目方案.md`](front/docs/项目方案.md) | 技术方案：架构、算法、评测、排期 |
| [`front/docs/接口契约.md`](front/docs/接口契约.md) | 前后端接口约定（**待与现有接口合并**） |
| [`front/docs/环境搭建踩坑记录.md`](front/docs/环境搭建踩坑记录.md) | 新人照这份装环境，含 5 个坑的解法 |
| [`front/docs/前端-零基础上手路线.md`](front/docs/前端-零基础上手路线.md) | 前端 4 周实施路线 |

---

## 六、当前进度

- [x] 环境搭建（Flutter + Android 工具链）
- [x] 应用骨架：底部导航 5 个 tab
- [x] 首页（Hero 轮播 + 家庭约束条 + 食材推荐 + 按条件能做的菜 + AI 建议 + 快捷入口）
- [x] 今日菜单 + 购物清单（含三档价格来源与置信度标注）
- [x] 食材页 / 现有食材管理 / 食材详情
- [x] 菜谱页 / 菜谱详情
- [x] AI 助手（多智能体协作轨迹）
- [x] 家庭设置（人数 / 预算 / 慢病 / 忌口 / 厨具 / 时间）
- [x] ★ 家庭档案 → 菜单 / 购物清单 **联动闭环**
      （改人数/预算/限钠，切回菜单页会真的重算 —— 约束不是摆设）
- [x] ★ 家庭档案 → **首页推荐**也联动（按烹饪时间筛掉超时的菜、按忌口过滤、
      低钠与口味偏好调序）—— 首页不再是写死的静态样板
- [x] ★ 家庭档案 → **AI 协作轨迹**也联动（轨迹读的是真实档案；
      关掉低钠约束，Critic 就不再否决方案 B）
- [x] 品牌应用图标（自适应图标，非 Flutter 默认蓝色图标）+ PWA 清单
- [x] 交互测试接入 CI（`flutter test` 是真实门禁，不是摆设）
- [ ] 真 CP-SAT 求解器（当前由 `lib/services/local_estimator.dart` 本地派生顶上）
- [ ] 后端接口接入（`lib/services/api.dart` 的 `useMock` 改成 `false`）
- [ ] 「我的食材」提升为跨页共享状态（目前是食材页内的局部状态）

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
