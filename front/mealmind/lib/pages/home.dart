import 'dart:async';

import 'package:flutter/material.dart';

import '../data/mock.dart';
import '../models/content.dart';
import '../services/api_config.dart';
import '../services/city.dart';
import '../services/content_store.dart';
import '../services/recommender.dart';
import '../state/app_state.dart';
import '../state/home_feed.dart';
import '../theme.dart';
import '../widgets/city_picker.dart';
import '../widgets/dish_photo.dart';
import '../widgets/food_photo.dart';
import '../widgets/menu_entry_card.dart';
import 'menu.dart';
import 'recipes.dart';

/// 首页 —— 对应队友原型 `homePage()`
///
/// 结构：顶部品牌栏 → Hero 推荐 → 家庭约束条 → 今日推荐食材 → 按条件能做的菜 → AI 建议 → 快捷操作
///
/// ★ 推荐内容不是写死的：`pickForHome()` 会拿家庭档案筛一遍
///   （烹饪时间筛掉超时的菜、忌口筛掉命中的菜、低钠和口味偏好调序），
///   所以在「我的」里改约束，切回首页是真的会变的。
class HomePage extends StatelessWidget {
  final VoidCallback onOpenFoods;
  final VoidCallback onOpenRecipes;
  final VoidCallback onOpenAi;
  final VoidCallback onOpenProfile;

  /// 点食材卡片时打开食材详情（走食材页的同一个弹层）
  final ValueChanged<Food> onOpenFoodDetail;

  const HomePage({
    super.key,
    required this.onOpenFoods,
    required this.onOpenRecipes,
    required this.onOpenAi,
    required this.onOpenProfile,
    required this.onOpenFoodDetail,
  });

  /// 本周菜单是【推一个二级页面】，不是切 tab。
  ///
  /// 底部导航那 5 项是「首页 / 食材 / 菜谱 / AI / 我的」；
  /// 菜单是首页推出去的完整方案，看完返回即可，不占导航位。
  void _openMenu(BuildContext context) {
    Navigator.of(context)
        .push<void>(MaterialPageRoute<void>(builder: (_) => const MenuPage()));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        // 监听家庭档案：改完约束切回来，这里会自动重算
        // 同时监听 HomeFeedStore —— 后端「算法 + AI」的结果到了就换上去
        child: ListenableBuilder(
          listenable: Listenable.merge(<Listenable>[
            AppState.instance,
            HomeFeedStore.instance,
          ]),
          builder: (context, _) {
            // ★ 有后端推荐就用后端的（算法筛候选 + 每天每地区一次 AI），
            //   后端离线 / 请求失败时 feed 为 null，自动退回本地规则 ——
            //   界面上看不出差别，但推荐依据完全不同，所以界面上会如实标注来源。
            final feed = HomeFeedStore.instance.feed;
            final picks = feed != null
                ? HomePicks.fromFeed(feed, AppState.instance.profile)
                : pickForHome(
                    AppState.instance.profile,
                    // 后端在线时用后端数据，否则 ContentStore 里是本地假数据
                    foodPool: ContentStore.instance.foods,
                    recipePool: ContentStore.instance.recipes,
                  );
            return ListView(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 28),
              children: [
                const _TopBar(),
                const SizedBox(height: 14),
                _HomeCarousel(
                  onOpenFoods: onOpenFoods,
                  onOpenRecipes: onOpenRecipes,
                  onOpenAi: onOpenAi,
                ),
                const SizedBox(height: 18),
                _ConstraintBar(
                  picks: picks,
                  onOpenProfile: onOpenProfile,
                  onOpenSource: () => _showSourceSheet(context, picks),
                ),
                // ★ 后端没连上时必须说出来。
                //   以前是「静默降级」——界面照常好看，只是没有 AI、没有天气、
                //   没有每日轮换。结果就是「我明明更新了代码，怎么看不到 AI 效果」，
                //   而且完全查不出原因。现在只要不是后端算的，就明确挂一条横幅。
                if (!picks.fromBackend) ...[
                  const SizedBox(height: 12),
                  const _NotConnectedBanner(),
                ],
                const SizedBox(height: 24),
                const _SectionHeader(
                  icon: Icons.eco,
                  title: '今日推荐食材',
                  subtitle: '应季鲜美 · 营养加分',
                ),
                const SizedBox(height: 12),
                _FoodRow(foods: picks.foods, onOpenDetail: onOpenFoodDetail),
                const SizedBox(height: 26),
                _SectionHeader(
                  icon: Icons.local_dining,
                  title: '今日推荐菜品',
                  subtitle: picks.subtitle,
                ),
                const SizedBox(height: 12),
                _RecipeRow(
                  recipes: picks.recipes,
                  onOpenRecipes: onOpenRecipes,
                ),
                const SizedBox(height: 14),
                _AiTipBar(
                  title: picks.aiTipTitle,
                  body: picks.aiTipBody,
                  onTap: onOpenAi,
                ),
                const SizedBox(height: 12),
                MenuEntryCard(onTap: () => _openMenu(context)),
                const SizedBox(height: 20),
                _QuickActions(
                  picks: picks,
                  onOpenFoods: onOpenFoods,
                  onOpenRecipes: onOpenRecipes,
                  onOpenAi: onOpenAi,
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

// =====================================================================
// 家庭约束条 —— 让「约束在生效」这件事在首页也看得见
//
// 首页以前是全项目唯一不读家庭档案的页面，个性化只存在于菜单页。
// 现在这里既显示当前条件，也直接说明推荐已经按它筛过；
// 点一下跳到「我的」，形成「首页看到 → 点进去改 → 回来看变化」的闭环。
// =====================================================================

class _ConstraintBar extends StatelessWidget {
  final HomePicks picks;
  final VoidCallback onOpenProfile;
  final VoidCallback onOpenSource;

  const _ConstraintBar({
    required this.picks,
    required this.onOpenProfile,
    required this.onOpenSource,
  });

  @override
  Widget build(BuildContext context) {
    final p = AppState.instance.profile;

    // 第一行：这份推荐是怎么来的（后端算法 + AI / 本地规则）
    // 第二行：随家庭约束变化的那句话
    // 第三行：天气（后端取到时才有）
    final sourceText = picks.sourceLabel ?? '本地规则（后端未连接）';
    final constraintText = picks.droppedNames.isEmpty
        ? '下方推荐已按家庭档案筛选'
        : '「${picks.droppedNames.first}」等 ${picks.dropped} 道'
              '超出条件，已从下方推荐排除';

    return InkWell(
      borderRadius: BorderRadius.circular(rCard),
      onTap: onOpenProfile,
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
        decoration: cardDeco(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: orange100,
                    borderRadius: BorderRadius.circular(11),
                  ),
                  child: const Icon(Icons.tune, size: 18, color: orange700),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${p.people} 人',
                        style: const TextStyle(
                          fontSize: 12.5,
                          fontWeight: FontWeight.w800,
                          color: ink,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        constraintText,
                        style: const TextStyle(fontSize: 10.5, color: muted),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                const Text(
                  '去修改',
                  style: TextStyle(
                    fontSize: 11,
                    color: orange700,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const Icon(Icons.chevron_right, size: 16, color: orange700),
              ],
            ),
            const SizedBox(height: 9),
            // 「推荐依据」入口：算法怎么筛的、AI 干了什么，点开就能看。
            // 刻意做成一行而不是一整块 —— 首页布局不动，就不会碰坏既有交互。
            //
            // ★ 这一行同时承担「我在看哪个城市的推荐」的职责：
            //   后端算的是哪个城市，就显示哪个城市；正在重算时显示「正在按 XX 重新计算…」。
            //   以前这里只写来源、不写城市，切换城市后数据要等几秒才回来，
            //   中间那几秒看起来就像「切了没反应」。
            InkWell(
              onTap: onOpenSource,
              borderRadius: BorderRadius.circular(9),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 3),
                child: ListenableBuilder(
                  listenable: HomeFeedStore.instance,
                  builder: (context, _) {
                    final store = HomeFeedStore.instance;
                    final text = store.loading
                        ? '正在按「${store.loadingRegion ?? ''}」重新计算…'
                        : [
                            sourceText,
                            if ((store.region ?? '').isNotEmpty) store.region!,
                            if (picks.weatherLine != null) picks.weatherLine!,
                          ].join(' · ');

                    return Row(
                      children: [
                        if (store.loading)
                          const SizedBox(
                            width: 12,
                            height: 12,
                            child: CircularProgressIndicator(
                              strokeWidth: 1.6,
                              color: orange700,
                            ),
                          )
                        else
                          Icon(
                            picks.fromBackend
                                ? Icons.auto_awesome
                                : Icons.calculate_outlined,
                            size: 13,
                            color: picks.fromBackend ? orange700 : muted,
                          ),
                        const SizedBox(width: 5),
                        Expanded(
                          child: Text(
                            text,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 10.5,
                              fontWeight: FontWeight.w600,
                              color: picks.fromBackend ? orange700 : muted,
                            ),
                          ),
                        ),
                        const Text(
                          '推荐依据',
                          style: TextStyle(
                            fontSize: 10.5,
                            color: orange700,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const Icon(
                          Icons.chevron_right,
                          size: 14,
                          color: orange700,
                        ),
                      ],
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =====================================================================
// 「推荐依据」弹层 —— 答辩时的加分项
//
// 首页不再只是「给你三个菜」，而是能当面说清：
//   今天什么天气 → 从我们自己的库里按什么权重筛出候选
//   → AI 在候选里挑了什么 → 最后怎么被你的忌口收口
// 每一步都是后端真实发生的（meta.steps / trace），不是前端编的。
// =====================================================================

void _showSourceSheet(BuildContext context, HomePicks picks) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _SourceSheet(picks: picks),
  );
}

class _SourceSheet extends StatelessWidget {
  final HomePicks picks;

  const _SourceSheet({required this.picks});

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.viewPaddingOf(context).bottom;
    final reasons = <String, String>{
      ...picks.foodReasons,
      ...picks.recipeReasons,
    };

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.82,
      ),
      padding: EdgeInsets.fromLTRB(18, 12, 18, 18 + bottom),
      decoration: const BoxDecoration(
        color: page,
        borderRadius: BorderRadius.vertical(top: Radius.circular(rBlock)),
      ),
      child: ListView(
        shrinkWrap: true,
        children: [
          Center(
            child: Container(
              width: 42,
              height: 4,
              decoration: BoxDecoration(
                color: line,
                borderRadius: BorderRadius.circular(99),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: orange100,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.account_tree_outlined,
                  size: 19,
                  color: orange700,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '今天的推荐是怎么算出来的',
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w900,
                        color: ink,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      picks.sourceLabel ?? '本地规则',
                      style: const TextStyle(fontSize: 11.5, color: muted),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (picks.weather != null) ...[
            const SizedBox(height: 14),
            _SourceBlock(
              title: '今天的天气',
              lines: [
                '${picks.weather!.emoji} ${picks.weather!.description}'
                    '（${picks.weather!.sourceLabel}）',
                picks.weather!.advice,
              ],
            ),
          ],
          const SizedBox(height: 14),
          _SourceBlock(
            title: '处理链路',
            lines: picks.steps.isEmpty
                ? const <String>['后端未连接，本次由本地规则生成']
                : [
                    for (final step in picks.steps)
                      '${step.step}（${step.ms} ms）：${step.detail}',
                  ],
          ),
          if (reasons.isNotEmpty) ...[
            const SizedBox(height: 14),
            _SourceBlock(
              title: '每一条的推荐理由',
              lines: [
                for (final entry in reasons.entries)
                  '${entry.key}：${entry.value}',
              ],
            ),
          ],
          const SizedBox(height: 16),
          const Text(
            '说明：推荐先由确定性算法从我们自己的食材库里筛选（时令、天气、营养、'
            '标签权重），大模型只在候选集内挑选与解释，不会凭空生成菜名。'
            '同一地区同一天的推荐对所有用户一致，第二天会轮换。',
            style: TextStyle(fontSize: 11, color: muted, height: 1.6),
          ),
        ],
      ),
    );
  }
}

class _SourceBlock extends StatelessWidget {
  final String title;
  final List<String> lines;

  const _SourceBlock({required this.title, required this.lines});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: cardDeco(radius: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w800,
              color: orange900,
            ),
          ),
          const SizedBox(height: 8),
          for (final lineText in lines)
            Padding(
              padding: const EdgeInsets.only(bottom: 5),
              child: Text(
                lineText,
                style: const TextStyle(
                  fontSize: 11.5,
                  color: ink,
                  height: 1.55,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

// =====================================================================
// 「后端没连上」横幅
//
// 为什么必须有它：这个 App 的后端连不上时会**静默降级**到本地演示数据 ——
// 界面照常好看、不弹错误。这个设计对演示是优点，但代价是：一旦后端没起来、
// 或者连到了旧版后端，你看到的就是「界面更新了，但 AI 效果一个都没有」，
// 而且**没有任何线索**。
// 所以只要推荐不是后端算的，就在首页正中间挂一条醒目的横幅，把原因说清楚。
// =====================================================================

class _NotConnectedBanner extends StatelessWidget {
  const _NotConnectedBanner();

  @override
  Widget build(BuildContext context) {
    final status = BackendStatus.instance;
    final detail = status.online
        // 能连上、但首页没拿到后端结果 —— 说明对面是旧版后端
        ? '连上了 ${status.apiBase}，但它没有「算法 + AI 推荐」接口（可能是旧版后端）'
        : '连不上后端（试过：${apiBaseCandidates.join('、')}）'
              '${status.lastError == null ? '' : '；最后一次错误：${status.lastError}'}';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF1E0),
        border: Border.all(color: orange, width: 1.2),
        borderRadius: BorderRadius.circular(rCard),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.cloud_off_rounded, size: 17, color: orange900),
              const SizedBox(width: 7),
              const Expanded(
                child: Text(
                  '当前显示的是本地演示数据',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: orange900,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          const Text(
            'AI 推荐、实时天气、每日轮换都需要后端，现在都不可用。',
            style: TextStyle(fontSize: 11.5, color: ink, height: 1.5),
          ),
          const SizedBox(height: 4),
          Text(
            detail,
            style: const TextStyle(fontSize: 10.5, color: muted, height: 1.5),
          ),
          const SizedBox(height: 8),
          Text(
            '启动后端：cd back && python -m uvicorn app.main:app --port 8000',
            style: TextStyle(
              fontSize: 10.5,
              color: orange900,
              fontFamily: 'monospace',
              fontWeight: FontWeight.w600,
              backgroundColor: Colors.white.withValues(alpha: 0.6),
            ),
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// 顶部品牌栏：食时 + 地区/季节 pill
// =====================================================================

class _TopBar extends StatelessWidget {
  const _TopBar();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '食时',
              style: TextStyle(
                fontSize: 31,
                fontWeight: FontWeight.w900,
                color: orange900,
                letterSpacing: -1.5,
                height: 1,
              ),
            ),
            SizedBox(height: 5),
            Text(
              '顺应时令 · 智慧饮食',
              style: TextStyle(
                fontSize: 10,
                color: orange700,
                fontWeight: FontWeight.w600,
                letterSpacing: 1.2,
              ),
            ),
          ],
        ),
        const Spacer(),
        // 天气 pill —— 后端拿到了实时天气才有，取不到就不显示（不占位、不假装）
        ListenableBuilder(
          listenable: HomeFeedStore.instance,
          builder: (context, _) {
            final weather = HomeFeedStore.instance.feed?.weather;
            if (weather == null) return const SizedBox.shrink();
            return Padding(
              padding: const EdgeInsets.only(right: 8),
              child: _Pill(
                icon: Icons.wb_sunny_outlined,
                text: weather.temperatureC == null
                    ? weather.description
                    : '${weather.temperatureC!.round()}°C',
              ),
            );
          },
        ),
        // 位置 pill —— 以前是个写死的死标签，现在点了能换城市
        ListenableBuilder(
          listenable: CityStore.instance,
          builder: (context, _) => _Pill(
            icon: Icons.location_on,
            text: CityStore.instance.city.name,
            onTap: () => showCityPicker(context),
          ),
        ),
        const SizedBox(width: 8),
        _Pill(icon: Icons.eco, text: currentSeason),
      ],
    );
  }
}

class _Pill extends StatelessWidget {
  final IconData icon;
  final String text;

  /// 传了就是可点的（比如位置 pill），不传就是纯展示（比如季节 pill）
  final VoidCallback? onTap;

  const _Pill({required this.icon, required this.text, this.onTap});

  @override
  Widget build(BuildContext context) {
    final content = Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: line),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: orange700),
          const SizedBox(width: 4),
          Text(text, style: const TextStyle(fontSize: 12, color: ink)),
          // 可点的 pill 加个小箭头，暗示这里能操作
          if (onTap != null) ...[
            const SizedBox(width: 2),
            const Icon(Icons.expand_more, size: 13, color: muted),
          ],
        ],
      ),
    );

    if (onTap == null) return content;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(999),
      child: content,
    );
  }
}

// =====================================================================
// Hero 推荐区
// =====================================================================

class _HomeCarousel extends StatefulWidget {
  final VoidCallback onOpenFoods;
  final VoidCallback onOpenRecipes;
  final VoidCallback onOpenAi;

  const _HomeCarousel({
    required this.onOpenFoods,
    required this.onOpenRecipes,
    required this.onOpenAi,
  });

  @override
  State<_HomeCarousel> createState() => _HomeCarouselState();
}

class _HomeCarouselState extends State<_HomeCarousel> {
  final PageController _controller = PageController();
  int _currentPage = 0;

  /// 页数：主 hero / 我的食材 / AI 助手（和 build 里的 pages 对应）
  static const int _pageCount = 3;

  /// 自动轮播节奏。4 秒是折中 ——
  /// 太快像广告位，太慢用户会以为它就是一张静态图。
  static const Duration _autoPlayEvery = Duration(seconds: 4);
  static const Duration _slideDuration = Duration(milliseconds: 560);

  /// 用户手动滑动之后暂停多久再恢复自动播放。
  /// 立刻恢复的话，手还没松开它就自己跑了；
  /// 一直不恢复的话，用户滑一下这个轮播就"死"了。
  static const Duration _manualPause = Duration(seconds: 8);

  Timer? _autoPlay;
  Timer? _resume;
  bool _dragging = false;

  @override
  void initState() {
    super.initState();
    _startAutoPlay();
  }

  @override
  void dispose() {
    // ⚠️ 两个 Timer 都必须取消。忘了这一步，页面销毁后回调仍会触发，
    //    在已经 dispose 的 PageController 上调 animateToPage 会直接抛异常。
    _autoPlay?.cancel();
    _resume?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _startAutoPlay() {
    _autoPlay?.cancel();
    _autoPlay = Timer.periodic(_autoPlayEvery, (_) {
      // 页面已经销毁、用户正在拖、或者还没布局好 —— 这几种情况都别动，
      // 否则要么抛异常，要么跟用户抢方向。
      if (!mounted || _dragging || !_controller.hasClients) return;
      _controller.animateToPage(
        (_currentPage + 1) % _pageCount,
        duration: _slideDuration,
        curve: Curves.easeInOutCubic,
      );
    });
  }

  void _pauseForManual() {
    _autoPlay?.cancel();
    _autoPlay = null;
    _resume?.cancel();
    _resume = Timer(_manualPause, () {
      if (mounted) _startAutoPlay();
    });
  }

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      _Hero(onOpenRecipes: widget.onOpenRecipes),
      _FeatureHero(
        image: 'assets/images/lotus-clean.jpg',
        eyebrow: '应季食材库',
        title: '看看家里\n有什么',
        body: '收藏家中现有食材，管理数量，减少浪费。',
        buttonText: '管理我的食材',
        buttonIcon: Icons.inventory_2_rounded,
        onTap: widget.onOpenFoods,
      ),
      _FeatureHero(
        eyebrow: 'AI 饮食助手',
        title: '不知道吃什么？\n问问 AI',
        body: '根据家中食材和你的口味，生成一顿营养家常饭。',
        buttonText: '打开 AI 助手',
        buttonIcon: Icons.auto_awesome_rounded,
        onTap: widget.onOpenAi,
        backgroundColors: const [orange50, Color(0xFFFFE7C5)],
      ),
    ];

    return Column(
      children: [
        SizedBox(
          height: 252,
          // Listener 只负责感知「用户碰了它」：一碰就让自动播放让路，
          // 不能和用户抢方向盘。
          child: Listener(
            onPointerDown: (_) {
              _dragging = true;
              _pauseForManual();
            },
            onPointerUp: (_) => _dragging = false,
            onPointerCancel: (_) => _dragging = false,
            child: PageView(
              controller: _controller,
              onPageChanged: (page) => setState(() => _currentPage = page),
              children: pages,
            ),
          ),
        ),
        const SizedBox(height: 10),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(pages.length, (index) {
            final active = index == _currentPage;
            return GestureDetector(
              onTap: () => _controller.animateToPage(
                index,
                duration: const Duration(milliseconds: 280),
                curve: Curves.easeOutCubic,
              ),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                width: active ? 22 : 7,
                height: 7,
                margin: const EdgeInsets.symmetric(horizontal: 3),
                decoration: BoxDecoration(
                  color: active ? orange : const Color(0xFFE3D8CB),
                  borderRadius: BorderRadius.circular(99),
                ),
              ),
            );
          }),
        ),
      ],
    );
  }
}

class _Hero extends StatelessWidget {
  final VoidCallback onOpenRecipes;

  const _Hero({required this.onOpenRecipes});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 252,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: const Color(0xFFF8EEDC),
        borderRadius: BorderRadius.circular(rHero),
        boxShadow: cardShadow,
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          Image.asset(
            'assets/images/hero-soup.jpg',
            fit: BoxFit.cover,
            alignment: Alignment.centerRight,
            filterQuality: FilterQuality.high,
          ),
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.centerLeft,
                end: Alignment.centerRight,
                colors: [
                  Color(0xFFFFF8E9),
                  Color(0xF7FFF8E9),
                  Color(0xB8FFF8E9),
                  Color(0x00FFF8E9),
                ],
                stops: [0, .34, .58, .82],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(22, 22, 18, 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  heroEyebrow,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: orange700,
                    letterSpacing: 0.6,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  heroTitle,
                  style: TextStyle(
                    fontSize: 33,
                    fontWeight: FontWeight.w900,
                    color: orange900,
                    height: 1.05,
                    letterSpacing: -1.4,
                  ),
                ),
                const SizedBox(height: 5),
                Container(
                  width: 112,
                  height: 4,
                  decoration: BoxDecoration(
                    color: orange,
                    borderRadius: BorderRadius.circular(99),
                  ),
                ),
                const SizedBox(height: 12),
                const SizedBox(
                  width: 205,
                  child: Text(
                    heroBody,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 13, color: ink, height: 1.55),
                  ),
                ),
                const Spacer(),
                FilledButton(
                  onPressed: onOpenRecipes,
                  style: FilledButton.styleFrom(
                    backgroundColor: orange,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 18,
                      vertical: 11,
                    ),
                    visualDensity: VisualDensity.compact,
                    shape: const StadiumBorder(),
                  ),
                  child: const Text(
                    '查看推荐菜谱  →',
                    style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FeatureHero extends StatelessWidget {
  final String? image;
  final String eyebrow;
  final String title;
  final String body;
  final String buttonText;
  final IconData buttonIcon;
  final VoidCallback onTap;
  final List<Color> backgroundColors;

  const _FeatureHero({
    this.image,
    required this.eyebrow,
    required this.title,
    required this.body,
    required this.buttonText,
    required this.buttonIcon,
    required this.onTap,
    this.backgroundColors = const [Color(0xFFFFF5DF), Color(0xFFF5E7C8)],
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 252,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: backgroundColors,
        ),
        borderRadius: BorderRadius.circular(rHero),
        boxShadow: cardShadow,
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (image != null)
            Image.asset(
              image!,
              fit: BoxFit.cover,
              alignment: Alignment.centerRight,
              filterQuality: FilterQuality.high,
            )
          else
            Positioned(
              right: -18,
              bottom: -20,
              child: Icon(
                Icons.auto_awesome_rounded,
                size: 170,
                color: orange700.withValues(alpha: 0.10),
              ),
            ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.centerLeft,
                end: Alignment.centerRight,
                colors: image == null
                    ? const [Color(0x00FFFFFF), Color(0x00FFFFFF)]
                    : const [
                        Color(0xFFFFF8E9),
                        Color(0xF8FFF8E9),
                        Color(0xC8FFF8E9),
                        Color(0x22FFF8E9),
                      ],
                stops: image == null ? null : const [0, .38, .62, 1],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(22, 20, 18, 18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(buttonIcon, size: 16, color: orange700),
                    const SizedBox(width: 6),
                    Text(
                      eyebrow,
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
                        color: orange700,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w900,
                    color: orange900,
                    height: 1.08,
                    letterSpacing: -1.1,
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: 220,
                  child: Text(
                    body,
                    style: const TextStyle(
                      fontSize: 12,
                      color: ink,
                      height: 1.5,
                    ),
                  ),
                ),
                const Spacer(),
                FilledButton.icon(
                  onPressed: onTap,
                  style: FilledButton.styleFrom(
                    backgroundColor: orange,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 10,
                    ),
                    visualDensity: VisualDensity.compact,
                    shape: const StadiumBorder(),
                  ),
                  icon: Icon(buttonIcon, size: 16),
                  label: Text(
                    buttonText,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// 区块标题
// =====================================================================

class _SectionHeader extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;

  const _SectionHeader({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: orange100,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(icon, size: 19, color: orange700),
        ),
        const SizedBox(width: 10),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w800,
                color: ink,
              ),
            ),
            const SizedBox(height: 2),
            Text(subtitle, style: const TextStyle(fontSize: 12, color: muted)),
          ],
        ),
      ],
    );
  }
}

// =====================================================================
// 食材卡片（横排三张）
// =====================================================================

class _FoodRow extends StatelessWidget {
  final List<Food> foods;
  final ValueChanged<Food> onOpenDetail;

  const _FoodRow({required this.foods, required this.onOpenDetail});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const spacing = 10.0;
        const contentHeight = 76.0;
        final cardWidth =
            (constraints.maxWidth - spacing * (foods.length - 1)) /
            foods.length;
        return SizedBox(
          height: cardWidth / 1.8 + contentHeight,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var i = 0; i < foods.length; i++) ...[
                if (i > 0) const SizedBox(width: spacing),
                Expanded(
                  child: _FoodCard(
                    food: foods[i],
                    onTap: () => onOpenDetail(foods[i]),
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

/// 卡片按压反馈：按住时轻微缩小。
///
/// 为什么不只靠 InkWell 的涟漪：涟漪是「点中那一瞬」的反馈，
/// 而缩放是「按住期间」持续存在的反馈 —— 手指按着不动，
/// 也看得出这张卡是可以点的。
class _PressCard extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  final BorderRadius? borderRadius;

  const _PressCard({required this.child, this.onTap, this.borderRadius});

  @override
  State<_PressCard> createState() => _PressCardState();
}

class _PressCardState extends State<_PressCard> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    return AnimatedScale(
      // 0.972 是"看得出来在缩、但不会晃眼"的量；再大就像在抖。
      scale: _pressed ? 0.972 : 1,
      duration: const Duration(milliseconds: 110),
      curve: Curves.easeOut,
      child: InkWell(
        onTap: widget.onTap,
        borderRadius: widget.borderRadius ?? BorderRadius.circular(rCard),
        onHighlightChanged: (value) {
          if (_pressed != value) setState(() => _pressed = value);
        },
        child: widget.child,
      ),
    );
  }
}

class _FoodCard extends StatelessWidget {
  final Food food;
  final VoidCallback onTap;

  const _FoodCard({required this.food, required this.onTap});

  /// 卡片底部那个小标签。
  ///
  /// 有功效标签（如「增强人体免疫力」）就用它；没有就退回食材分类
  /// （蔬菜 / 水果 / 肉蛋 …）。
  ///
  /// 为什么必须有兜底：清洗库里 590 个核心食材**只有 124 个（21%）带功效标签**，
  /// 不做兜底的话 79% 的卡片下面就是一块空白，跟旁边有标签的卡片放在一起很怪。
  ({String text, Color color}) get _chip {
    if (food.tags.isNotEmpty) {
      return (text: food.tags.first, color: orange700);
    }
    return (text: food.category, color: muted);
  }

  @override
  Widget build(BuildContext context) {
    // 这张卡片以前点了没反应 —— 现在点开食材详情
    //
    // ⚠️ 这里曾经有个 bug：卡片把「名字 + 标签」画了两遍
    //    （先一个 Expanded 块，下面又一个 Padding 块）。
    //    卡片高度是固定的，于是两块互相挤压 —— 有标签的卡片被裁得只剩一块，
    //    看起来"正常"；没标签的卡片（79%）就露出**重复的食材名**。
    //    现在恢复成原型的设计：图片 → 名字（一次）→ 标签。
    final chip = _chip;

    return _PressCard(
      onTap: onTap,
      borderRadius: BorderRadius.circular(rCard),
      child: Container(
        clipBehavior: Clip.antiAlias,
        decoration: cardDeco(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(aspectRatio: 1.8, child: FoodPhoto(asset: food.image)),
            Padding(
              padding: const EdgeInsets.all(10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    food.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: ink,
                    ),
                  ),
                  if (chip.text.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 7,
                        vertical: 4,
                      ),
                      decoration: tagDeco(),
                      child: Text(
                        chip.text,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 10,
                          color: chip.color,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =====================================================================
// 菜谱卡片（三张并排，对齐视觉稿）
// =====================================================================

class _RecipeRow extends StatelessWidget {
  final List<Recipe> recipes;
  final VoidCallback onOpenRecipes;

  const _RecipeRow({required this.recipes, required this.onOpenRecipes});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < recipes.length; i++) ...[
          if (i > 0) const SizedBox(width: 10),
          Expanded(
            child: _RecipeCard(
              recipe: recipes[i],
              onOpenRecipes: onOpenRecipes,
            ),
          ),
        ],
      ],
    );
  }
}

class _RecipeCard extends StatelessWidget {
  final Recipe recipe;
  final VoidCallback onOpenRecipes;

  const _RecipeCard({required this.recipe, required this.onOpenRecipes});

  @override
  Widget build(BuildContext context) {
    return _PressCard(
      borderRadius: BorderRadius.circular(rCard),
      onTap: onOpenRecipes,
      child: Container(
        clipBehavior: Clip.antiAlias,
        decoration: cardDeco(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(
              aspectRatio: 1.55,
              child: DishPhoto(asset: recipe.image),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(9, 9, 9, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    recipe.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                      color: ink,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    recipe.desc,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 10, color: muted),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      const Icon(Icons.schedule, size: 11, color: muted),
                      const SizedBox(width: 3),
                      Expanded(
                        child: Text(
                          recipe.time,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 9, color: muted),
                        ),
                      ),
                      const Icon(Icons.people_outline, size: 11, color: muted),
                      const SizedBox(width: 2),
                      Text(
                        recipe.people,
                        style: const TextStyle(fontSize: 9, color: muted),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =====================================================================
// AI 建议条
// =====================================================================

class _AiTipBar extends StatelessWidget {
  /// 后端给的标题/正文。为空时退回本地写死的文案 ——
  /// 保证后端离线时这一块不会变成空白。
  final String? title;
  final String? body;
  final VoidCallback onTap;

  const _AiTipBar({required this.onTap, this.title, this.body});

  @override
  Widget build(BuildContext context) {
    // 这条建议以前点了没反应 —— 现在点进 AI 助手
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(22),
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [orange50, Color(0xFFFBF7E9)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(22),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: orange700,
                borderRadius: BorderRadius.circular(14),
              ),
              child: const Icon(
                Icons.auto_awesome,
                color: Colors.white,
                size: 20,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title ?? mockAiTip.title,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                      color: ink,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    body ?? mockAiTip.body,
                    style: const TextStyle(
                      fontSize: 13,
                      color: muted,
                      height: 1.6,
                    ),
                  ),
                ],
              ),
            ),
            // 右侧箭头暗示这里可以点
            const Icon(Icons.chevron_right, size: 18, color: orange700),
          ],
        ),
      ),
    );
  }
}

// =====================================================================
// 快捷操作
// =====================================================================

class _QuickActions extends StatelessWidget {
  final HomePicks picks;
  final VoidCallback onOpenFoods;
  final VoidCallback onOpenRecipes;
  final VoidCallback onOpenAi;

  const _QuickActions({
    required this.picks,
    required this.onOpenFoods,
    required this.onOpenRecipes,
    required this.onOpenAi,
  });

  void _openQuickMealPicker(BuildContext context) {
    final recipes = picks.recipes.isNotEmpty
        ? picks.recipes
        : ContentStore.instance.recipes;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _QuickMealSheet(
        recipes: recipes,
        onOpenRecipe: (recipe) => openRecipeDetail(context, recipe),
        onOpenRecipes: onOpenRecipes,
        onOpenAi: onOpenAi,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton(
            onPressed: () => _openQuickMealPicker(context),
            style: OutlinedButton.styleFrom(
              side: const BorderSide(color: orange100),
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: const StadiumBorder(),
            ),
            child: const Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.casino_outlined, size: 17, color: orange700),
                SizedBox(width: 6),
                Text(
                  '快速选一餐',
                  style: TextStyle(
                    color: orange700,
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: FilledButton(
            onPressed: onOpenFoods,
            style: FilledButton.styleFrom(
              backgroundColor: orange,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: const StadiumBorder(),
            ),
            child: const Text(
              '去选食材',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
            ),
          ),
        ),
      ],
    );
  }
}

class _QuickMealSheet extends StatefulWidget {
  final List<Recipe> recipes;
  final ValueChanged<Recipe> onOpenRecipe;
  final VoidCallback onOpenRecipes;
  final VoidCallback onOpenAi;

  const _QuickMealSheet({
    required this.recipes,
    required this.onOpenRecipe,
    required this.onOpenRecipes,
    required this.onOpenAi,
  });

  @override
  State<_QuickMealSheet> createState() => _QuickMealSheetState();
}

class _QuickMealSheetState extends State<_QuickMealSheet> {
  int _index = 0;

  void _next() {
    if (widget.recipes.length < 2) return;
    setState(() => _index = (_index + 1) % widget.recipes.length);
  }

  void _closeThen(VoidCallback action) {
    Navigator.pop(context);
    WidgetsBinding.instance.addPostFrameCallback((_) => action());
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.viewPaddingOf(context).bottom;
    if (widget.recipes.isEmpty) {
      return Container(
        padding: EdgeInsets.fromLTRB(22, 12, 22, 24 + bottom),
        decoration: const BoxDecoration(
          color: page,
          borderRadius: BorderRadius.vertical(top: Radius.circular(rBlock)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _SheetHandle(),
            const SizedBox(height: 24),
            const Icon(Icons.no_meals_outlined, size: 42, color: muted),
            const SizedBox(height: 12),
            const Text(
              '暂时没有合适的菜谱',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () => _closeThen(widget.onOpenRecipes),
              child: const Text('查看全部菜谱'),
            ),
          ],
        ),
      );
    }

    final recipe = widget.recipes[_index];
    return Container(
      padding: EdgeInsets.fromLTRB(18, 12, 18, 20 + bottom),
      decoration: const BoxDecoration(
        color: page,
        borderRadius: BorderRadius.vertical(top: Radius.circular(rBlock)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SheetHandle(),
          const SizedBox(height: 16),
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: orange100,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.auto_awesome_rounded,
                  size: 19,
                  color: orange700,
                ),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '今日一餐灵感',
                      style: TextStyle(
                        fontSize: 19,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    Text(
                      '已按家庭人数、口味和忌口筛选',
                      style: TextStyle(fontSize: 11.5, color: muted),
                    ),
                  ],
                ),
              ),
              IconButton(
                onPressed: _next,
                tooltip: '换一个推荐',
                icon: const Icon(Icons.refresh_rounded, color: orange700),
              ),
            ],
          ),
          const SizedBox(height: 14),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            child: Container(
              key: ValueKey(recipe.id),
              clipBehavior: Clip.antiAlias,
              decoration: cardDeco(radius: 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  AspectRatio(
                    aspectRatio: 2.15,
                    child: DishPhoto(asset: recipe.image),
                  ),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          recipe.name,
                          style: const TextStyle(
                            fontSize: 21,
                            fontWeight: FontWeight.w900,
                            color: ink,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          recipe.desc,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 12.5,
                            color: muted,
                            height: 1.5,
                          ),
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 7,
                          runSpacing: 7,
                          children: [
                            _MealMeta(
                              icon: Icons.schedule_rounded,
                              text: recipe.time,
                            ),
                            _MealMeta(
                              icon: Icons.people_outline_rounded,
                              text: recipe.people,
                            ),
                            _MealMeta(
                              icon: Icons.local_dining_outlined,
                              text: recipe.difficulty,
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _next,
                  icon: const Icon(Icons.casino_outlined, size: 17),
                  label: const Text('换一个'),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 13),
                    foregroundColor: orange700,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: FilledButton.icon(
                  onPressed: () =>
                      _closeThen(() => widget.onOpenRecipe(recipe)),
                  icon: const Icon(Icons.menu_book_rounded, size: 17),
                  label: const Text('查看做法'),
                  style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 13),
                    backgroundColor: orange,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              TextButton.icon(
                onPressed: () => _closeThen(widget.onOpenAi),
                icon: const Icon(Icons.auto_awesome, size: 15),
                label: const Text('让 AI 帮我搭配'),
              ),
              TextButton(
                onPressed: () => _closeThen(widget.onOpenRecipes),
                child: const Text('查看全部菜谱'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SheetHandle extends StatelessWidget {
  const _SheetHandle();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        width: 42,
        height: 4,
        decoration: BoxDecoration(
          color: line,
          borderRadius: BorderRadius.circular(99),
        ),
      ),
    );
  }
}

class _MealMeta extends StatelessWidget {
  final IconData icon;
  final String text;

  const _MealMeta({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: tagDeco(),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: orange700),
          const SizedBox(width: 4),
          Text(
            text.isEmpty ? '待补充' : text,
            style: const TextStyle(
              fontSize: 11,
              color: orange700,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}
