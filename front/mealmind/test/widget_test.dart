import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:mealmind/main.dart';
import 'package:mealmind/pages/admin.dart';
import 'package:mealmind/pages/login.dart';
import 'package:mealmind/services/api_config.dart';
import 'package:mealmind/services/auth_store.dart';
import 'package:mealmind/state/today_menu.dart';

void main() {
  testWidgets('五个主入口可用，食材可添加到我的库存', (tester) async {
    // 每个用例使用独立的根节点，避免复用上一个用例停留的 tab 和滚动位置。
    await tester.pumpWidget(ShishiApp(key: UniqueKey()));

    expect(find.text('今天吃什么'), findsOneWidget);
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('首页'), findsOneWidget);
    expect(find.text('食材'), findsOneWidget);
    expect(find.text('菜谱'), findsOneWidget);
    expect(find.text('AI'), findsOneWidget);
    expect(find.text('我的'), findsOneWidget);

    final homeCarousel = find.byType(PageView).first;
    await tester.drag(homeCarousel, const Offset(-360, 0));
    await tester.pumpAndSettle();
    expect(find.text('看看家里\n有什么'), findsOneWidget);
    expect(find.text('管理我的食材'), findsOneWidget);

    await tester.drag(homeCarousel, const Offset(-360, 0));
    await tester.pumpAndSettle();
    expect(find.text('不知道吃什么？\n问问 AI'), findsOneWidget);
    expect(find.text('打开 AI 助手'), findsOneWidget);

    await tester.tap(find.text('食材'));
    await tester.pumpAndSettle();

    // 页头大标题、tab、列表标题都会出现「全部食材」，所以不限定数量。
    expect(find.text('全部食材'), findsWidgets);
    // 「时令」现在是和蔬菜/肉蛋/水产并列的一个分类，不再是 tab 名。
    expect(find.text('时令'), findsOneWidget);
    expect(find.text('全部'), findsOneWidget);
    expect(find.text('蔬菜'), findsOneWidget);
    expect(find.text('肉蛋'), findsOneWidget);
    expect(find.text('水产'), findsOneWidget);
    expect(find.text('豆制品'), findsOneWidget);

    expect(find.text('我的 0'), findsOneWidget);
    final addButton = find.byTooltip('添加到我的食材').first;
    await tester.ensureVisible(addButton);
    await tester.pumpAndSettle();
    await tester.tap(addButton);
    await tester.pumpAndSettle();

    final removeButton = find.byTooltip('从我的食材中移除').first;
    expect(removeButton, findsOneWidget);
    await tester.tap(removeButton);
    await tester.pumpAndSettle();

    // 卡片滚入视口后页头已经被 ListView 回收，这里验证按钮确实恢复为“+”。
    expect(find.byTooltip('添加到我的食材'), findsWidgets);

    final addAgainButton = find.byTooltip('添加到我的食材').first;
    await tester.tap(addAgainButton);
    await tester.pumpAndSettle();
    expect(find.byTooltip('从我的食材中移除'), findsOneWidget);
    await tester.drag(find.byType(ListView).first, const Offset(0, 800));
    await tester.pumpAndSettle();
    expect(find.text('我的 1'), findsOneWidget);
    await tester.tap(find.text('我的 1'));
    await tester.pumpAndSettle();

    expect(find.text('莲藕'), findsOneWidget);
    expect(find.text('1'), findsOneWidget);
    expect(find.textContaining('节'), findsNothing);
    expect(find.byTooltip('删除莲藕'), findsOneWidget);
  });

  testWidgets('个人页统计卡可进入库存并编辑口味', (tester) async {
    await tester.pumpWidget(ShishiApp(key: UniqueKey()));

    await tester.tap(find.text('我的'));
    await tester.pumpAndSettle();

    final preferencesCard = find.text('口味偏好').first;
    await tester.scrollUntilVisible(
      preferencesCard,
      180,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(preferencesCard);
    await tester.pumpAndSettle();
    expect(find.text('编辑口味偏好'), findsOneWidget);
    expect(find.text('保存设置'), findsOneWidget);

    await tester.tap(find.text('保存设置'));
    await tester.pumpAndSettle();

    final pantryCard = find.text('我的食材').first;
    await tester.scrollUntilVisible(
      pantryCard,
      -120,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(pantryCard);
    await tester.pumpAndSettle();
    expect(find.text('我家的食材'), findsWidgets);
  });

  testWidgets('首页快速选一餐打开轻量推荐面板', (tester) async {
    await tester.pumpWidget(ShishiApp(key: UniqueKey()));

    final quickMeal = find.text('快速选一餐');
    await tester.scrollUntilVisible(
      quickMeal,
      260,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(quickMeal);
    await tester.pumpAndSettle();

    expect(find.text('今日一餐灵感'), findsOneWidget);
    expect(find.text('换一个'), findsOneWidget);
    expect(find.text('查看做法'), findsOneWidget);
    expect(find.text('让 AI 帮我搭配'), findsOneWidget);
  });

  testWidgets('手机号注册成功后自动登录并通过入口门禁', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    BackendStatus.instance.setOfflineForTesting();
    await AuthStore.instance.logout();
    var authenticated = false;

    await tester.pumpWidget(
      MaterialApp(
        home: LoginPage(
          gateMode: true,
          onAuthenticated: () => authenticated = true,
        ),
      ),
    );

    expect(find.text('创建你的账号'), findsOneWidget);
    expect(find.text('手机验证码'), findsNothing);
    expect(find.text('账号密码'), findsNothing);

    await tester.enterText(find.byType(TextFormField).at(0), '13800138000');
    await tester.tap(find.text('获取验证码'));
    await tester.pump();
    expect(find.text('演示验证码已发送：123456'), findsOneWidget);

    await tester.enterText(find.byType(TextFormField).at(1), '123456');
    await tester.enterText(find.byType(TextFormField).at(2), '246810');
    await tester.enterText(find.byType(TextFormField).at(3), '246810');
    await tester.scrollUntilVisible(
      find.text('完成注册'),
      220,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('完成注册'));
    await tester.pump(const Duration(milliseconds: 500));

    expect(authenticated, isTrue);
    expect(AuthStore.instance.isLoggedIn, isTrue);
    await AuthStore.instance.logout();
  });

  testWidgets('管理员演示账号可登录并打开新版控制台', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await AuthStore.instance.logout();
    await AuthStore.instance.login(
      AuthStore.adminUsername,
      AuthStore.adminPassword,
    );

    expect(AuthStore.instance.user?.isAdmin, isTrue);

    await tester.pumpWidget(const MaterialApp(home: AdminPage()));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('食时管理台'), findsOneWidget);
    expect(find.text('演示数据'), findsOneWidget);
    expect(find.text('总览'), findsOneWidget);
    expect(find.text('用户管理'), findsOneWidget);
    expect(find.text('登录安全'), findsOneWidget);
    expect(find.text('早上好，食时管理员'), findsOneWidget);

    await tester.tap(find.text('用户管理'));
    await tester.pumpAndSettle();
    expect(find.text('受限账号示例'), findsOneWidget);

    await tester.tap(find.text('登录安全'));
    await tester.pumpAndSettle();
    expect(find.textContaining('登录活动'), findsOneWidget);
    expect(find.text('只看失败'), findsOneWidget);

    await AuthStore.instance.logout();
  });

  testWidgets('菜谱详情加入今日菜单后，菜谱页「今日菜单」tab 能看到', (tester) async {
    // 这个用例锁住的原本是一个空按钮：
    // 「加入今日菜单」以前只弹一句提示、什么都不存，
    // 界面上也没有任何地方能看到加进去的菜。
    //
    // TodayMenuStore 是全局单例，用例之间会互相影响，先清一下。
    TodayMenuStore.instance.clear();

    await tester.pumpWidget(ShishiApp(key: UniqueKey()));

    await tester.tap(find.text('菜谱'));
    await tester.pumpAndSettle();

    // 两个 tab 都在，且默认停在「全部菜谱」那一侧
    expect(find.text('全部菜谱'), findsWidgets);
    expect(find.text('今日菜单 0'), findsOneWidget);

    // 打开第一道菜的详情，加入今日菜单
    final firstRecipe = find.text('莲藕排骨汤').first;
    await tester.ensureVisible(firstRecipe);
    await tester.pumpAndSettle();
    await tester.tap(firstRecipe);
    await tester.pumpAndSettle();

    // 详情内容比屏幕高，按钮在底部，要先滚到它再点 ——
    // 直接 tap 会因为落点在视口外而「点空」，测试却不会因此报错。
    final addButton = find.text('加入今日菜单');
    expect(addButton, findsOneWidget);
    await tester.ensureVisible(addButton);
    await tester.pumpAndSettle();
    await tester.tap(addButton);
    await tester.pumpAndSettle();

    // 先把「数据没写进 store」和「写进去了但界面没刷新」区分开
    expect(
      TodayMenuStore.instance.count,
      1,
      reason: '「加入今日菜单」没有把菜写进 TodayMenuStore',
    );

    // ⚠️ 上面那句 ensureVisible 把列表滚下去过，页头和 tab 已经被 ListView
    //    回收掉了，所以先滚回顶部 —— 否则这里失败的原因会是「滚得太靠下」，
    //    而不是「计数没更新」，能白查半天。
    await tester.drag(find.byType(ListView).first, const Offset(0, 900));
    await tester.pumpAndSettle();

    // 详情关掉后回到菜谱页，计数变成 1
    expect(find.text('今日菜单 1'), findsOneWidget);

    await tester.tap(find.text('今日菜单 1'));
    await tester.pumpAndSettle();
    expect(find.text('莲藕排骨汤'), findsOneWidget);

    // 清空后应该回到空状态，而不是留一片空白
    await tester.tap(find.text('清空'));
    await tester.pumpAndSettle();
    expect(find.textContaining('今日菜单还是空的'), findsOneWidget);

    TodayMenuStore.instance.clear();
  });

  testWidgets('首页能进本周菜单，也能返回', (tester) async {
    // 这一页此前完全没有入口（死代码）：底部导航里没有它，
    // 也没有任何按钮指向它，但「我的」页一直对用户说「菜单已重算」。
    await tester.pumpWidget(ShishiApp(key: UniqueKey()));

    // 入口在首页底部，而 ListView 不会构建视口外的项 ——
    // 不先滚下去，find 会直接抛 "Bad state: No element"。
    await tester.drag(find.byType(ListView).first, const Offset(0, -800));
    await tester.pumpAndSettle();

    final entry = find.text('本周菜单');
    expect(entry, findsOneWidget);
    await tester.tap(entry);
    await tester.pumpAndSettle();

    // 真的进到菜单页了：这是那一页独有的标题
    expect(find.text('本次求解采用的约束'), findsOneWidget);

    // 返回首页（AppBar 自动给的返回按钮）
    await tester.pageBack();
    await tester.pumpAndSettle();
    // 首页回来了：底部导航始终可见，用它判断最稳
    // （此刻首页停在底部，页头「今天吃什么」已经滚出视口了）
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('本周菜单'), findsOneWidget);
  });
}
