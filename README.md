# 食时 · 顺应时令的智慧饮食助手

> 全球校园人工智能算法精英大赛 · AI+开源赛道

「食时」是一款结合 AI 的时令饮食助手：从**当季食材**出发，推荐菜谱与菜单，管理家中现有食材，生成购物清单，并由 AI 助手持续给出个性化建议。

---

## 一、仓库结构

```
.
├── mealmind/          ★ Flutter App（当前主力开发）
│   ├── lib/             Dart 源码
│   │   ├── main.dart          应用入口 + 底部导航（5 个 tab）
│   │   ├── theme.dart         ★ 设计 token（配色/圆角/阴影）
│   │   ├── data/mock.dart     假数据（接口未就绪时前端先用它）
│   │   ├── models/            数据模型
│   │   ├── pages/             页面
│   │   └── services/          接口层
│   └── assets/         图片素材 + 假数据
│
├── dist/              网页原型（HTML/CSS/JS，早期版本）
├── front/             前端实现说明（1643 行，需求与页面结构）
├── docs/              项目文档（方案 / 接口契约 / 环境搭建 / 评审）
├── scripts/           环境安装脚本
├── mock/              接口假数据（plan.json）
└── image/             设计过程截图
```

---

## 二、关于两个前端形态

仓库里目前有**两套前端**，不要混淆：

| | `dist/`（网页原型） | `mealmind/`（Flutter App） |
|---|---|---|
| 技术 | 静态 HTML/CSS/JS | Flutter + Dart |
| 定位 | **设计原型 / 交互参考** | **交付形态**（能装到手机上） |
| 状态 | 早期版本，已定型 | 开发中 |
| 数据 | 全部硬编码 | 先读假数据，后端就绪后切真接口 |

> **视觉与文案以 `dist/` 为准，`mealmind/lib/theme.dart` 里的颜色值是从
> `dist/styles.css` 的 `:root` 逐字抄过来的** —— 两边必须保持一致。

---

## 三、快速开始

### 环境要求

Flutter 3.47+ / Dart 3.13+ / Android SDK。

**首次搭建环境**（含国内镜像与 5 个常见坑的解法）：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/setup-flutter.ps1"
```

详见 [`docs/环境搭建踩坑记录.md`](docs/环境搭建踩坑记录.md)。

### 运行 App

```powershell
cd mealmind
flutter pub get
flutter run                 # 插上手机（需开 USB 调试）
flutter run -d chrome       # 或先在浏览器里看，不用等编译
```

### 打包

```powershell
flutter build apk --release   # 安卓安装包
flutter build web             # 网页版（演示保底）
```

---

## 四、前端开发约定

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
| [`front/front指南.txt`](front/front指南.txt) | 需求与页面结构（原始版，1643 行） |
| [`docs/项目方案.md`](docs/项目方案.md) | 技术方案：架构、算法、评测、排期 |
| [`docs/接口契约.md`](docs/接口契约.md) | 前后端接口约定（**待与现有接口合并**） |
| [`docs/环境搭建踩坑记录.md`](docs/环境搭建踩坑记录.md) | 新人照这份装环境，含 5 个坑的解法 |
| [`docs/前端-零基础上手路线.md`](docs/前端-零基础上手路线.md) | 前端 4 周实施路线 |
| [`docs/评审-队友架构方案.md`](docs/评审-队友架构方案.md) | 早期架构评审记录 |

---

## 六、当前进度

- [x] 环境搭建（Flutter + Android 工具链）
- [x] 应用骨架：底部导航 5 个 tab
- [x] 首页（Hero + 食材推荐 + 菜谱推荐 + AI 建议）
- [x] 今日菜单 + 购物清单
- [x] 食材页 / 现有食材管理 / 食材详情
- [x] 菜谱页 / 菜谱详情
- [x] AI 助手（多智能体协作轨迹）
- [x] 家庭设置（人数 / 预算 / 慢病 / 忌口 / 厨具 / 时间）
- [ ] 后端接口接入
