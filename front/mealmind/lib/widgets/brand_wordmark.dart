import 'package:flutter/material.dart';

/// Original calligraphy and tagline from the login transition artwork.
class BrandWordmark extends StatelessWidget {
  final double width;
  final Color? backgroundColor;

  const BrandWordmark({super.key, this.width = 140, this.backgroundColor});

  @override
  Widget build(BuildContext context) => Semantics(
    label: '食时，顺应时令，智慧饮食',
    image: true,
    child: SizedBox(
      width: width,
      child: AspectRatio(
        aspectRatio: 445 / 290,
        child: FittedBox(
          fit: BoxFit.contain,
          child: SizedBox(
            width: 445,
            height: 290,
            child: ClipRect(
              child: Stack(
                children: [
                  Positioned(
                    left: -250,
                    top: -735,
                    width: 941,
                    height: 1672,
                    child: Image.asset(
                      'assets/images/splash.png',
                      fit: BoxFit.fill,
                      color: backgroundColor,
                      colorBlendMode: backgroundColor == null
                          ? null
                          : BlendMode.darken,
                      excludeFromSemantics: true,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
