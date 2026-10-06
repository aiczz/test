import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:mealmind/main.dart';
import 'package:mealmind/models/content.dart';
import 'package:mealmind/pages/admin.dart';
import 'package:mealmind/pages/foods.dart';
import 'package:mealmind/pages/login.dart';
import 'package:mealmind/services/api_config.dart';
import 'package:mealmind/services/auth_store.dart';
import 'package:mealmind/services/content_store.dart';
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

  testWidgets('注册页用邮箱验证码，离线时明确拒绝而不是假装通过', (tester) async {
    // 验证码机制是真的（后端随机生成、有 TTL / 限流 / 防重放，见
    // back/tests/test_verification.py），所以前端离线时【不能】再给一个
    // 本地闭环 —— 收不到邮件就是收不到，弹一句"演示验证码 123456"才是骗人。
    // 这个用例就锁住这个行为。
    SharedPreferences.setMockInitialValues(<String, Object>{});
    BackendStatus.instance.setOfflineForTesting();
    await AuthStore.instance.logout();

    await tester.pumpWidget(
      MaterialApp(
        home: LoginPage(gateMode: true, onAuthenticated: () {}),
      ),
    );

    expect(find.text('创建你的账号'), findsOneWidget);
    expect(find.text('手机验证码'), findsNothing);
    expect(find.text('账号密码'), findsNothing);
    // 第一个字段已经换成邮箱
    expect(find.text('邮箱'), findsOneWidget);
    expect(find.text('手机号'), findsNothing);

    await tester.enterText(find.byType(TextFormField).at(0), 'cook@example.com');
    await tester.tap(find.text('获取验证码'));
    await tester.pump();

    // ★ 离线必须说清楚"需要后端"，且绝不能出现任何形式的假验证码
    expect(find.textContaining('离线'), findsOneWidget);
    expect(find.textContaining('123456'), findsNothing);
    expect(find.text('演示验证码已发送：123456'), findsNothing);
    // 没有得到码就不该进入"已发送"状态
    expect(find.text('获取验证码'), findsOneWidget);
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

    // ⚠️ 上面那句 ensureVisible 把列表滚下去过，页头和 tab 已经被滚动容器
    //    回收掉了，所以先滚回顶部 —— 否则这里失败的原因会是「滚得太靠下」，
    //    而不是「计数没更新」，能白查半天。
    //
    //    这里用 Scrollable（ListView / CustomScrollView 的共同基类）而不是
    //    写死 ListView：菜谱页为了只建屏幕上看得见的卡片，已经换成了
    //    CustomScrollView + SliverList.builder（接后端后有 10000 道菜，
    //    一次性建一万个卡片会卡死浏览器）。写死类型的话，以后每换一次
    //    滚动组件这个用例就会莫名其妙地红一次。
    await tester.drag(find.byType(Scrollable).first, const Offset(0, 900));
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

  testWidgets('菜谱页分类由后端提供，点分类能真的筛出菜', (tester) async {
    // 这个用例锁住的问题：菜谱页以前写死一排原型分类
    // `['全部','快手菜','汤品','低脂','家常','秋季推荐']`，
    // 而清洗库里的标签是「家常菜」「汤羹」「低脂减重」—— 字符串对不上，
    // 所以除了「全部」每个分类点进去都是空的。
    //
    // 现在分类名 + 分组 + 每个分类的菜品数全部来自后端 /api/recipes/tags。
    // widget 测试跑在离线环境，所以这里手工喂一份和后端同形状的数据。
    final store = ContentStore.instance;
    store.debugSeed(
      recipes: const <Recipe>[
        Recipe(
          id: '1',
          name: '番茄蛋花汤',
          image: '',
          desc: '清爽开胃',
          time: '10分钟',
          people: '2人份',
          tags: <String>['汤羹', '家常菜'],
        ),
        Recipe(
          id: '2',
          name: '香煎鸡胸肉',
          image: '',
          desc: '高蛋白',
          time: '15分钟',
          people: '1人份',
          tags: <String>['快手菜', '鸡肉'],
        ),
        Recipe(
          id: '3',
          name: '牛肉面',
          image: '',
          desc: '一碗顶饱',
          time: '20分钟',
          people: '2人份',
          tags: <String>['面点主食'],
        ),
      ],
      tagGroups: const <RecipeTagGroup>[
        RecipeTagGroup(
          group: '家常快手',
          tags: <RecipeTag>[
            RecipeTag(name: '家常菜', count: 1),
            RecipeTag(name: '快手菜', count: 1),
          ],
        ),
        RecipeTagGroup(
          group: '品类',
          tags: <RecipeTag>[
            RecipeTag(name: '汤羹', count: 1),
            RecipeTag(name: '面点主食', count: 1),
          ],
        ),
      ],
    );
    // 单例，跑完必须还原，否则后面的用例会看到这 3 道假菜
    addTearDown(store.load);

    await tester.pumpWidget(ShishiApp(key: UniqueKey()));
    await tester.tap(find.text('菜谱'));
    await tester.pumpAndSettle();

    // 分类用的是后端给的规范名（卡片上也会出现同名标签，所以不限定数量）
    expect(find.text('汤羹'), findsWidgets);
    expect(find.text('家常菜'), findsWidgets);
    expect(find.text('面点主食'), findsWidgets);
    // 原型里那两个对不上库的旧分类名不该再出现
    expect(find.text('汤品'), findsNothing);
    expect(find.text('秋季推荐'), findsNothing);

    // 点「汤羹」只剩汤 —— 这才是「分类点进去有菜」。
    //
    // ⚠️ 断言用列表标题上的「N 道」而不是去找卡片：菜谱页现在是
    //    SliverList.builder，**屏幕外的卡片根本不会被建出来**（这正是换掉
    //    一次性建 10000 个卡片的原因），所以「找不到香煎鸡胸肉」既可能是被
    //    筛掉了、也可能只是滚不到，用数量断言才分得清这两件事。
    await tester.tap(find.text('汤羹').first);
    await tester.pumpAndSettle();
    expect(find.text('1 道'), findsOneWidget);
    expect(find.text('番茄蛋花汤'), findsOneWidget);

    // 再点「全部」三道菜都回来
    await tester.tap(find.text('全部').first);
    await tester.pumpAndSettle();
    expect(find.text('3 道'), findsOneWidget);
    expect(find.text('番茄蛋花汤'), findsOneWidget);
  });

  testWidgets('食材详情不编数据：拿不到应季指数和关联菜谱就如实说明', (tester) async {
    // 这个用例锁住三处「编出来的话」，它们以前都在食材详情弹层里：
    //   1. 「应季指数 92」是写死的常量 —— 打开哪个食材都是 92；
    //   2. 「XX 正值当季」对每个食材都说，哪怕是反季的；
    //   3. 「适合做这些菜」在本地用 recipe.ingredients 反查，而列表接口
    //      根本不返回 ingredients，于是永远匹配 0 条、静默退化成
    //      「取前两道菜」—— 点任何食材看到的都是同两道。
    //
    // widget 测试跑在离线环境（没有后端），正好是「拿不到真数据」的那条分支：
    // 这时界面必须**如实说拿不到**，而不是编一个数字、两道菜顶上。
    await tester.pumpWidget(ShishiApp(key: UniqueKey()));

    await tester.tap(find.text('食材'));
    await tester.pumpAndSettle();

    // 打开第一个食材的详情。
    // ⚠️ 必须限定在 FoodsPage 里找 —— 首页也在同一棵树上（IndexedStack），
    //    不限定的话 find.text('莲藕').first 很可能选中首页那张离屏的卡片，
    //    点它会「点空」，然后失败在「适合做这些菜」找不到，白查半天。
    final firstFood = ContentStore.instance.foods.first.name;
    final foodTile = find.descendant(
      of: find.byType(FoodsPage),
      matching: find.text(firstFood),
    );
    await tester.ensureVisible(foodTile.first);
    await tester.pumpAndSettle();
    await tester.tap(foodTile.first);
    await tester.pumpAndSettle();

    expect(find.text('适合做这些菜'), findsOneWidget);
    // 应季指数不显示（本地假数据没有这个分值）
    expect(find.textContaining('应季指数'), findsNothing);

    // ⚠️ 「适合做这些菜」下面那块在弹层的折叠线以下，**默认的 finder 会跳过
    //    屏幕外的 widget**（skipOffstage: true）。不先滚下去的话，
    //    断言会以「找不到」失败，看起来像文案没渲染，其实只是没滚到。
    final sheetList = find
        .descendant(
          of: find.byType(DraggableScrollableSheet),
          matching: find.byType(Scrollable),
        )
        .first;
    await tester.drag(sheetList, const Offset(0, -400));
    await tester.pumpAndSettle();

    // 关联菜谱拿不到时给的是说明，不是硬凑的菜；也不能一直转圈
    expect(find.textContaining('暂时查不到用这个食材做的菜谱'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);

    // 关掉弹层，别影响后面的用例
    Navigator.of(tester.element(find.text('适合做这些菜'))).pop();
    await tester.pumpAndSettle();
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
