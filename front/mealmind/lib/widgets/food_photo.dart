import 'package:flutter/material.dart';

/// A bounded, edge-to-edge photo shared by home, inventory and food details.
class FoodPhoto extends StatelessWidget {
  final String asset;
  const FoodPhoto({super.key, required this.asset});

  /// 说明：食材配图曾经指向一套【从未提交】的 `-wide.png`，于是 backend_api.dart
  ///    里每条命中规则都返回不存在的资源（测试直接判失败，真机上整片空白）。
  ///    现在改成查表：lib/data/ingredient_images.dart 由
  ///      team/front/scripts/generate-images.ps1  +  make-dart-image-map.ps1
  ///    从图库 590 张原图生成（cover 裁切 480x300 jpg），菜谱另有 500 张。
  ///    映射在 backend_api.dart 的 _foodImageForName 里，所以这里不需要替换表。
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
