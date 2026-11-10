import 'dart:math' as math;
import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

// =====================================================================
// 食时 · Design v2 「节令历书」 —— 首屏样板（独立预览，不接任何现有页面）
//
// 运行：
//   cd team/front/mealmind
//   flutter run -t lib/preview/design_v2.dart -d chrome
//
// 这一版只做三件事，都在这一个文件里：
//   1. 把 theme.dart 的 54 行颜色表扩成真正可用的 token（色 / 字号 / 间距 / 曲线）
//   2. 首屏：宣纸底 + 晨雾缓慢流动 + 节气大字 + 朱砂印
//   3. 品牌字标以「墨迹扩散」入场，三张卡片错峰浮现
//
// 动效全部可被系统「减弱动态效果」关掉（MediaQuery.disableAnimations）。
// =====================================================================

// ---------- 1. 设计 token ----------

class V2Color {
  const V2Color._();

  // 宣纸底：比现有 brand50 更暖，偏黄，像旧书页
  static const paper = Color(0xFFF7F3E8);
  static const paperDeep = Color(0xFFEFE7D5);

  // 墨：标题用 ink，正文用 inkSoft
  static const ink = Color(0xFF1C2B21);
  static const inkSoft = Color(0xFF4E5C52);

  // 主绿：比现有 green900 更深一点，更像墨绿
  static const moss = Color(0xFF2F4B36);
  static const mossSoft = Color(0xFF6E8873);

  // 朱砂：只给印章与「当季」这类极少量强调
  static const seal = Color(0xFFA23E30);

  static const line = Color(0xFFDCD3BE);
  static const card = Color(0xFFFFFDF6);
}

class V2Space {
  const V2Space._();
  static const xs = 6.0;
  static const sm = 10.0;
  static const md = 16.0;
  static const lg = 24.0;
  static const xl = 36.0;
  static const xxl = 56.0;
}

class V2Type {
  const V2Type._();
  // 只有 Regular 一个字重，所以层级靠「字号 + 字距 + 颜色」三重叠加，
  // 而不是靠字重——这是现有字体条件下的最优解。
  static const solarTerm = 92.0; // 节气大字
  static const h1 = 30.0;
  static const h2 = 19.0;
  static const body = 15.0;
  static const cap = 11.0;

  static const trackingSolar = 10.0;
  static const trackingCap = 2.4;
}

class V2Curve {
  const V2Curve._();
  static const settle = Cubic(0.16, 1.0, 0.3, 1.0); // 落位
  static const spread = Cubic(0.22, 0.61, 0.36, 1.0); // 墨迹铺开
}

// ---------- 2. 入口 ----------

void main() => runApp(const PreviewApp());

class PreviewApp extends StatelessWidget {
  const PreviewApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: '食时 · Design v2',
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: V2Color.paper,
        fontFamily: 'NotoSansSC',
        colorScheme: ColorScheme.fromSeed(
          seedColor: V2Color.moss,
          surface: V2Color.paper,
        ),
      ),
      home: const SolarTermHome(),
    );
  }
}

// ---------- 3. 首屏 ----------

class SolarTermHome extends StatefulWidget {
  const SolarTermHome({super.key});

  @override
  State<SolarTermHome> createState() => _SolarTermHomeState();
}

class _SolarTermHomeState extends State<SolarTermHome>
    with TickerProviderStateMixin {
  late final AnimationController _intro;
  late final AnimationController _drift;

  // 入场时间轴（毫秒）：雾 → 墨迹 → 大字 → 卡片
  static const _inkWindow = Interval(0.10, 0.62, curve: V2Curve.spread);
  static const _titleWindow = Interval(0.34, 0.72, curve: V2Curve.settle);
  static const _sealWindow = Interval(0.56, 0.80, curve: V2Curve.settle);

  @override
  void initState() {
    super.initState();
    _intro = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1900),
    );
    // 40 秒一循环：慢到几乎察觉不到在动，但停下来就看得出是活的
    _drift = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 40),
    );
    _intro.forward();
    _drift.repeat();
  }

  @override
  void dispose() {
    _intro.dispose();
    _drift.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // STATIC=true 时直接落到动画终点，用于截图核对静态排版。
    // 正常运行时由系统「减弱动态效果」或 STATIC 决定是否播放入场。
    final reduceMotion =
        MediaQuery.of(context).disableAnimations ||
        const bool.fromEnvironment('STATIC');

    final intro = reduceMotion
        ? const AlwaysStoppedAnimation<double>(1.0)
        : _intro;

    return Scaffold(
      backgroundColor: V2Color.paper,
      body: Stack(
        children: [
          // 背景：宣纸 + 晨雾
          Positioned.fill(
            child: DecoratedBox(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [V2Color.paper, V2Color.paperDeep],
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: IgnorePointer(
              child: AnimatedBuilder(
                animation: _drift,
                builder: (_, __) => CustomPaint(
                  painter: _MorningFogPainter(
                    t: reduceMotion ? 0.0 : _drift.value,
                    seed: 11,
                  ),
                ),
              ),
            ),
          ),
          SafeArea(
            child: LayoutBuilder(
              builder: (context, box) {
                final narrow = box.maxWidth < 520;
                return Align(
                  alignment: Alignment.topCenter,
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 430),
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: EdgeInsets.fromLTRB(
                        narrow ? V2Space.lg : V2Space.xl,
                        V2Space.md,
                        narrow ? V2Space.lg : V2Space.xl,
                        V2Space.xl,
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _BrandMark(progress: intro),
                          const SizedBox(height: V2Space.xl),
                          _MetaRow(progress: intro),
                          const SizedBox(height: V2Space.md),
                          _Rule(progress: intro),
                          const SizedBox(height: V2Space.lg),
                          _SolarTermTitle(progress: intro),
                          const SizedBox(height: V2Space.md),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.center,
                            children: [
                              Expanded(child: _Tagline(progress: intro)),
                              const SizedBox(width: V2Space.md),
                              _SealStamp(progress: intro),
                            ],
                          ),
                          const SizedBox(height: V2Space.xl),
                          _SectionLabel(progress: intro),
                          const SizedBox(height: V2Space.md),
                          for (var i = 0; i < _dishes.length; i++)
                            Padding(
                              padding: const EdgeInsets.only(
                                bottom: V2Space.md,
                              ),
                              child: _DishCard(
                                data: _dishes[i],
                                progress: intro,
                                index: i,
                              ),
                            ),
                          const SizedBox(height: V2Space.sm),
                          _Footnote(progress: intro),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

// ---------- 4. 组件 ----------

/// 品牌字标：墨迹由中心向外铺开，边缘一开始模糊、落定后收干。
class _BrandMark extends StatelessWidget {
  const _BrandMark({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: progress,
      builder: (context, child) {
        final t = const Interval(0.10, 0.62, curve: V2Curve.spread)
            .transform(progress.value.clamp(0.0, 1.0));
        // 铺开半径 0.18 → 1.15，边缘从虚到实
        final radius = 0.16 + 0.99 * t;
        final blur = 7.0 * (1 - t);
        final scale = 1.035 - 0.035 * t;

        return Opacity(
          opacity: t.clamp(0.0, 1.0),
          child: Transform.scale(
            scale: scale,
            alignment: Alignment.centerLeft,
            child: ImageFiltered(
              imageFilter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
              child: ShaderMask(
                blendMode: BlendMode.dstIn,
                shaderCallback: (rect) => RadialGradient(
                  center: const Alignment(-0.25, 0.05),
                  radius: radius,
                  colors: const [
                    Colors.black,
                    Colors.black,
                    Color(0x00000000),
                  ],
                  stops: const [0.0, 0.72, 1.0],
                ).createShader(rect),
                child: child,
              ),
            ),
          ),
        );
      },
      child: const _WordmarkImage(width: 132),
    );
  }
}

/// 直接复用仓库里已有的书法字标（splash.png 的裁切区域）。
class _WordmarkImage extends StatelessWidget {
  const _WordmarkImage({required this.width});

  final double width;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      child: AspectRatio(
        // 只裁到书法字基本身（445×230），把下面那行小标语切掉：
        // 那行字在 132px 宽下缩得只剩一排墨点，反而像渲染坏了。
        aspectRatio: 445 / 230,
        child: FittedBox(
          fit: BoxFit.contain,
          child: SizedBox(
            width: 445,
            height: 230,
            child: ClipRect(
              child: Stack(
                children: [
                  Positioned(
                    left: -250,
                    top: -735,
                    width: 941,
                    height: 1672,
                    child: Image.asset(
                      'assets/images/splash.png',
                      fit: BoxFit.fill,
                      excludeFromSemantics: true,
                      // splash.png 是不透明的白底。乘上纸色后白底恰好等于背景色，
                      // 等于免费得到了一个去白底的透明字标，不用重新导图。
                      color: V2Color.paper,
                      colorBlendMode: BlendMode.multiply,
                      errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _MetaRow extends StatelessWidget {
  const _MetaRow({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    return _FadeUp(
      progress: progress,
      window: const Interval(0.30, 0.66, curve: V2Curve.settle),
      child: Row(
        children: [
          Text(
            '立冬 · 十一月十日',
            style: const TextStyle(
              fontSize: V2Type.cap,
              letterSpacing: V2Type.trackingCap,
              color: V2Color.inkSoft,
            ),
          ),
          const Spacer(),
          Container(
            width: 5,
            height: 5,
            decoration: const BoxDecoration(
              color: V2Color.seal,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: V2Space.xs),
          const Text(
            '杭州 14°',
            style: TextStyle(
              fontSize: V2Type.cap,
              letterSpacing: V2Type.trackingCap,
              color: V2Color.inkSoft,
            ),
          ),
        ],
      ),
    );
  }
}

class _Rule extends StatelessWidget {
  const _Rule({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: progress,
      builder: (context, _) {
        final t = const Interval(0.34, 0.78, curve: V2Curve.settle)
            .transform(progress.value.clamp(0.0, 1.0));
        return Align(
          alignment: Alignment.centerLeft,
          child: Container(
            height: 1,
            width: 268 * t,
            color: V2Color.line,
          ),
        );
      },
    );
  }
}

class _SolarTermTitle extends StatelessWidget {
  const _SolarTermTitle({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    return _FadeUp(
      progress: progress,
      window: const Interval(0.34, 0.72, curve: V2Curve.settle),
      offset: 18,
      child: const FittedBox(
        fit: BoxFit.scaleDown,
        alignment: Alignment.centerLeft,
        child: Text(
          '立冬',
          maxLines: 1,
          style: TextStyle(
            fontSize: V2Type.solarTerm,
            height: 1.06,
            letterSpacing: V2Type.trackingSolar,
            color: V2Color.ink,
          ),
        ),
      ),
    );
  }
}

class _Tagline extends StatelessWidget {
  const _Tagline({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    return _FadeUp(
      progress: progress,
      window: const Interval(0.46, 0.84, curve: V2Curve.settle),
      child: const Text(
        '水始冰，地始冻。\n收一收，吃点热的。',
        style: TextStyle(
          fontSize: V2Type.body,
          height: 1.95,
          letterSpacing: 1.2,
          color: V2Color.inkSoft,
        ),
      ),
    );
  }
}

/// 朱砂印：整页唯一的红色，出现一次。
class _SealStamp extends StatelessWidget {
  const _SealStamp({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: progress,
      builder: (context, child) {
        final t = const Interval(0.56, 0.82, curve: V2Curve.settle)
            .transform(progress.value.clamp(0.0, 1.0));
        return Opacity(
          opacity: t,
          child: Transform.rotate(
            angle: -0.06,
            child: Transform.scale(scale: 0.86 + 0.14 * t, child: child),
          ),
        );
      },
      child: Container(
        width: 46,
        height: 46,
        decoration: BoxDecoration(
          border: Border.all(color: V2Color.seal, width: 1.6),
          borderRadius: BorderRadius.circular(4),
        ),
        child: const Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '食',
                style: TextStyle(
                  fontSize: 15,
                  height: 1.05,
                  color: V2Color.seal,
                ),
              ),
              Text(
                '时',
                style: TextStyle(
                  fontSize: 15,
                  height: 1.05,
                  color: V2Color.seal,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    return _FadeUp(
      progress: progress,
      window: const Interval(0.50, 0.86, curve: V2Curve.settle),
      child: Row(
        children: [
          const Text(
            '今日宜',
            style: TextStyle(
              fontSize: V2Type.cap,
              letterSpacing: V2Type.trackingCap,
              color: V2Color.inkSoft,
            ),
          ),
          const SizedBox(width: V2Space.sm),
          Expanded(child: Container(height: 1, color: V2Color.line)),
        ],
      ),
    );
  }
}

class _DishCard extends StatelessWidget {
  const _DishCard({
    required this.data,
    required this.progress,
    required this.index,
  });

  final _Dish data;
  final Animation<double> progress;
  final int index;

  @override
  Widget build(BuildContext context) {
    final start = 0.52 + index * 0.09;
    final window = Interval(start, (start + 0.34).clamp(0.0, 1.0),
        curve: V2Curve.settle);

    return _FadeUp(
      progress: progress,
      window: window,
      offset: 14,
      child: Container(
        padding: const EdgeInsets.all(V2Space.md),
        decoration: BoxDecoration(
          color: V2Color.card,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: V2Color.line.withValues(alpha: 0.7)),
          boxShadow: const [
            BoxShadow(
              color: Color(0x0F2F4B36),
              blurRadius: 18,
              offset: Offset(0, 6),
            ),
          ],
        ),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: SizedBox(
                width: 68,
                height: 68,
                child: Image.asset(
                  data.image,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => Container(
                    color: V2Color.paperDeep,
                  ),
                ),
              ),
            ),
            const SizedBox(width: V2Space.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    data.name,
                    style: const TextStyle(
                      fontSize: V2Type.h2,
                      height: 1.3,
                      letterSpacing: 0.6,
                      color: V2Color.ink,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    data.reason,
                    style: const TextStyle(
                      fontSize: 13,
                      height: 1.5,
                      color: V2Color.inkSoft,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      _Pill(text: data.minutes),
                      const SizedBox(width: V2Space.xs),
                      _Pill(text: data.tag),
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

class _Pill extends StatelessWidget {
  const _Pill({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: V2Color.moss.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 11,
          letterSpacing: 0.6,
          color: V2Color.moss,
        ),
      ),
    );
  }
}

class _Footnote extends StatelessWidget {
  const _Footnote({required this.progress});

  final Animation<double> progress;

  @override
  Widget build(BuildContext context) {
    return _FadeUp(
      progress: progress,
      window: const Interval(0.80, 1.0, curve: V2Curve.settle),
      child: const Padding(
        padding: EdgeInsets.only(top: V2Space.sm),
        child: Text(
          '以上三道按「立冬 · 温补」从 700 道菜里筛出，'
          '每道都标了它为什么今天合适。',
          style: TextStyle(
            fontSize: 12,
            height: 1.7,
            color: V2Color.inkSoft,
          ),
        ),
      ),
    );
  }
}

/// 统一的「淡入 + 上浮」，所有入场都走它，避免各处手写 interval。
class _FadeUp extends StatelessWidget {
  const _FadeUp({
    required this.progress,
    required this.window,
    required this.child,
    this.offset = 10,
  });

  final Animation<double> progress;
  final Interval window;
  final Widget child;
  final double offset;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: progress,
      builder: (context, child) {
        final t = window.transform(progress.value.clamp(0.0, 1.0));
        return Opacity(
          opacity: t,
          child: Transform.translate(
            offset: Offset(0, offset * (1 - t)),
            child: child,
          ),
        );
      },
      child: child,
    );
  }
}

// ---------- 5. 晨雾背景 ----------

/// 两层大半径径向渐变，各自以极慢的不同方向漂移。
/// 只用两个径向渐变，帧成本可以忽略；不用视频、不用 shader。
class _MorningFogPainter extends CustomPainter {
  _MorningFogPainter({required this.t, required this.seed});

  final double t;
  final int seed;

  @override
  void paint(Canvas canvas, Size size) {
    final a = t * 2 * math.pi;
    _blob(
      canvas,
      size,
      center: Offset(
        size.width * (0.14 + 0.10 * math.sin(a)),
        size.height * (0.58 + 0.07 * math.cos(a * 0.8)),
      ),
      radius: size.width * 0.92,
      color: const Color(0xFF7E9B7A).withValues(alpha: 0.17),
    );
    _blob(
      canvas,
      size,
      center: Offset(
        size.width * (0.86 + 0.07 * math.cos(a * 0.6 + 1.0)),
        size.height * (0.70 + 0.06 * math.sin(a * 0.9 + 0.5)),
      ),
      radius: size.width * 0.78,
      color: const Color(0xFFD8C79A).withValues(alpha: 0.20),
    );
  }

  void _blob(
    Canvas canvas,
    Size size, {
    required Offset center,
    required double radius,
    required Color color,
  }) {
    final paint = Paint()
      ..shader = RadialGradient(
        colors: [color, color.withValues(alpha: 0)],
        stops: const [0.0, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: radius));
    canvas.drawCircle(center, radius, paint);
  }

  @override
  bool shouldRepaint(covariant _MorningFogPainter old) => old.t != t;
}

// ---------- 6. 内容（真实菜名，取自仓库 assets）----------

class _Dish {
  const _Dish(this.name, this.reason, this.minutes, this.tag, this.image);

  final String name;
  final String reason;
  final String minutes;
  final String tag;
  final String image;
}

const _dishes = <_Dish>[
  _Dish(
    '番茄土豆炖牛腩',
    '炖菜最长的等待换来最稳的温度，适合入冬第一周。',
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
