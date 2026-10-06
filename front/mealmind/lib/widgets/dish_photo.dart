import 'package:flutter/material.dart';

import '../theme.dart';

/// 菜品配图。
///
/// 【为什么需要它】
/// 清洗库有 10000 道菜，但配图图库只覆盖其中约 500 道（按菜名精确命中）。
/// 剩下 9500 道**没有图**。
///
/// 以前的做法是：没命中就从三张通用图里按菜名 hash 挑一张 —— 于是
/// 「红烧肉」可能配上一张番茄炒蛋的照片。这不是「凑合」，这是**错误信息**：
/// 用户会以为那就是这道菜的样子。所以现在改成：
///   · 有真实配图 → 显示配图
///   · 没有       → 显示一个明确的占位图，并写「暂无配图」
/// 宁可承认没有图，也不拿别的菜的图冒充。
class DishPhoto extends StatelessWidget {
  /// 资源路径。空字符串 = 这道菜没有配图。
  final String asset;

  final BoxFit fit;

  const DishPhoto({super.key, required this.asset, this.fit = BoxFit.cover});

  @override
  Widget build(BuildContext context) {
    if (asset.isEmpty) return const _DishPhotoPlaceholder();

    return Image.asset(
      asset,
      width: double.infinity,
      height: double.infinity,
      fit: fit,
      alignment: Alignment.center,
      filterQuality: FilterQuality.high,
      // 资源缺失（比如图库换了文件名）也走占位图，而不是抛异常/留白
      errorBuilder: (_, _, _) => const _DishPhotoPlaceholder(),
    );
  }
}

/// 没有配图时的占位：一眼能看出「这里本来应该有张图，但没有」。
class _DishPhotoPlaceholder extends StatelessWidget {
  const _DishPhotoPlaceholder();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFF7F2EA), Color(0xFFEFE7DB)],
        ),
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.ramen_dining_outlined,
              size: 26,
              color: muted.withValues(alpha: 0.7),
            ),
            const SizedBox(height: 4),
            Text(
              '暂无配图',
              style: TextStyle(
                fontSize: 10,
                color: muted.withValues(alpha: 0.9),
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
