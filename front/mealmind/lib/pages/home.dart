import 'package:flutter/material.dart';

import '../data/mock.dart';
import '../models/content.dart';
import '../theme.dart';
import 'menu.dart';

/// 首页 —— 对应队友原型 `homePage()`
///
/// 结构：顶部品牌栏 → Hero 推荐 → 今日推荐食材 → 家常易做推荐 → AI 建议 → 快捷操作
class HomePage extends StatelessWidget {
  final VoidCallback onOpenFoods;
  final VoidCallback onOpenRecipes;

  const HomePage({
    super.key,
    required this.onOpenFoods,
    required this.onOpenRecipes,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 28),
          children: [
            const _TopBar(),
            const SizedBox(height: 14),
            _Hero(onOpenRecipes: onOpenRecipes),
            const SizedBox(height: 26),
            const _SectionHeader(
              icon: Icons.eco,
              title: '今日推荐食材',
              subtitle: '应季鲜美 · 营养加分',
            ),
            const SizedBox(height: 12),
            _FoodRow(foods: mockFoods.take(3).toList()),
            const SizedBox(height: 26),
            const _SectionHeader(
              icon: Icons.local_dining,
              title: '家常易做推荐',
              subtitle: '应季食材 · 简单好做',
            ),
            const SizedBox(height: 12),
            _RecipeRow(
              recipes: mockRecipes.take(3).toList(),
              onOpenRecipes: onOpenRecipes,
            ),
            const SizedBox(height: 14),
            const _AiTipBar(),
            const SizedBox(height: 20),
            _QuickActions(onOpenFoods: onOpenFoods),
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
        _Pill(icon: Icons.location_on, text: currentCity),
        const SizedBox(width: 8),
        _Pill(icon: Icons.eco, text: currentSeason),
      ],
    );
  }
}

class _Pill extends StatelessWidget {
  final IconData icon;
  final String text;

  const _Pill({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
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
          Text(
            text,
            style: const TextStyle(fontSize: 12, color: ink),
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// Hero 推荐区
// =====================================================================

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
                    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 11),
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
            Text(
              subtitle,
              style: const TextStyle(fontSize: 12, color: muted),
            ),
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

  const _FoodRow({required this.foods});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < foods.length; i++) ...[
          if (i > 0) const SizedBox(width: 10),
          Expanded(child: _FoodCard(food: foods[i])),
        ],
      ],
    );
  }
}

class _FoodCard extends StatelessWidget {
  final Food food;

  const _FoodCard({required this.food});

  @override
  Widget build(BuildContext context) {
    return Container(
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
                    padding:
                        const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
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

  const _RecipeCard({
    required this.recipe,
    required this.onOpenRecipes,
  });

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
  const _AiTipBar();

  @override
  Widget build(BuildContext context) {
    return Container(
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
            child: const Icon(Icons.auto_awesome, color: Colors.white, size: 20),
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
                      fontSize: 13, color: muted, height: 1.6),
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
