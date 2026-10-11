// 「注销账号」的界面行为。
//
// 这里要锁住的是三件必须做到的事：
//   1. 确认词没打对时提交不了 —— 注销是真删，误点一次就没了
//   2. 真提交时请求发得对、本地登录态跟着清掉；后端拒绝时要如实显示原因
//   3. ★ 本机上属于这个人的数据也要一起清掉（家庭档案 + 今日菜单），
//      而且清它的时候【不能】顺手往账号推一次 —— 账号已经删了，
//      那个请求会吃 401，把「注销成功」的提示顶成「登录已失效」
//
// AuthStore 是全局单例、网络层平时每次现建，所以用 debugUseDio 塞一个假
// adapter 进去：既拦住了真网络，走的又是 deleteAccount 的真实代码路径
// （包括它怎么把后端的 detail 变成给用户看的一句话）。

import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealmind/models/content.dart';
import 'package:mealmind/pages/profile.dart';
import 'package:mealmind/services/api_config.dart';
import 'package:mealmind/services/auth_store.dart';
import 'package:mealmind/state/app_state.dart';
import 'package:mealmind/state/today_menu.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 把请求记下来、按预设状态码作答的假后端。
class _FakeBackend implements HttpClientAdapter {
  final List<RequestOptions> requests = <RequestOptions>[];

  int statusCode = 204;
  String detail = '';

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    if (statusCode == 204) {
      // 和 FastAPI 的 204 一样：没有 body
      return ResponseBody.fromString('', 204);
    }
    return ResponseBody.fromString(
      jsonEncode(<String, String>{'detail': detail}),
      statusCode,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>[Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

/// 一份「上一个人」留在这台设备上的本机缓存。
///
/// 注销要清的正是它：只清服务端的话，换另一个账号登进来会直接看到
/// 前一个人的家庭人数、忌口和口味偏好。
Map<String, Object> _previousPersonCache() => <String, Object>{
  'family_profile': jsonEncode(<String, dynamic>{
    'people': 5,
    'cook_minutes': 30,
    'low_sodium': false,
    'preferences': <String>['重辣'],
    'avoid': <String>['花生'],
    'tools': <String>['烤箱'],
  }),
};

void main() {
  // 下面的用例里既有 testWidgets 也有纯 test，先显式把绑定装好，
  // 免得纯 test 那条依赖 SharedPreferences 的平台通道。
  TestWidgetsFlutterBinding.ensureInitialized();

  late _FakeBackend backend;

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    // 用例不联网：探测固定成离线，ProfilePage 里那些「在线才去拉」的
    // 统计数字就不会掺进请求记录里
    BackendStatus.instance.setOfflineForTesting();
    await AuthStore.instance.logout();

    backend = _FakeBackend();
    final dio = Dio(BaseOptions(baseUrl: 'http://test.invalid'));
    dio.httpClientAdapter = backend;
    AuthStore.instance.debugUseDio(dio);
  });

  tearDown(() {
    AuthStore.instance.debugUseDio(null);
  });

  Future<void> pumpProfile(WidgetTester tester) async {
    // 「我的」页很长，注销入口在最底部 —— 视口给高一点，省掉一堆滚动手势
    tester.view.physicalSize = const Size(800, 3000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    AppState.instance.debugResetMemory();
    await tester.pumpWidget(
      MaterialApp(
        home: ProfilePage(onOpenRecipes: () {}, onOpenPantry: () {}),
      ),
    );
    await tester.pumpAndSettle();
  }

  /// 滚到危险操作区并打开注销弹窗。返回弹窗里的输入框。
  Future<Finder> openDeleteDialog(WidgetTester tester) async {
    final entry = find.text('注销账号');
    final scrollable = find
        .descendant(of: find.byType(ProfilePage), matching: find.byType(Scrollable))
        .first;
    await tester.scrollUntilVisible(entry, 300, scrollable: scrollable);
    await tester.pumpAndSettle();

    expect(find.text('危险操作'), findsOneWidget, reason: '注销入口应该独立成一个危险操作区');
    await tester.tap(entry);
    await tester.pumpAndSettle();

    // ⚠️ 只能限定在弹窗里找输入框：ProfilePage 自己的「自定义偏好」弹层
    //    里也有 TextFormField，用 find.byType(TextField) 会选错。
    return find.descendant(
      of: find.byType(AlertDialog),
      matching: find.byType(TextField),
    );
  }

  Finder confirmButton() => find.widgetWithText(FilledButton, '确认注销');

  testWidgets('注销：确认词打错时按钮禁用，点了也不会发请求', (tester) async {
    await AuthStore.instance.loginAsDemo();
    await pumpProfile(tester);
    final field = await openDeleteDialog(tester);

    // 一打开就是禁用的：「注销」两个字还没打
    expect(
      tester.widget<FilledButton>(confirmButton()).onPressed,
      isNull,
      reason: '还没输入确认词就能提交，等于没有二次确认',
    );

    await tester.enterText(field, '确定');
    await tester.pumpAndSettle();
    expect(
      tester.widget<FilledButton>(confirmButton()).onPressed,
      isNull,
      reason: '打了别的字也能提交的话，这道确认形同虚设',
    );

    // 硬点一下（按钮处于禁用态）：绝不能有请求出去
    await tester.tap(confirmButton(), warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(backend.requests, isEmpty, reason: '确认词不对却发出了注销请求');
    expect(find.text('确认注销'), findsOneWidget, reason: '不该把弹窗关掉');
  });

  testWidgets('注销：确认词打对后发出 DELETE，并清掉本地登录态', (tester) async {
    await AuthStore.instance.loginAsDemo();
    final token = AuthStore.instance.token;
    expect(token, isNotNull);

    await pumpProfile(tester);
    final field = await openDeleteDialog(tester);

    await tester.enterText(field, '注销');
    await tester.pumpAndSettle();
    expect(
      tester.widget<FilledButton>(confirmButton()).onPressed,
      isNotNull,
      reason: '确认词打对了按钮还是灰的，用户根本走不完这个流程',
    );

    await tester.tap(confirmButton());
    await tester.pumpAndSettle();

    expect(backend.requests, hasLength(1));
    final request = backend.requests.single;
    expect(request.method, 'DELETE');
    expect(request.path, '/api/auth/me');
    expect(request.headers['Authorization'], 'Bearer $token');

    // 后端那边人已经没了，本地必须跟着退登 ——
    // 否则界面停在「显示着已登录、调什么接口都 401」
    expect(AuthStore.instance.isLoggedIn, isFalse);
    expect(AuthStore.instance.token, isNull);
    // 门禁会把界面切回登录页，而登录页只能显示 notice ——
    // 不留一句的话，用户不知道到底删成功没有
    expect(AuthStore.instance.notice, contains('已注销'));
    expect(find.text('确认注销'), findsNothing, reason: '注销成功后弹窗应该关掉');
  });

  testWidgets('注销：管理员/演示账号被拒时如实显示原因，且不把人登出', (tester) async {
    await AuthStore.instance.loginAsDemo();
    backend.statusCode = 403;
    // 和后端 auth_service.delete_account 里那句话保持一致
    backend.detail = '管理员与演示账号不允许自助注销；该账号还要用于比赛演示和后台管理';

    await pumpProfile(tester);
    final field = await openDeleteDialog(tester);

    await tester.enterText(field, '注销');
    await tester.pumpAndSettle();
    await tester.tap(confirmButton());
    await tester.pumpAndSettle();

    // 后端那句话要原样透出来：用户得知道「不是我操作错了，是这类账号不让注销」
    expect(find.textContaining('不允许自助注销'), findsOneWidget);
    expect(find.text('确认注销'), findsOneWidget, reason: '失败时弹窗要留着，让用户能取消');
    // ★ 失败绝不能退登 —— 账号还在，凭什么把人踢下线
    expect(AuthStore.instance.isLoggedIn, isTrue);
  });

  test('注销要用的 clearLocalCache：清掉本机档案，但一个请求都不发', () async {
    SharedPreferences.setMockInitialValues(_previousPersonCache());
    final prefs = await SharedPreferences.getInstance();
    expect(
      prefs.getString('family_profile'),
      isNotNull,
      reason: '前置条件没建起来的话，下面的断言会变成空转',
    );

    await AppState.instance.load();
    expect(AppState.instance.profile.people, 5, reason: '前置条件：内存里得先是上一个人的档案');

    await AppState.instance.clearLocalCache();

    // ★ 清本机数据不该碰网络层。注销时账号已经没了，真发出去的请求会吃
    //   401，而 401 会被 Dio 拦截器翻译成「登录已失效」，正好把「注销成功」
    //   的提示顶掉。
    //
    //   ⚠️ 这条断言本身抓不住「走 saveProfile」的写法 —— 测试是离线环境，
    //   saveProfile 在 `!online` 那行就 return 了，一个请求都不会发。
    //   真正抓住它的是下面那条缓存断言：saveProfile 会把一份【默认档案】
    //   写进缓存，而这里要的是把缓存那条删掉。
    expect(
      backend.requests,
      isEmpty,
      reason: '清本机数据发出了请求',
    );
    expect(AppState.instance.profile.people, 3, reason: '内存没有复位成默认值');
    expect(
      prefs.getString('family_profile'),
      isNull,
      reason: '缓存那条没删掉，换账号登录会读到上一个人的档案',
    );
  });

  testWidgets('注销：本机的家庭档案与今日菜单一起清掉，且不多发一个请求', (tester) async {
    SharedPreferences.setMockInitialValues(_previousPersonCache());
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('family_profile'), isNotNull, reason: '前置条件没建起来');

    await AuthStore.instance.loginAsDemo();
    await pumpProfile(tester);

    // pumpProfile 清过内存，这里再从本机缓存读回来 ——
    // 也就是「这台设备上还留着上一个人的档案」的那个状态
    await AppState.instance.load();
    expect(AppState.instance.profile.people, 5, reason: '前置条件：内存里得先是上一个人的档案');

    TodayMenuStore.instance.add(
      const Recipe(
        id: 'leftover',
        name: '上一个人加的菜',
        image: '',
        desc: '',
        time: '',
        people: '',
        tags: <String>[],
      ),
    );
    addTearDown(TodayMenuStore.instance.clear);
    expect(TodayMenuStore.instance.count, 1);

    final field = await openDeleteDialog(tester);
    await tester.enterText(field, '注销');
    await tester.pumpAndSettle();
    await tester.tap(confirmButton());
    await tester.pumpAndSettle();

    // ---- 内存复位成默认值 ----
    expect(AppState.instance.profile.people, 3);
    expect(AppState.instance.profile.preferences, isNot(contains('重辣')));
    expect(AppState.instance.profile.avoid, isNot(contains('花生')));
    expect(TodayMenuStore.instance.isEmpty, isTrue, reason: '今日菜单也是个人数据');

    // ---- 本机缓存那条真的没了（不是写了一份默认值回去）----
    expect(
      prefs.getString('family_profile'),
      isNull,
      reason: '缓存留着的话，换账号登录会读到上一个人的档案',
    );

    // ---- 整场注销只该有 DELETE /api/auth/me 这一条请求 ----
    // 清本机数据要是走了网络层，这里就会多出一条（生产环境走 saveProfile
    // 的话是 PUT /api/profile）—— 账号已删，它会吃 401，把成功提示顶掉。
    expect(
      backend.requests.map((r) => '${r.method} ${r.path}').toList(),
      <String>['DELETE /api/auth/me'],
      reason: '清本机数据多发了请求',
    );
  });
}
