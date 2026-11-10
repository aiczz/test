// 首页（决赛版）—— 「节令历书」
//
// 设计意图：把节气/季节当成版面的主角，而不是装饰。
// 上半屏是一张封面（菜品大图 + 模糊氛围底 + 毛笔字 + 小图），
// 下半屏是一张「纸」，菜谱按历书的目录行排，不再是一张张卡片。
//
// 数据来源和旧首页完全一致，没有任何写死的推荐：
//   后端在线 → HomeFeedStore 的 feed（算法筛候选 + 每天每地区一次 AI）
//   后端离线 → pickForHome() 本地规则兜底
// 所以「我的」里改家庭约束，这一页的推荐同样会变。

import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../models/content.dart';
import '../services/city.dart';
import '../services/content_store.dart';
import '../services/recommender.dart';
import '../state/app_state.dart';
import '../state/home_feed.dart';
import '../widgets/dish_photo.dart';

// ---------- 色板 ----------

const Color _inkDeep = Color(0xFF0F1A14);
const Color _paper = Color(0xFFF7F3EA);
const Color _paperDim = Color(0xFFEBE4D4);
const Color _moss = Color(0xFF2C4A3B);
const Color _ink = Color(0xFF1A1A18);
const Color _inkSoft = Color(0xFF5D5A50);

const String _fontBrush = 'MaShanZheng';
const String _fontDisplay = 'ZCOOLXiaoWei';

/// 区间缓动：把 [start, end] 这段进度单独映射到 0..1。
class _Span {
  const _Span(this.start, this.end);
  final double start;
  final double end;

  double at(double t) {
    if (end <= start) return 1;
    final v = (t - start) / (end - start);
    return v.clamp(0.0, 1.0);
  }
}

double _easeOut(double t) => 1 - math.pow(1 - t, 3).toDouble();

class HomeEditorial extends StatefulWidget {
  final VoidCallback onOpenFoods;
  final VoidCallback onOpenRecipes;
  final VoidCallback onOpenAi;
  final VoidCallback onOpenProfile;
  final ValueChanged<Food> onOpenFoodDetail;

  const HomeEditorial({
    super.key,
    required this.onOpenFoods,
    required this.onOpenRecipes,
    required this.onOpenAi,
    required this.onOpenProfile,
    required this.onOpenFoodDetail,
  });

  @override
  State<HomeEditorial> createState() => _HomeEditorialState();
}

class _HomeEditorialState extends State<HomeEditorial>
    with SingleTickerProviderStateMixin {
  late final AnimationController _intro;

  @override
  void initState() {
    super.initState();
    _intro = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    );
    _intro.forward();
    // 兜底：浏览器/系统把帧节流时，入场可能停在半路。3 秒后强制到终点，
    // 免得整页卡在「刚开始浮上来」的状态。
    Timer(const Duration(seconds: 3), () {
      if (mounted && _intro.value < 1) _intro.value = 1;
    });
  }

  @override
  void dispose() {
    _intro.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final progress = reduceMotion
        ? const AlwaysStoppedAnimation<double>(1.0)
        : _intro;

    return Scaffold(
      backgroundColor: _inkDeep,
      body: SafeArea(
        bottom: false,
        child: LayoutBuilder(
          builder: (context, frame) => Center(
            child: SizedBox(
              width: math.min(480.0, frame.maxWidth),
              height: frame.maxHeight,
              child: ListenableBuilder(
                listenable: Listenable.merge(<Listenable>[
                  AppState.instance,
                  HomeFeedStore.instance,
                  ContentStore.instance,
                  CityStore.instance,
                ]),
                builder: (context, _) {
                  final picks = _resolvePicks();
                  return AnimatedBuilder(
                    animation: progress,
                    builder: (context, _) => _buildPage(
                      context,
                      frame.maxHeight,
                      picks,
                      progress.value,
                      animate: !reduceMotion,
                    ),
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// 有后端推荐就用后端的，否则退回本地规则——和旧首页同一套口径。
  HomePicks _resolvePicks() {
    final feed = HomeFeedStore.instance.feed;
    if (feed != null) {
      return HomePicks.fromFeed(
        feed,
        AppState.instance.profile,
        recipePool: ContentStore.instance.recipes,
      );
    }
    return pickForHome(
      AppState.instance.profile,
      foodPool: ContentStore.instance.foods,
      recipePool: ContentStore.instance.recipes,
    );
  }

  Widget _buildPage(
    BuildContext context,
    double maxHeight,
    HomePicks picks,
    double t, {
    required bool animate,
  }) {
    final heroHeight = math.max(300.0, maxHeight * 0.46);
    return Stack(
      children: <Widget>[
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          height: heroHeight,
          child: _Hero(picks: picks, t: t),
        ),
        SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          padding: EdgeInsets.only(top: heroHeight - 26),
          child: _Sheet(
            picks: picks,
            t: t,
            onOpenRecipes: widget.onOpenRecipes,
            onOpenAi: widget.onOpenAi,
          ),
        ),
        if (animate)
          const Positioned.fill(
            child: IgnorePointer(child: CustomPaint(painter: _GrainPainter())),
          ),
      ],
    );
  }
}

// ---------- 上半屏：封面 ----------

class _Hero extends StatelessWidget {
  const _Hero({required this.picks, required this.t});

  final HomePicks picks;
  final double t;

  @override
  Widget build(BuildContext context) {
    final hero = picks.recipes.isNotEmpty ? picks.recipes.first : null;
    final asset = (hero == null || hero.image.isEmpty)
        ? 'assets/images/splash.png'
        : hero.image;

    return ClipRect(
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          // 模糊底：全屏高斯模糊在 Web 上很贵，如果跟着动画每帧重算就是卡顿的来源。
          // 所以它完全不参与动画，并用 RepaintBoundary 保证只栅格化一次——
          // 反正 σ=16 之下，再缓慢的位移肉眼也看不出来。
          RepaintBoundary(
            child: ImageFiltered(
              imageFilter: ui.ImageFilter.blur(sigmaX: 16, sigmaY: 16),
              child: DishPhoto(asset: asset, fit: BoxFit.cover),
            ),
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  _inkDeep.withValues(alpha: 0.62),
                  _inkDeep.withValues(alpha: 0.38),
                  _inkDeep.withValues(alpha: 0.94),
                ],
                stops: const <double>[0.0, 0.45, 1.0],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 30),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                _TopBar(picks: picks, t: t),
                const Spacer(),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: <Widget>[
                    Expanded(child: _SeasonTitle(picks: picks, t: t)),
                    const SizedBox(width: 12),
                    if (hero != null) _InsetPhoto(asset: asset, t: t),
                  ],
                ),
                const SizedBox(height: 16),
                _Caption(picks: picks, t: t),
              ],
            ),
          ),
          Positioned(
            right: 8,
            top: 66,
            child: _VerticalMeta(picks: picks, t: t),
          ),
        ],
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.picks, required this.t});

  final HomePicks picks;
  final double t;

  @override
  Widget build(BuildContext context) {
    final v = _easeOut(_Span(0.05, 0.42).at(t));
    return Opacity(
      opacity: 0.62 + 0.38 * v,
      child: Row(
        children: <Widget>[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
            decoration: BoxDecoration(
              color: _paper,
              borderRadius: BorderRadius.circular(3),
            ),
            child: const Text(
              '食时',
              style: TextStyle(
                fontFamily: _fontBrush,
                fontSize: 17,
                height: 1.15,
                color: _moss,
              ),
            ),
          ),
          const SizedBox(width: 10),
          const Text(
            'SHI SHI',
            style: TextStyle(
              fontSize: 8.5,
              letterSpacing: 2.6,
              fontWeight: FontWeight.w600,
              color: Color(0xFFCFD6CB),
            ),
          ),
          const Spacer(),
          if (picks.sourceLabel != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                border: Border.all(
                  color: _paper.withValues(alpha: 0.45),
                  width: 0.8,
                ),
                borderRadius: BorderRadius.circular(2),
              ),
              child: Text(
                picks.sourceLabel!,
                style: const TextStyle(
                  fontSize: 9.5,
                  color: _paper,
                  letterSpacing: 0.4,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _SeasonTitle extends StatelessWidget {
  const _SeasonTitle({required this.picks, required this.t});

  final HomePicks picks;
  final double t;

  @override
  Widget build(BuildContext context) {
    final name = _seasonLabel(picks);
    final chars = name.split('');
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: <Widget>[
        for (var i = 0; i < chars.length; i++)
          Padding(
            padding: const EdgeInsets.only(right: 4),
            child: _brushChar(chars[i], i),
          ),
      ],
    );
  }

  Widget _brushChar(String ch, int i) {
    final start = 0.14 + i * 0.06;
    final v = _easeOut(_Span(start, start + 0.38).at(t));
    // 永远留 62% 可见度：动画卡住也不会变成空白
    return Opacity(
      opacity: 0.62 + 0.38 * v,
      child: Transform.translate(
        offset: Offset(0, 22 * (1 - v)),
        child: Text(
          ch,
          style: const TextStyle(
            fontFamily: _fontBrush,
            fontSize: 96,
            height: 0.95,
            color: _paper,
          ),
        ),
      ),
    );
  }
}

class _Caption extends StatelessWidget {
  const _Caption({required this.picks, required this.t});

  final HomePicks picks;
  final double t;

  @override
  Widget build(BuildContext context) {
    final v = _easeOut(_Span(0.52, 0.86).at(t));
    // 优先用 AI 正文（更有信息量），太短时才退回标题
    final body = picks.aiTipBody;
    final text = (body != null && body.trim().length > 10)
        ? body.trim()
        : (picks.aiTipTitle != null && picks.aiTipTitle!.isNotEmpty)
            ? picks.aiTipTitle!
            : (picks.notes.isNotEmpty
                ? picks.notes.first
                : '顺时而食，今天也好好吃饭');
    return Opacity(
      opacity: 0.62 + 0.38 * v,
      child: Text(
        text,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontFamily: _fontDisplay,
          fontSize: 14,
          height: 1.6,
          color: _paper.withValues(alpha: 0.94),
        ),
      ),
    );
  }
}

class _InsetPhoto extends StatelessWidget {
  const _InsetPhoto({required this.asset, required this.t});

  final String asset;
  final double t;

  @override
  Widget build(BuildContext context) {
    final v = _easeOut(_Span(0.58, 0.95).at(t));
    return Opacity(
      opacity: 0.62 + 0.38 * v,
      child: Transform.translate(
        offset: Offset(0, 14 * (1 - v)),
        child: Container(
          padding: const EdgeInsets.all(3),
          decoration: BoxDecoration(
            color: _paper,
            borderRadius: BorderRadius.circular(2),
            boxShadow: <BoxShadow>[
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.35),
                blurRadius: 14,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(1),
            child: SizedBox(
              width: 104,
              height: 78,
              child: DishPhoto(asset: asset, fit: BoxFit.cover),
            ),
          ),
        ),
      ),
    );
  }
}

class _VerticalMeta extends StatelessWidget {
  const _VerticalMeta({required this.picks, required this.t});

  final HomePicks picks;
  final double t;

  @override
  Widget build(BuildContext context) {
    final v = _easeOut(_Span(0.2, 0.6).at(t));
    final city = CityStore.instance.city.name;
    final parts = <String>[
      _monthDay(),
      city,
      if (picks.weather?.temperatureC != null)
        '${picks.weather!.temperatureC!.round()}°',
    ];
    return Opacity(
      opacity: 0.62 + 0.38 * v,
      child: RotatedBox(
        quarterTurns: 3,
        child: Text(
          parts.join(' · '),
          style: TextStyle(
            fontSize: 10,
            letterSpacing: 1.6,
            color: _paper.withValues(alpha: 0.82),
          ),
        ),
      ),
    );
  }
}

// ---------- 下半屏：纸面 ----------

class _Sheet extends StatelessWidget {
  const _Sheet({
    required this.picks,
    required this.t,
    required this.onOpenRecipes,
    required this.onOpenAi,
  });

  final HomePicks picks;
  final double t;
  final VoidCallback onOpenRecipes;
  final VoidCallback onOpenAi;

  @override
  Widget build(BuildContext context) {
    final v = _easeOut(_Span(0.30, 0.74).at(t));
    final recipes = picks.recipes.take(3).toList();
    return Transform.translate(
      // 纸面只做位移、永不透明：它是内容的容器，动画卡住也不能消失
      offset: Offset(0, 60 * (1 - v)),
      child: Container(
        constraints: const BoxConstraints(minHeight: 520),
        decoration: const BoxDecoration(
          color: _paper,
          borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
        ),
        padding: const EdgeInsets.fromLTRB(22, 24, 22, 26),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            _SheetHeader(picks: picks, t: t, count: recipes.length),
            const SizedBox(height: 14),
            for (var i = 0; i < recipes.length; i++)
              _DishRow(
                recipe: recipes[i],
                index: i,
                t: t,
                onTap: onOpenRecipes,
              ),
            if (recipes.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 18),
                child: Text(
                  '暂时没有符合条件的菜，去「菜谱」里翻翻',
                  style: TextStyle(fontSize: 13, color: _inkSoft),
                ),
              ),
            const SizedBox(height: 8),
            _SheetFooter(
              picks: picks,
              t: t,
              onOpenRecipes: onOpenRecipes,
              onOpenAi: onOpenAi,
            ),
          ],
        ),
      ),
    );
  }
}

class _SheetHeader extends StatelessWidget {
  const _SheetHeader({
    required this.picks,
    required this.t,
    required this.count,
  });

  final HomePicks picks;
  final double t;
  final int count;

  @override
  Widget build(BuildContext context) {
    final v = _easeOut(_Span(0.56, 0.92).at(t));
    // 标题已经是季节了，这里换成首道菜的第一个标签，别重复
    final tag = picks.recipes.isNotEmpty && picks.recipes.first.tags.isNotEmpty
        ? picks.recipes.first.tags.first
        : _seasonLabel(picks);
    return Opacity(
      opacity: 0.62 + 0.38 * v,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: <Widget>[
              const Text(
                '今日宜',
                style: TextStyle(
                  fontFamily: _fontDisplay,
                  fontSize: 24,
                  color: _ink,
                  letterSpacing: 2,
                ),
              ),
              const SizedBox(width: 10),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(color: _paperDim),
                child: Text(
                  tag,
                  style: const TextStyle(
                    fontSize: 11,
                    color: _inkSoft,
                    letterSpacing: 0.6,
                  ),
                ),
              ),
              const Spacer(),
              Text(
                '${count.toString().padLeft(2, '0')} 道',
                style: const TextStyle(
                  fontSize: 10.5,
                  color: _inkSoft,
                  letterSpacing: 1.4,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Container(height: 1.2, color: _ink.withValues(alpha: 0.82)),
        ],
      ),
    );
  }
}

class _DishRow extends StatelessWidget {
  const _DishRow({
    required this.recipe,
    required this.index,
    required this.t,
    required this.onTap,
  });

  final Recipe recipe;
  final int index;
  final double t;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final start = 0.60 + index * 0.09;
    final v = _easeOut(_Span(start, start + 0.28).at(t));
    return Opacity(
      opacity: 0.62 + 0.38 * v,
      child: Transform.translate(
        offset: Offset(0, 16 * (1 - v)),
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 13),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                ClipRRect(
                  borderRadius: BorderRadius.circular(1),
                  child: SizedBox(
                    width: 78,
                    height: 78,
                    child: DishPhoto(asset: recipe.image, fit: BoxFit.cover),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Row(
                        children: <Widget>[
                          Expanded(
                            child: Text(
                              recipe.name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontFamily: _fontDisplay,
                                fontSize: 19,
                                height: 1.25,
                                color: _ink,
                              ),
                            ),
                          ),
                          Text(
                            (index + 1).toString().padLeft(2, '0'),
                            style: TextStyle(
                              fontSize: 11,
                              color: _inkSoft.withValues(alpha: 0.55),
                              letterSpacing: 1,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        (picksReasonOrDesc(recipe)),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 12.5,
                          height: 1.65,
                          color: _inkSoft,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: <Widget>[
                          _Tag(text: '约 ${recipe.time}'),
                          if (recipe.tags.isNotEmpty) _Tag(text: recipe.tags.first),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

String picksReasonOrDesc(Recipe recipe) {
  final desc = recipe.desc.trim();
  return desc.isEmpty ? '顺时而食，做法见菜谱详情' : desc;
}

class _Tag extends StatelessWidget {
  const _Tag({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2.5),
      decoration: BoxDecoration(
        border: Border.all(color: _inkSoft.withValues(alpha: 0.32), width: 0.8),
        borderRadius: BorderRadius.circular(1),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 10.5,
          color: _inkSoft,
          letterSpacing: 0.3,
        ),
      ),
    );
  }
}

class _SheetFooter extends StatelessWidget {
  const _SheetFooter({
    required this.picks,
    required this.t,
    required this.onOpenRecipes,
    required this.onOpenAi,
  });

  final HomePicks picks;
  final double t;
  final VoidCallback onOpenRecipes;
  final VoidCallback onOpenAi;

  @override
  Widget build(BuildContext context) {
    final v = _easeOut(_Span(0.80, 1.0).at(t));
    final note = picks.notes.isNotEmpty
        ? picks.notes.first
        : '按当季食材与家庭条件筛出，做法见菜谱详情';
    return Opacity(
      opacity: 0.62 + 0.38 * v,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Container(height: 0.8, color: _ink.withValues(alpha: 0.18)),
          const SizedBox(height: 16),
          Text(
            note,
            style: const TextStyle(fontSize: 12, height: 1.7, color: _inkSoft),
          ),
          const SizedBox(height: 16),
          Row(
            children: <Widget>[
              Expanded(
                child: _SheetButton(
                  label: '看全部菜谱',
                  filled: true,
                  onTap: onOpenRecipes,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _SheetButton(
                  label: '问 AI 怎么搭配',
                  filled: false,
                  onTap: onOpenAi,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SheetButton extends StatelessWidget {
  const _SheetButton({
    required this.label,
    required this.filled,
    required this.onTap,
  });

  final String label;
  final bool filled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        height: 42,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: filled ? _moss : Colors.transparent,
          border: filled
              ? null
              : Border.all(color: _inkSoft.withValues(alpha: 0.45), width: 0.9),
          borderRadius: BorderRadius.circular(2),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12.5,
            letterSpacing: 0.5,
            color: filled ? _paper : _inkSoft,
          ),
        ),
      ),
    );
  }
}

// ---------- 印刷颗粒 ----------

class _GrainPainter extends CustomPainter {
  const _GrainPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final rnd = math.Random(20261110);
    final paint = Paint()..style = PaintingStyle.fill;
    // 固定种子：每次重建的位置一样，不会闪
    for (var i = 0; i < 900; i++) {
      final dx = rnd.nextDouble() * size.width;
      final dy = rnd.nextDouble() * size.height;
      final a = 0.012 + rnd.nextDouble() * 0.02;
      paint.color = (rnd.nextBool() ? Colors.black : Colors.white)
          .withValues(alpha: a);
      canvas.drawCircle(Offset(dx, dy), 0.6 + rnd.nextDouble() * 0.7, paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// ---------- 小工具 ----------

String _seasonLabel(HomePicks picks) {
  final feed = HomeFeedStore.instance.feed;
  final name = feed?.seasonName;
  if (name != null && name.trim().isNotEmpty) return name.trim();
  return '$currentSeasonChar季';
}

String _monthDay() {
  final now = DateTime.now();
  return '${now.month}月${now.day}日';
}
