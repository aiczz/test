import 'package:flutter/material.dart';

/// A bounded, edge-to-edge photo shared by home, inventory and food details.
class FoodPhoto extends StatelessWidget {
  final String asset;
  const FoodPhoto({super.key, required this.asset});

  /// ⚠️ 这里原本有一张 `.jpg → -wide.png` 的替换表，指向一套【从未提交】的
  ///    高清宽图（清理大文件那次 force push 之后就不在仓库里了，旧历史里
  ///    用的也是 `.jpg`）。结果是每张食材图都加载失败：
  ///      Unable to load asset: "assets/images/ingredient-pork-wide.png"
  ///    测试里这会被当成异常直接判失败，真机上则是整片空白。
  ///    现在只用仓库里真实存在的文件；等那套宽图补回来，再把映射加回来。
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
