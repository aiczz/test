import 'package:flutter/material.dart';

import '../data/mock.dart';
import '../models/content.dart';
import '../services/city.dart';
import '../services/content_store.dart';
import '../services/recommender.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/city_picker.dart';
import 'menu.dart';

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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        // 监听家庭档案：改完约束切回来，这里会自动重算
        child: ListenableBuilder(
          listenable: AppState.instance,
          builder: (context, _) {
            final picks = pickForHome(
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
                _ConstraintBar(picks: picks, onOpenProfile: onOpenProfile),
                const SizedBox(height: 24),
                const _SectionHeader(
                  icon: Icons.eco,
                  title: '今日推荐食材',
                  subtitle: '应季鲜美 · 营养加分',
                ),
                const SizedBox(height: 12),
                _FoodRow(
                  foods: picks.foods,
                  onOpenDetail: onOpenFoodDetail,
                ),
                const SizedBox(height: 26),
                _SectionHeader(
                  icon: Icons.local_dining,
                  title: '按你的条件能做',
                  subtitle: picks.subtitle,
                ),
                const SizedBox(height: 12),
                _RecipeRow(
                  recipes: picks.recipes,
                  onOpenRecipes: onOpenRecipes,
                ),
                const SizedBox(height: 14),
                _AiTipBar(onTap: onOpenAi),
                const SizedBox(height: 20),
                _QuickActions(onOpenFoods: onOpenFoods),
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

  const _ConstraintBar({required this.picks, required this.onOpenProfile});

  @override
  Widget build(BuildContext context) {
    final p = AppState.instance.profile;

    return InkWell(
      borderRadius: BorderRadius.circular(rCard),
      onTap: onOpenProfile,
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
        decoration: cardDeco(),
        child: Row(
          children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                color: green100,
                borderRadius: BorderRadius.circular(11),
              ),
              child: const Icon(Icons.tune, size: 18, color: green700),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${p.people} 人 · 预算 ¥${p.budget.toStringAsFixed(0)} · '
                    '${p.cookMinutes.round()} 分钟',
                    style: const TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w800,
                      color: ink,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    picks.droppedNames.isEmpty
                        ? '下方推荐已按这些条件筛选'
                        : '「${picks.droppedNames.first}」等 ${picks.dropped} 道'
                              '超出条件，已从下方推荐排除',
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
                color: green700,
                fontWeight: FontWeight.w700,
              ),
            ),
            const Icon(Icons.chevron_right, size: 16, color: green700),
          ],
        ),
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
                color: green900,
                letterSpacing: -1.5,
                height: 1,
              ),
            ),
            SizedBox(height: 5),
            Text(
              '顺应时令 · 智慧饮食',
              style: TextStyle(
                fontSize: 10,
                color: green700,
                fontWeight: FontWeight.w600,
                letterSpacing: 1.2,
              ),
            ),
          ],
        ),
        const Spacer(),
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
          Icon(icon, size: 13, color: green700),
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

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
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
        backgroundColors: const [Color(0xFFE5F3DF), Color(0xFFFFE7C5)],
      ),
    ];

    return Column(
      children: [
        SizedBox(
          height: 252,
          child: PageView(
            controller: _controller,
            onPageChanged: (page) => setState(() => _currentPage = page),
            children: pages,
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
                  color: active ? orange : const Color(0xFFD4DDD0),
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
                    color: green700,
                    letterSpacing: 0.6,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  heroTitle,
                  style: TextStyle(
                    fontSize: 33,
                    fontWeight: FontWeight.w900,
                    color: green900,
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
                color: green700.withValues(alpha: 0.10),
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
                    Icon(buttonIcon, size: 16, color: green700),
                    const SizedBox(width: 6),
                    Text(
                      eyebrow,
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
                        color: green700,
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
                    color: green900,
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
            color: green100,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(icon, size: 19, color: green700),
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
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < foods.length; i++) ...[
          if (i > 0) const SizedBox(width: 10),
          Expanded(
            child: _FoodCard(
              food: foods[i],
              onTap: () => onOpenDetail(foods[i]),
            ),
          ),
        ],
      ],
    );
  }
}

class _FoodCard extends StatelessWidget {
  final Food food;
  final VoidCallback onTap;

  const _FoodCard({required this.food, required this.onTap});

  @override
  Widget build(BuildContext context) {
    // 这张卡片以前点了没反应 —— 现在点开食材详情
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(rCard),
      child: Container(
        clipBehavior: Clip.antiAlias,
        decoration: cardDeco(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(
              aspectRatio: 1.8,
              child: ColoredBox(
                color: const Color(0xFFFFF8EC),
                child: Image.asset(
                  food.image,
                  fit: BoxFit.contain,
                  alignment: Alignment.center,
                  filterQuality: FilterQuality.high,
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    food.name,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: ink,
                    ),
                  ),
                  const SizedBox(height: 6),
                  if (food.tags.isNotEmpty)
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 7,
                        vertical: 4,
                      ),
                      decoration: tagDeco(),
                      child: Text(
                        food.tags.first,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 10,
                          color: green700,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
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
    return InkWell(
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
              child: Image.asset(
                recipe.image,
                fit: BoxFit.cover,
                alignment: Alignment.center,
                filterQuality: FilterQuality.high,
              ),
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
  final VoidCallback onTap;

  const _AiTipBar({required this.onTap});

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
            colors: [Color(0xFFE6F4DF), Color(0xFFFBF7E9)],
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
                color: green700,
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
                    mockAiTip.title,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                      color: ink,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    mockAiTip.body,
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
            const Icon(Icons.chevron_right, size: 18, color: green700),
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
  final VoidCallback onOpenFoods;

  const _QuickActions({required this.onOpenFoods});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton(
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute<void>(builder: (_) => const MenuPage()),
            ),
            style: OutlinedButton.styleFrom(
              side: const BorderSide(color: Color(0xFFCFE3C8)),
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: const StadiumBorder(),
            ),
            child: const Text(
              '查看今日菜单',
              style: TextStyle(
                color: green700,
                fontWeight: FontWeight.w700,
                fontSize: 14,
              ),
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
