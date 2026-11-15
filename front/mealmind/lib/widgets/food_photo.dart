import 'package:flutter/material.dart';

import 'lazy_photo.dart';

class FoodPhoto extends StatelessWidget {
  final String asset;
  final String name;
  const FoodPhoto({super.key, required this.asset, this.name = ''});
  @override
  Widget build(BuildContext context) =>
      LazyPhoto(kind: 'food', name: name, fallback: asset);
}
