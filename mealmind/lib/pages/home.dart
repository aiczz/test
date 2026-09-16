import 'package:flutter/material.dart';

import '../data/mock.dart';
import '../models/content.dart';
import '../theme.dart';
import 'menu.dart';

/// 首页 —— 对应队友原型 `homePage()`
///
/// 结构：顶部品牌栏 → Hero 推荐 → 今日推荐食材 → 家常易做推荐 → AI 建议 → 快捷操作
class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
          children: [
            const _TopBar(),
            const SizedBox(height: 14),
            const _Hero(),
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
            for (final r in mockRecipes.take(3)) ...[
              _RecipeCard(recipe: r),
              const SizedBox(height: 12),
            ],
            const SizedBox(height: 14),
            const _AiTipBar(),
            const SizedBox(height: 20),
            const _QuickActions(),
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
        const Text(
          '食时',
          style: TextStyle(
            fontSize: 26,
            fontWeight: FontWeight.w900,
            color: green900,
            letterSpacing: -1,
          ),
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
  const _Hero();

  @override
  Widget build(BuildContext context) {
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: const Color(0xFFF8EEDC), // 米色底，对应原型 .hero
        borderRadius: BorderRadius.circular(rHero),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 图片
          SizedBox(
            height: 176,
            child: Image.asset(
              'assets/images/hero-soup.jpg',
              fit: BoxFit.cover,
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  heroEyebrow,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: green700,
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  heroTitle,
                  style: TextStyle(
                    fontSize: 34,
                    fontWeight: FontWeight.w900,
                    color: green900,
                    height: 1.05,
                    letterSpacing: -1.2,
                  ),
                ),
                const SizedBox(height: 10),
                const Text(
                  heroBody,
                  style: TextStyle(fontSize: 14, color: muted, height: 1.6),
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: () => _toast(context, '打开菜谱详情（下一步实现）'),
                  style: FilledButton.styleFrom(
                    backgroundColor: orange,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 22, vertical: 13),
                    shape: const StadiumBorder(),
                  ),
                  child: const Text(
                    '查看推荐菜谱 →',
                    style: TextStyle(fontWeight: FontWeight.w700),
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
            aspectRatio: 1.25,
            child: Image.asset(food.image, fit: BoxFit.cover),
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
// 菜谱卡片（横向：左图右文）
// =====================================================================

class _RecipeCard extends StatelessWidget {
  final Recipe recipe;

  const _RecipeCard({required this.recipe});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(rCard),
      onTap: () => _toast(context, '打开「${recipe.name}」详情（下一步实现）'),
      child: Container(
        // 固定高度，保证图片和右侧文字对齐；内容比这个矮，不会溢出
        height: 132,
        clipBehavior: Clip.antiAlias,
        decoration: cardDeco(),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              width: 112,
              child: Image.asset(recipe.image, fit: BoxFit.cover),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      recipe.name,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w800,
                        color: ink,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      recipe.desc,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12, color: muted),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 5,
                      runSpacing: 5,
                      children: [
                        for (var i = 0; i < recipe.tags.length && i < 2; i++)
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 7, vertical: 3),
                            decoration: tagDeco(
                              bg: i == 0 ? orange100 : green100,
                            ),
                            child: Text(
                              recipe.tags[i],
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                                color: i == 0 ? orange : green700,
                              ),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        const Icon(Icons.schedule, size: 12, color: muted),
                        const SizedBox(width: 3),
                        Text(
                          recipe.time,
                          style:
                              const TextStyle(fontSize: 11, color: muted),
                        ),
                        const SizedBox(width: 10),
                        const Icon(Icons.people_outline,
                            size: 12, color: muted),
                        const SizedBox(width: 3),
                        Text(
                          recipe.people,
                          style:
                              const TextStyle(fontSize: 11, color: muted),
                        ),
                      ],
                    ),
                  ],
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
  const _QuickActions();

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
            onPressed: () => _toast(context, '去选食材（下一步实现）'),
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

// =====================================================================
// 临时提示（SnackBar）—— 等各页面实现后会被真正的跳转替换
// =====================================================================

void _toast(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(message),
      duration: const Duration(milliseconds: 1400),
      behavior: SnackBarBehavior.floating,
      backgroundColor: const Color(0xFF163A26),
      shape: const StadiumBorder(),
    ),
  );
}
