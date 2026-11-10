import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

// =====================================================================
// 食时 · Design v3「墨绿重彩」 —— 大胆版首屏
//
// 与 v2「节令历书」的区别：
//   v2 是一张留白的纸；v3 是一张有照片、有深色块、有笔锋的封面。
//   信息结构相同，所以两者可以逐块对比取舍。
//
// 运行：
//   cd team/front/mealmind
//   flutter run -t lib/preview/design_v3.dart -d chrome
//   加 --dart-define=STATIC=true 会直接落到动画终点（截图用）。
//
// 这一版新增的三样东西：
//   1. 毛笔字 MaShanZheng（马善政）—— 节气大字不再用黑体硬撑
//   2. 展示宋楷 ZCOOLXiaoWei（站酷小薇）—— 菜名、栏目标题
//   3. 通幅大图 + 深色渐变遮罩 + 纸质颗粒
// 两款字体均为 SIL OFL，可随应用再分发（需登记进开源资源清单）。
// =====================================================================

// ---------- 1. token ----------

class V3Color {
  const V3Color._();

  static const inkDeep = Color(0xFF0F1C15); // 最深墨绿：遮罩、深色底
  static const moss = Color(0xFF2A4A34);
  static const mossSoft = Color(0xFF6E8873);

  static const paper = Color(0xFFF5EFE1); // 宣纸
  static const paperDim = Color(0xFFE9E1CE);
  static const card = Color(0xFFFBF7EC);

  static const brass = Color(0xFFB98A3E); // 黄铜：当季/温补这类小标记
  static const seal = Color(0xFFB04A34); // 朱砂
  static const line = Color(0xFFD5C9AE);
}

class V3Font {
  const V3Font._();
  static const brush = 'MaShanZheng';
  static const display = 'ZCOOLXiaoWei';
  static const sans = 'NotoSansSC';
}

class V3Curve {
  const V3Curve._();
  static const settle = Cubic(0.16, 1.0, 0.3, 1.0);
  static const rise = Cubic(0.22, 1.0, 0.28, 1.0);
  static const pop = Cubic(0.34, 1.56, 0.64, 1.0);
}

// ---------- 2. 入口 ----------

void main() => runApp(const PreviewAppV3());

class PreviewAppV3 extends StatelessWidget {
  const PreviewAppV3({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: '食时 · Design v3',
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: V3Color.paper,
        fontFamily: V3Font.sans,
        colorScheme: ColorScheme.fromSeed(
          seedColor: V3Color.moss,
          surface: V3Color.paper,
        ),
      ),
      home: const EditorialHome(),
    );
  }
}

// ---------- 3. 首屏 ----------

class EditorialHome extends StatefulWidget {
  const EditorialHome({super.key});

  @override
  State<EditorialHome> createState() => _EditorialHomeState();
}

class _EditorialHomeState extends State<EditorialHome>
    with TickerProviderStateMixin {
  late final AnimationController _intro;
  late final AnimationController _ken;

  @override
  void initState() {
    super.initState();
    _intro = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    );
    // 14 秒一个往返：镜头在盘子上缓慢推近再退回
    _ken = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 14),
    );
    _intro.forward();
    _ken.repeat(reverse: true);
    // 兜底：3 秒后无论如何把入场推到终点。
    // 浏览器在后台标签页会节流 rAF，回来时动画可能停在半路——
    // 那样整页会卡在淡入的中间态（看起来就是「黑屏」）。
    Timer(const Duration(seconds: 3), () {
      if (mounted && _intro.value < 1) _intro.value = 1;
    });
  }

  @override
  void dispose() {
    _intro.dispose();
    _ken.dispose();
    super.dispose();
  }

  // 三种情况直接落到动画终点：系统开了「减少动效」、构建时加了 STATIC、
  // 或者 URL 带 ?static —— 最后一种是为了在无头浏览器里截图时不受动画时序影响。
  bool get _static =>
      MediaQuery.of(context).disableAnimations ||
      const bool.fromEnvironment('STATIC') ||
      Uri.base.queryParameters.containsKey('static');

  @override
  Widget build(BuildContext context) {
    final Animation<double> progress =
        _static ? const AlwaysStoppedAnimation<double>(1.0) : _intro;

    return Scaffold(
      // 桌面色：桌面浏览器里让手机版面浮在深底上，而不是拉满整屏
      backgroundColor: const Color(0xFF0B120E),
      body: LayoutBuilder(
        builder: (context, frame) => Center(
          child: SizedBox(
            width: math.min(480.0, frame.maxWidth),
            height: frame.maxHeight,
            child: Stack(
              children: [
                LayoutBuilder(
                builder: (context, box) {
                  // 大图占屏幕 46%，纸面往上压 26px 盖住它的下沿
                  final heroHeight = math.max(300.0, box.maxHeight * 0.46);
                  return Stack(
                    children: [
                      Positioned(
                        top: 0,
                        left: 0,
                        right: 0,
                        height: heroHeight,
                        child: _Hero(
                          progress: progress,
                          ken: _static
                              ? const AlwaysStoppedAnimation<double>(0.0)
                              : _ken,
                        ),
                      ),
                      SingleChildScrollView(
                        physics: const BouncingScrollPhysics(),
                        padding: EdgeInsets.only(top: heroHeight - 26),
                        child: _PaperSheet(
                          progress: progress,
                          // 屏幕高时纸面也要盖到屏幕底，否则下面会露出墨绿底
                          minHeight:
                              math.max(0.0, box.maxHeight - heroHeight + 30),
                        ),
                      ),
                    ],
                  );
                },
              ),
              // 纸张颗粒压在最上层，让整页有印刷质感
                if (!_static)
                  const Positioned.fill(
                    child: IgnorePointer(
                      child: CustomPaint(painter: _GrainPainter()),
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

// ---------- 4. 大图区 ----------

class _Hero extends StatelessWidget {
  const _Hero({required this.progress, required this.ken});

  final Animation<double> progress;
  final Animation<double> ken;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge(<Listenable>[progress, ken]),
      builder: (context, _) {
        final t = progress.value;
        final deck = ConstrainedInterval(0.0, 0.60, V3Curve.settle).at(t);
        // 入场时从 1.05 收到 1.0，之后交给 ken 慢慢推近
        final kenScale = 1.0 + 0.05 * ken.value;
        final scale = (1.05 - 0.05 * deck) * kenScale;

        // ClipRect：高斯模糊会向外溢出，不裁的话在桌面宽屏上会糊到版面之外
        return ClipRect(
          child: Stack(
            fit: StackFit.expand,
            children: [
            // 底层：同一张图放大后重度高斯模糊。
            // 原始素材只有 480×300，铺满全屏在视网膜屏上必然发虚；
            // 与其硬撑清晰度，不如让它当一层氛围底，把「清晰的那张」留给右侧小图。
            ImageFiltered(
              imageFilter: ui.ImageFilter.blur(sigmaX: 20, sigmaY: 20),
              child: Transform.scale(
                scale: scale * 1.16,
                child: Image.asset(
                  'assets/images/dish-114762-chestnut-braised-pork-ribs.jpg',
                  fit: BoxFit.cover,
                  filterQuality: FilterQuality.medium,
                  errorBuilder: (_, __, ___) =>
                      const ColoredBox(color: V3Color.moss),
                ),
              ),
            ),
            // 上浅下深：保证白字可读
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    V3Color.inkDeep.withValues(alpha: 0.42 * deck),
                    V3Color.inkDeep.withValues(alpha: 0.30 * deck),
                    V3Color.inkDeep.withValues(alpha: 0.92 * deck),
                  ],
                  stops: const <double>[0.0, 0.45, 1.0],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 18, 24, 34),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  _HeroTopBar(progress: progress),
                  const Spacer(),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: <Widget>[
                      Expanded(child: _BrushTitle(progress: progress)),
                      const SizedBox(width: 12),
                      _InsetPhoto(progress: progress),
                    ],
                  ),
                  const SizedBox(height: 16),
                  // 说明文字独占整行，不再被右侧小图挤成窄条
                  _HeroCaption(progress: progress),
                ],
              ),
            ),
            Positioned(
              right: 14,
              top: 74,
              child: _VerticalMeta(progress: progress),
            ),
          ],
          ),
        );
      },
    );
  }
}

class _HeroTopBar extends StatelessWidget {
  const _HeroTopBar({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    final t =
        ConstrainedInterval(0.05, 0.42, V3Curve.settle).at(progress.value);
    return Opacity(
      opacity: 0.62 + 0.38 * t,
      child: Row(
        children: <Widget>[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
            decoration: BoxDecoration(
              color: V3Color.paper,
              borderRadius: BorderRadius.circular(3),
            ),
            child: const Text(
              '食时',
              style: TextStyle(
                fontFamily: V3Font.brush,
                fontSize: 17,
                height: 1.1,
                color: V3Color.moss,
              ),
            ),
          ),
          const SizedBox(width: 10),
          const Text(
            'SHI SHI',
            style: TextStyle(
              fontSize: 9,
              letterSpacing: 3.2,
              color: V3Color.paperDim,
            ),
          ),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              border: Border.all(color: V3Color.paper.withValues(alpha: 0.34)),
              borderRadius: BorderRadius.circular(3),
            ),
            child: const Text(
              '立 冬',
              style: TextStyle(
                fontSize: 10,
                letterSpacing: 2,
                color: V3Color.paper,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 毛笔大字：按字逐个「从上往下刷」出来，像一笔一笔写上去。
class _BrushTitle extends StatelessWidget {
  const _BrushTitle({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: <Widget>[
        _brushChar('立', 0.14, 0.52),
        _brushChar('冬', 0.24, 0.62),
      ],
    );
  }

  Widget _brushChar(String ch, double a, double b) {
    final t = ConstrainedInterval(a, b, V3Curve.rise).at(progress.value);
    return Align(
      heightFactor: t.clamp(0.0, 1.0),
      alignment: Alignment.bottomLeft,
      child: Text(
        ch,
        style: const TextStyle(
          fontFamily: V3Font.brush,
          fontSize: 104,
          height: 1.0,
          color: V3Color.paper,
        ),
      ),
    );
  }
}

class _HeroCaption extends StatelessWidget {
  const _HeroCaption({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    final t =
        ConstrainedInterval(0.52, 0.86, V3Curve.settle).at(progress.value);
    return Opacity(
      opacity: 0.62 + 0.38 * t,
      child: Transform.translate(
        offset: Offset(0, 10 * (1 - t)),
        child: const Text(
          '水始冰，地始冻 —— 今天适合吃点需要时间的菜。',
          style: TextStyle(
            fontFamily: V3Font.display,
            fontSize: 14,
            height: 1.7,
            letterSpacing: 0.6,
            color: V3Color.paper,
          ),
        ),
      ),
    );
  }
}

class _VerticalMeta extends StatelessWidget {
  const _VerticalMeta({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    final t =
        ConstrainedInterval(0.40, 0.78, V3Curve.settle).at(progress.value);
    return Opacity(
      opacity: 0.62 + 0.38 * t,
      child: RotatedBox(
        quarterTurns: 1,
        child: Text(
          '十一月十日 · 杭州 14°',
          maxLines: 1,
          style: TextStyle(
            fontSize: 10.5,
            letterSpacing: 3.0,
            color: V3Color.paper.withValues(alpha: 0.8),
          ),
        ),
      ),
    );
  }
}

/// 小图：raw 素材 480×300，这里只显示 112×84（视网膜屏下 224×168），
/// 采样率比源图还低，所以是整页唯一「清楚」的那块菜。
class _InsetPhoto extends StatelessWidget {
  const _InsetPhoto({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    final t =
        ConstrainedInterval(0.58, 0.95, V3Curve.settle).at(progress.value);
    return Opacity(
      opacity: 0.62 + 0.38 * t.clamp(0.0, 1.0),
      child: Transform.translate(
        offset: Offset(0, 14 * (1 - t)),
        child: Container(
          padding: const EdgeInsets.all(3),
          decoration: BoxDecoration(
            color: V3Color.paper,
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
              width: 112,
              height: 84,
              child: Image.asset(
                'assets/images/dish-114762-chestnut-braised-pork-ribs.jpg',
                fit: BoxFit.cover,
                filterQuality: FilterQuality.high,
                errorBuilder: (_, __, ___) =>
                    const ColoredBox(color: V3Color.paperDim),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ---------- 5. 纸面 ----------

class _PaperSheet extends StatelessWidget {
  const _PaperSheet({required this.progress, required this.minHeight});

  final Animation<double> progress;
  final double minHeight;

  @override
  Widget build(BuildContext context) {
    final t =
        ConstrainedInterval(0.30, 0.74, V3Curve.rise).at(progress.value);

    // 纸面本身永远不透明：它是整页内容的容器，任何动画卡住都不能让它消失。
    // 入场只做「从下浮上来」的位移，不做淡入——淡入一旦停在 0 就是一大片黑。
    return Transform.translate(
      offset: Offset(0, 60 * (1 - t)),
      child: Container(
          constraints: BoxConstraints(minHeight: minHeight),
          decoration: const BoxDecoration(
            color: V3Color.paper,
            borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
          ),
          padding: const EdgeInsets.fromLTRB(22, 26, 22, 44),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              _SheetHeader(progress: progress),
              const SizedBox(height: 18),
              for (var i = 0; i < _dishes.length; i++)
                Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: _DishRow(
                    data: _dishes[i],
                    progress: progress,
                    index: i,
                  ),
                ),
              const SizedBox(height: 6),
              _SheetFooter(progress: progress),
            ],
          ),
        ),
    );
  }
}

class _SheetHeader extends StatelessWidget {
  const _SheetHeader({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    final t =
        ConstrainedInterval(0.56, 0.92, V3Curve.settle).at(progress.value);
    return Opacity(
      opacity: 0.62 + 0.38 * t,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: <Widget>[
              const Text(
                '今日宜',
                style: TextStyle(
                  fontFamily: V3Font.display,
                  fontSize: 26,
                  height: 1.2,
                  letterSpacing: 2,
                  color: V3Color.inkDeep,
                ),
              ),
              const SizedBox(width: 10),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                  color: V3Color.brass.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(3),
                ),
                child: const Text(
                  '温 补',
                  style: TextStyle(
                    fontSize: 11,
                    letterSpacing: 2,
                    color: V3Color.brass,
                  ),
                ),
              ),
              const Spacer(),
              const Text(
                '03 道',
                style: TextStyle(
                  fontSize: 11,
                  letterSpacing: 2,
                  color: V3Color.mossSoft,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Container(height: 1.2, color: V3Color.inkDeep),
        ],
      ),
    );
  }
}

/// 菜品行：方形大图 + 名称 + 理由 + 标记。
/// 不用卡片阴影，用细线分隔 —— 更像菜谱目录，而不是一堆 Material 卡片。
class _DishRow extends StatelessWidget {
  const _DishRow({
    required this.data,
    required this.progress,
    required this.index,
  });

  final _Dish data;
  final Animation<double> progress;
  final int index;

  @override
  Widget build(BuildContext context) {
    final start = 0.62 + index * 0.07;
    final t =
        ConstrainedInterval(start, start + 0.30, V3Curve.settle).at(
      progress.value,
    );

    return Opacity(
      opacity: 0.62 + 0.38 * t.clamp(0.0, 1.0),
      child: Transform.translate(
        offset: Offset(24 * (1 - t), 0),
        child: Container(
          padding: const EdgeInsets.only(bottom: 14),
          decoration: const BoxDecoration(
            border: Border(
              bottom: BorderSide(color: V3Color.line, width: 1),
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: SizedBox(
                  width: 92,
                  height: 92,
                  child: Image.asset(
                    data.image,
                    fit: BoxFit.cover,
                    filterQuality: FilterQuality.medium,
                    errorBuilder: (_, __, ___) =>
                        const ColoredBox(color: V3Color.paperDim),
                  ),
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
                            data.name,
                            style: const TextStyle(
                              fontFamily: V3Font.display,
                              fontSize: 21,
                              height: 1.25,
                              letterSpacing: 0.5,
                              color: V3Color.inkDeep,
                            ),
                          ),
                        ),
                        Text(
                          '0${index + 1}',
                          style: TextStyle(
                            fontFamily: V3Font.display,
                            fontSize: 13,
                            color: V3Color.mossSoft.withValues(alpha: 0.7),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      data.reason,
                      style: const TextStyle(
                        fontSize: 12.5,
                        height: 1.65,
                        color: V3Color.moss,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: <Widget>[
                        _Tag(text: data.minutes, accent: false),
                        const SizedBox(width: 6),
                        _Tag(text: data.tag, accent: true),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag({required this.text, required this.accent});

  final String text;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final Color color = accent ? V3Color.brass : V3Color.mossSoft;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        border: Border.all(color: color.withValues(alpha: 0.45)),
        borderRadius: BorderRadius.circular(3),
      ),
      child: Text(
        text,
        style: TextStyle(fontSize: 10.5, letterSpacing: 0.8, color: color),
      ),
    );
  }
}

class _SheetFooter extends StatelessWidget {
  const _SheetFooter({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    final t =
        ConstrainedInterval(0.80, 1.0, V3Curve.settle).at(progress.value);
    final pop =
        ConstrainedInterval(0.82, 1.0, V3Curve.pop).at(progress.value);

    return Opacity(
      opacity: 0.62 + 0.38 * t.clamp(0.0, 1.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: <Widget>[
          Expanded(
            child: Text(
              '以上三道按「立冬·温补」从 700 道菜里筛出，'
              '每道都写了它为什么今天合适。',
              style: TextStyle(
                fontSize: 12,
                height: 1.75,
                color: V3Color.moss.withValues(alpha: 0.85),
              ),
            ),
          ),
          const SizedBox(width: 14),
          Transform.scale(
            scale: pop.clamp(0.0, 1.2),
            child: const _Seal(),
          ),
        ],
      ),
    );
  }
}

class _Seal extends StatelessWidget {
  const _Seal();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        color: V3Color.seal,
        borderRadius: BorderRadius.circular(3),
      ),
      child: const Center(
        child: Text(
          '食时',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: V3Font.brush,
            fontSize: 17,
            height: 1.0,
            color: V3Color.paper,
          ),
        ),
      ),
    );
  }
}

// ---------- 6. 工具 ----------

/// 一次性进度值 + 区间 + 缓动。
/// 比 Interval 更适合这种「一个 controller 驱动整条时间轴」的写法，
/// 也保证任何时刻都返回 0..1，不用每处手写 clamp。
class ConstrainedInterval {
  const ConstrainedInterval(this.start, this.end, this.curve);

  final double start;
  final double end;
  final Curve curve;

  double at(double raw) {
    final v = raw.clamp(0.0, 1.0);
    if (v <= start) return 0;
    if (v >= end) return 1;
    return curve.transform((v - start) / (end - start));
  }
}

/// 印刷颗粒：固定种子，画一次，不参与重绘。
class _GrainPainter extends CustomPainter {
  const _GrainPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final rnd = math.Random(20261110);
    final paint = Paint();
    for (var i = 0; i < 1600; i++) {
      final x = rnd.nextDouble() * size.width;
      final y = rnd.nextDouble() * size.height;
      final a = 0.012 + rnd.nextDouble() * 0.030;
      paint.color = (rnd.nextDouble() > 0.5 ? Colors.white : Colors.black)
          .withValues(alpha: a);
      canvas.drawRect(Rect.fromLTWH(x, y, 1, 1), paint);
    }
    // 几根长纤维，模拟纸张纹路
    for (var i = 0; i < 26; i++) {
      final x = rnd.nextDouble() * size.width;
      final y = rnd.nextDouble() * size.height;
      final len = 12 + rnd.nextDouble() * 46;
      paint.color = Colors.black.withValues(alpha: 0.016);
      canvas.drawRect(Rect.fromLTWH(x, y, len, 1), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// ---------- 7. 内容 ----------

class _Dish {
  const _Dish(this.name, this.reason, this.minutes, this.tag, this.image);

  final String name;
  final String reason;
  final String minutes;
  final String tag;
  final String image;
}

const List<_Dish> _dishes = <_Dish>[
  _Dish(
    '番茄土豆炖牛腩',
    '炖菜用最长的等待换最稳的温度，适合入冬第一周。',
    '约 90 分钟',
    '温补',
    'assets/images/dish-023880-tomato-braised-beef.jpg',
  ),
  _Dish(
    '板栗烧排骨',
    '板栗正当季，甜味能把咸鲜收住，不用额外放糖。',
    '约 60 分钟',
    '当季',
    'assets/images/dish-114762-chestnut-braised-pork-ribs.jpg',
  ),
  _Dish(
    '羊肉炖萝卜',
    '立冬的羊肉配白萝卜，去膻又暖，一锅够三个人。',
    '约 75 分钟',
    '家常',
    'assets/images/dish-102022-lamb-radish-stew.jpg',
  ),
];
