import 'package:flutter/material.dart';

/// A bounded, edge-to-edge photo shared by home, inventory and food details.
class FoodPhoto extends StatelessWidget {
  final String asset;
  const FoodPhoto({super.key, required this.asset});

  /// 说明：食材高清宽图原本【从未提交】（清理大文件那次 force push 之后就不在
  ///    仓库里了），于是 backend_api.dart 里每条命中规则都返回不存在的资源：
  ///      Unable to load asset: "..." （测试里直接判失败，真机上整片空白）
  ///    现在这批图已经补回来了：48 张 `ingredient-*-wide.jpg`，由
  ///      team/front/scripts/map-wide-images.ps1
  ///    从 ingredient_image_library 的 590 张原图按中文名对上、cover 裁切成
  ///    480x300 的 jpg（共约 1.3 MB）。映射写在 backend_api.dart 的
  ///    _foodImageForName 里，所以这里不再需要 .jpg → 宽图 的替换表。
  static const _replacements = <String, String>{};

  @override
  Widget build(BuildContext context) => ClipRect(
    child: SizedBox.expand(
      child: Image.asset(
        _replacements[asset] ?? asset,
        width: double.infinity,
        height: double.infinity,
        fit: BoxFit.cover,
        alignment: Alignment.center,
        filterQuality: FilterQuality.high,
      ),
    ),
  );
}
