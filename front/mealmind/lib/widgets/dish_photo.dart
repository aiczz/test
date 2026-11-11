import 'package:flutter/material.dart';

import '../data/dish_images.dart';
import '../services/api_config.dart';
import '../theme.dart';

/// 菜品配图。
///
/// 【图片优先级】
///   1. 后端返回的 `imageUrl`（网络图 https://... 或相对路径 /static/...）
///   2. 本地 `kDishImageByName[name]` 兜底（481 道有 asset 图片的菜）
///   3. 都没 → 占位图 + 「暂无配图」
///
/// 【URL 类型】
///   - https://image.pollinations.ai/...      → Image.network 直接加载远程
///   - /static/images/{dish_id}.jpg          → 拼 apiBase 后 Image.network（本地静态文件）
///   - assets/images/dishes/{name}.jpg       → Image.asset 本地 asset
class DishPhoto extends StatelessWidget {
  /// 后端返回的图片 URL 或 asset 路径。空字符串 = 后端没给。
  final String? imageUrl;

  /// 菜名 —— 用于本地 asset 兜底（kDishImageByName）。
  final String name;

  final BoxFit fit;

  const DishPhoto({
    super.key,
    this.imageUrl,
    required this.name,
    this.fit = BoxFit.cover,
  });

  /// 把后端返回的 imageUrl 解析成 Flutter 能直接用的形式。
  /// 相对路径拼上 apiBase 变成完整 URL。
  String? _resolveUrl(String? raw) {
    if (raw == null) return null;
    final s = raw.trim();
    if (s.isEmpty) return null;
    if (s.startsWith('http://') || s.startsWith('https://')) return s;
    if (s.startsWith('/')) {
      // 相对路径 → 拼 apiBase（去掉末尾斜杠）
      final base = BackendStatus.instance.apiBase;
      return '${base.endsWith('/') ? base.substring(0, base.length - 1) : base}$s';
    }
    return s;  // asset 路径原样返回
  }

  @override
  Widget build(BuildContext context) {
    // ---- 1. 后端给了 imageUrl ----
    final url = _resolveUrl(imageUrl);
    if (url != null) {
      if (url.startsWith('http://') || url.startsWith('https://')) {
        return Image.network(
          url,
          width: double.infinity,
          height: double.infinity,
          fit: fit,
          alignment: Alignment.center,
          filterQuality: FilterQuality.high,
          // 网络图加载失败也走占位图
          errorBuilder: (_, _, _) => const _DishPhotoPlaceholder(),
          loadingBuilder: (context, child, progress) {
            if (progress == null) return child;
            return const _DishPhotoLoading();
          },
        );
      }
      // asset 路径（assets/images/xxx.jpg）
      return Image.asset(
        url,
        width: double.infinity,
        height: double.infinity,
        fit: fit,
        alignment: Alignment.center,
        filterQuality: FilterQuality.high,
        errorBuilder: (_, _, _) => const _DishPhotoPlaceholder(),
      );
    }

    // ---- 2. 本地 asset 兜底 ----
    final localAsset = kDishImageByName[name];
    if (localAsset != null && localAsset.isNotEmpty) {
      return Image.asset(
        localAsset,
        width: double.infinity,
        height: double.infinity,
        fit: fit,
        alignment: Alignment.center,
        filterQuality: FilterQuality.high,
        errorBuilder: (_, _, _) => const _DishPhotoPlaceholder(),
      );
    }

    // ---- 3. 占位 ----
    return const _DishPhotoPlaceholder();
  }
}

/// 网络图加载中 —— 用同样的背景渐变，叠个小 spinner。
class _DishPhotoLoading extends StatelessWidget {
  const _DishPhotoLoading();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFF3F9EF), Color(0xFFE5EEDF)],
        ),
      ),
      child: Center(
        child: SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            valueColor: AlwaysStoppedAnimation<Color>(muted.withValues(alpha: 0.6)),
          ),
        ),
      ),
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
          colors: [Color(0xFFF3F9EF), Color(0xFFE5EEDF)],
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
