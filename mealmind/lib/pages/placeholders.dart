import 'package:flutter/material.dart';

import '../theme.dart';

/// =====================================================================
/// 占位页 —— 还没实现的页面先放这里
///
/// 已完成（各自独立文件）：
///   首页   pages/home.dart
///   菜单 + 购物清单   pages/menu.dart
///   菜谱 + 详情   pages/recipes.dart
///   AI 助手 + 多智能体协作轨迹   pages/ai.dart
///
/// 剩下这两个下一阶段实现：
///   食材   → 分类筛选 + 我的食材 + "用这些食材做菜"
///   我的   → 家庭设置（人数/预算/慢病/忌口）→ 驱动求解器
/// =====================================================================

class _Placeholder extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final List<String> plan;

  const _Placeholder({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.plan,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 24, 16, 24),
          children: [
            Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: green100,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Icon(icon, color: green700, size: 22),
                ),
                const SizedBox(width: 12),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        fontSize: 20,
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
            ),
            const SizedBox(height: 22),
            Container(
              padding: const EdgeInsets.all(18),
              decoration: cardDeco(radius: rBlock),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '这一页会包含：',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: ink,
                    ),
                  ),
                  const SizedBox(height: 12),
                  for (final item in plan)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Padding(
                            padding: EdgeInsets.only(top: 6),
                            child: Icon(Icons.circle,
                                size: 5, color: green600),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              item,
                              style: const TextStyle(
                                fontSize: 13,
                                color: muted,
                                height: 1.6,
                              ),
                            ),
                          ),
                        ],
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

// ---------------------------------------------------------------------

class FoodsPage extends StatelessWidget {
  const FoodsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _Placeholder(
      icon: Icons.local_florist,
      title: '食材',
      subtitle: '时令食材 · 我家有什么',
      plan: [
        '分类筛选（全部 / 蔬菜 / 肉蛋 / 水产 / 豆制品）',
        '时令食材列表',
        '食材详情',
        '「我的现有食材」管理',
        '用现有食材做菜',
      ],
    );
  }
}

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _Placeholder(
      icon: Icons.person,
      title: '我的',
      subtitle: '顺应时令，认真吃饭',
      plan: [
        '★ 家庭设置：人数 / 预算 / 慢病 / 忌口 / 厨具 / 时间',
        '   （← 这一页的设置会驱动求解器，是"吃什么"的关键输入）',
        '收藏与浏览历史',
        '我的食材',
        '用餐与时令提醒',
      ],
    );
  }
}
