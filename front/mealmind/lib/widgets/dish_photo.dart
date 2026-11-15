import 'package:flutter/material.dart';

import '../data/dish_images.dart';
import 'lazy_photo.dart';

class DishPhoto extends StatelessWidget {
  final String? imageUrl;
  final String name;
  final BoxFit fit;
  const DishPhoto({
    super.key,
    this.imageUrl,
    required this.name,
    this.fit = BoxFit.cover,
  });
  @override
  Widget build(BuildContext context) => LazyPhoto(
    kind: 'recipe',
    name: name,
    fallback: imageUrl?.isNotEmpty == true ? imageUrl : kDishImageByName[name],
    fit: fit,
  );
}
