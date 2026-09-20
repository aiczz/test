import 'package:flutter/material.dart';

import 'models/content.dart';
import 'pages/ai.dart';
import 'pages/foods.dart';
import 'pages/home.dart';
import 'pages/profile.dart';
import 'pages/recipes.dart';
import 'services/api_config.dart';
import 'services/auth_store.dart';
import 'services/content_store.dart';
import 'theme.dart';

Future<void> main() async {
  // shared_preferences 需要先初始化绑定
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const _Bootstrap());
}

/// 启动流程：先显示品牌屏，同时在后台把登录状态、后端探测、内容数据准备好，
/// 准备好了再切到真正的 App。
///
/// 为什么改成这样：以前是在 runApp 之前 await 这三件事，用户会盯着**纯白屏**
/// 最多 2 秒（后端探测的超时）。现在至少看到的是品牌屏 —— 白屏改成品牌屏，
/// 观感差别很大，尤其是答辩投影的时候。
class _Bootstrap extends StatefulWidget {
  const _Bootstrap();

  @override
  State<_Bootstrap> createState() => _BootstrapState();
}

class _BootstrapState extends State<_Bootstrap> {
  late final Future<void> _ready = _prepare();

  Future<void> _prepare() async {
    // 恢复上次的登录状态（token 存在本地）
    await AuthStore.instance.restore();
    // 探测后端；在线就把内容数据也拉下来
    await BackendStatus.instance.probe();

    // ★ 后端在线就顺手刷新一次用户信息。
    //   本地缓存的用户 JSON 可能是旧版本写下的 —— 比如 is_admin 是后加的
    //   字段，老缓存里没有它，管理员登着也看不到「管理」入口。
    //   刷这一次就能自愈，不用让用户手动退出重登。
    if (BackendStatus.instance.online) {
      await AuthStore.instance.refreshUser();
    }

    await ContentStore.instance.load();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<void>(
      future: _ready,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.done) {
          return const ShishiApp();
        }
        return const _SplashScreen();
      },
    );
  }
}

/// 启动屏。只用到 theme.dart 里已有的 token，视觉和 App 内保持一致。
class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        backgroundColor: page,
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 74,
                height: 74,
                decoration: BoxDecoration(
                  color: green700,
                  borderRadius: BorderRadius.circular(22),
                  boxShadow: cardShadow,
                ),
                child: const Icon(Icons.rice_bowl, size: 38, color: cream),
              ),
              const SizedBox(height: 20),
              const Text(
                '食时',
                style: TextStyle(
                  fontSize: 27,
                  fontWeight: FontWeight.w900,
                  color: green900,
                  letterSpacing: -1.2,
                  height: 1,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                '顺应时令 · 智慧饮食',
                style: TextStyle(
                  fontSize: 10.5,
                  color: green700,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                ),
              ),
              const SizedBox(height: 26),
              const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: green700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 食时 · 顺应时令的智慧饮食助手
class ShishiApp extends StatelessWidget {
  const ShishiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '食时',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        // 主色用队友那套深绿
        colorScheme: ColorScheme.fromSeed(
          seedColor: green700,
          primary: green700,
        ),
        scaffoldBackgroundColor: page,
        appBarTheme: const AppBarTheme(
          backgroundColor: page,
          foregroundColor: ink,
          elevation: 0,
          centerTitle: false,
        ),
        navigationBarTheme: NavigationBarThemeData(
          backgroundColor: Colors.white,
          surfaceTintColor: Colors.white,
          indicatorColor: Colors.transparent,
          elevation: 0,
          labelTextStyle: WidgetStateProperty.resolveWith((states) {
            final selected = states.contains(WidgetState.selected);
            return TextStyle(
              color: selected ? green700 : muted,
              fontSize: 11,
              fontWeight: selected ? FontWeight.w800 : FontWeight.w500,
            );
          }),
        ),
        // 中文优先用系统的苹方 / 微软雅黑
        fontFamily: null,
      ),
      home: const RootShell(),
      // 桌面浏览器 / 平板上，把界面限制成「手机宽度」居中显示。
      // 两个好处：
      //   1. 看起来就是一台手机，答辩投影时更像 App
      //   2. ★ 图片不会被拉宽 —— 源图只有 230~458 px，一拉宽就糊
      builder: (context, child) {
        return ColoredBox(
          color: const Color(0xFFE6ECE2),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 430),
              child: child ?? const SizedBox.shrink(),
            ),
          ),
        );
      },
    );
  }
}

// =====================================================================
// 底部导航（对应队友原型里的 5 个一级入口）
// =====================================================================

class _TabItem {
  final IconData icon;
  final IconData activeIcon;
  final String label;

  const _TabItem(this.icon, this.activeIcon, this.label);
}

const _tabs = <_TabItem>[
  _TabItem(Icons.eco_outlined, Icons.eco, '首页'),
  _TabItem(Icons.local_florist_outlined, Icons.local_florist, '食材'),
  _TabItem(Icons.menu_book_outlined, Icons.menu_book, '菜谱'),
  _TabItem(Icons.auto_awesome_outlined, Icons.auto_awesome, 'AI助手'),
  _TabItem(Icons.person_outline, Icons.person, '我的'),
];

class RootShell extends StatefulWidget {
  const RootShell({super.key});

  @override
  State<RootShell> createState() => _RootShellState();
}

class _RootShellState extends State<RootShell> {
  int _index = 0;
  int _aiRequestToken = 0;
  String? _pendingAiPrompt;

  /// 食材页的 State —— 首页的食材卡片靠它打开同一个详情弹层
  final GlobalKey<FoodsPageState> _foodsKey = GlobalKey<FoodsPageState>();

  void _selectTab(int index) => setState(() => _index = index);

  void _askAiWithFoods(List<String> foodNames) {
    setState(() {
      _pendingAiPrompt = '请用我选中的${foodNames.join('、')}推荐一顿家常饭';
      _aiRequestToken++;
      _index = 3;
    });
  }

  /// 首页点到食材卡片：先切到食材页，再打开它的详情弹层。
  void _openFoodDetail(Food food) {
    setState(() => _index = 1);
    // 等这一帧切完再弹 —— 否则弹层会挂在还没显示出来的页面上
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _foodsKey.currentState?.openFoodDetail(food);
    });
  }

  void _openPantry() {
    setState(() => _index = 1);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _foodsKey.currentState?.openPantry();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // IndexedStack 会保留每个页面的滚动位置，切回来不会跳顶
      body: IndexedStack(
        index: _index,
        children: [
          HomePage(
            onOpenFoods: () => _selectTab(1),
            onOpenRecipes: () => _selectTab(2),
            onOpenAi: () => _selectTab(3),
            onOpenProfile: () => _selectTab(4),
            onOpenFoodDetail: _openFoodDetail,
          ),
          FoodsPage(key: _foodsKey, onAskAi: _askAiWithFoods),
          const RecipesPage(),
          AiPage(
            initialPrompt: _pendingAiPrompt,
            requestToken: _aiRequestToken,
          ),
          ProfilePage(
            onOpenRecipes: () => _selectTab(2),
            onOpenPantry: _openPantry,
          ),
        ],
      ),
      bottomNavigationBar: DecoratedBox(
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(top: BorderSide(color: line)),
        ),
        child: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: _selectTab,
          backgroundColor: Colors.white,
          surfaceTintColor: Colors.white,
          indicatorColor: Colors.transparent,
          height: 68,
          labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
          destinations: <NavigationDestination>[
            for (final t in _tabs)
              NavigationDestination(
                icon: Icon(t.icon, color: muted, size: 22),
                selectedIcon: Icon(t.activeIcon, color: green700, size: 22),
                label: t.label,
              ),
          ],
        ),
      ),
    );
  }
}
