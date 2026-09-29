import 'package:flutter/material.dart';

/// A bounded, edge-to-edge photo shared by home, inventory and food details.
class FoodPhoto extends StatelessWidget {
  final String asset;
  const FoodPhoto({super.key, required this.asset});

  static const _replacements = <String, String>{
    'assets/images/ingredient_pork.jpg':
        'assets/images/ingredient-pork-wide.png',
    'assets/images/ingredient_onion.jpg':
        'assets/images/ingredient-onion-wide.png',
    'assets/images/ingredient_carrot.jpg':
        'assets/images/ingredient-carrot-wide.png',
    'assets/images/ingredient_chicken.jpg':
        'assets/images/ingredient-chicken-wide.png',
    'assets/images/ingredient-coriander-wide.png':
        'assets/images/ingredient-coriander-wide.png',
    'assets/images/ingredient-red-date-wide.png':
        'assets/images/ingredient-red-date-wide.png',
    'assets/images/ingredient-celery-wide.png':
        'assets/images/ingredient-celery-wide.png',
    'assets/images/ingredient-sweet-potato-wide.png':
        'assets/images/ingredient-sweet-potato-wide.png',
  };

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
