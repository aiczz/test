// 仅用于自查：直接挂载决赛版首页，不经过登录和后端。
// 部署前用它验证真实组件（DishPhoto / CityStore / ContentStore）能跑起来。
// 不参与正式构建。

import 'package:flutter/material.dart';

import '../models/content.dart';
import '../pages/home_editorial.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      home: HomeEditorial(
        onOpenFoods: () {},
        onOpenRecipes: () {},
        onOpenAi: () {},
        onOpenProfile: () {},
        onOpenFoodDetail: (Food food) {},
      ),
    ),
  );
}
