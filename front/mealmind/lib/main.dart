import 'package:flutter/material.dart';

import 'pages/ai.dart';
import 'pages/foods.dart';
import 'pages/home.dart';
import 'pages/profile.dart';
import 'pages/recipes.dart';
import 'theme.dart';

void main() => runApp(const ShishiApp());

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

  void _selectTab(int index) => setState(() => _index = index);

  void _askAiWithFoods(List<String> foodNames) {
    setState(() {
      _pendingAiPrompt = '请用我选中的${foodNames.join('、')}推荐一顿家常饭';
      _aiRequestToken++;
      _index = 3;
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
          ),
          FoodsPage(onAskAi: _askAiWithFoods),
          const RecipesPage(),
          AiPage(
            initialPrompt: _pendingAiPrompt,
            requestToken: _aiRequestToken,
          ),
          const ProfilePage(),
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
