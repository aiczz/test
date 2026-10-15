import 'package:flutter/material.dart';

import '../theme.dart';
import 'brand_wordmark.dart';

/// Original login transition icon and calligraphy.
class BrandSplash extends StatelessWidget {
  const BrandSplash({super.key});

  @override
  Widget build(BuildContext context) => Center(
    child: SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 132,
            height: 132,
            child: FittedBox(
              fit: BoxFit.contain,
              child: SizedBox(
                width: 240,
                height: 240,
                child: ClipRect(
                  child: Stack(
                    children: [
                      Positioned(
                        left: -350,
                        top: -470,
                        width: 941,
                        height: 1672,
                        child: Image.asset(
                          'assets/images/splash.png',
                          fit: BoxFit.fill,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 20),
          const BrandWordmark(width: 260),
          const SizedBox(height: 28),
          const SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(strokeWidth: 2, color: brand700),
          ),
        ],
      ),
    ),
  );
}
