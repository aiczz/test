#!/usr/bin/env python3
"""生成「食时」品牌应用图标。

为什么留这个脚本：图标是生成物，不是手绘资产。把生成逻辑放进仓库，
以后改配色/改造型只要重跑一次，不用去找设计师要图。

依赖：Pillow   ->   pip install Pillow

用法（在仓库根目录执行）：
    python scripts/make_icons.py

会覆盖：
    mealmind/web/icons/Icon-192.png
    mealmind/web/icons/Icon-512.png
    mealmind/web/icons/Icon-maskable-192.png
    mealmind/web/icons/Icon-maskable-512.png
    mealmind/web/favicon.png
    mealmind/android/app/src/main/res/mipmap-*/ic_launcher.png

设计：品牌绿渐变圆角底 + 米白饭碗 + 斜插筷子。
造型全部用几何图元拼，保证在 48×48 这种小尺寸下依然认得出是「吃饭」。
"""

import os
import sys

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("缺少 Pillow，请先执行: pip install Pillow")

# ---- 品牌色（与 mealmind/lib/theme.dart 保持一致）----
GREEN_700 = (0x17, 0x73, 0x3D)
GREEN_900 = (0x0B, 0x53, 0x2F)
CREAM = (0xFF, 0xFD, 0xF8)

# 超采样倍数：先画大图再缩，边缘才不会有锯齿
SS = 4

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_ICONS = os.path.join(ROOT, "mealmind", "web", "icons")
WEB_FAVICON = os.path.join(ROOT, "mealmind", "web", "favicon.png")
ANDROID_RES = os.path.join(ROOT, "mealmind", "android", "app", "src",
                           "main", "res")


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _rounded_line(draw, p1, p2, width, fill):
    """画一条两端带圆头的粗线（Pillow 的 line 没有 line-cap）。"""
    draw.line([p1, p2], fill=fill, width=width)
    r = width / 2.0
    for (x, y) in (p1, p2):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def render_master(px, maskable):
    """渲染一张 px×px 的主图。

    maskable=True 时：底色铺满整张画布（不做圆角），主体缩到中心 68%，
    以适配 Android / PWA 的圆形、方形等各种裁切形状。
    """
    S = px
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # ---- 1. 背景：竖向渐变，用圆角矩形做遮罩 ----
    grad = Image.new("RGB", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=_lerp(GREEN_700, GREEN_900, y / (S - 1)))
    bg_mask = Image.new("L", (S, S), 0)
    radius = 0 if maskable else int(S * 0.22)
    ImageDraw.Draw(bg_mask).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), bg_mask)

    d = ImageDraw.Draw(img)
    k = 0.68 if maskable else 1.0

    def X(fx):
        return (0.5 + (fx - 0.5) * k) * S

    def Y(fy):
        return (0.5 + (fy - 0.5) * k) * S

    def BOX(x0, y0, x1, y1):
        return [X(x0), Y(y0), X(x1), Y(y1)]

    stick_w = max(1, int(0.040 * k * S))
    rim_h = max(1, int(0.062 * k * S))

    # ---- 2. 筷子：先画，下半截会被碗和碗口盖住 ----
    # 整体略微左移，让「筷子 + 碗」的视觉重心落在中轴线上
    _rounded_line(d, (X(0.428), Y(0.650)), (X(0.518), Y(0.242)),
                  stick_w, CREAM)
    _rounded_line(d, (X(0.500), Y(0.650)), (X(0.590), Y(0.242)),
                  stick_w, CREAM)

    # ---- 3. 碗身：下半圆，中心 (0.5, 0.560)，半径 0.25 ----
    d.pieslice(BOX(0.250, 0.310, 0.750, 0.810), 0, 180, fill=CREAM)

    # ---- 4. 碗口：只比碗身宽 0.015，读作碗沿而不是「耳朵」 ----
    d.rounded_rectangle([X(0.235), Y(0.529), X(0.765), Y(0.529) + rim_h],
                        radius=rim_h / 2, fill=CREAM)

    return img


def save(img, px, path):
    out = img.resize((px, px), Image.LANCZOS)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.save(path)
    print("  {0:>4}x{1:<4} {2}".format(px, px,
                                       os.path.relpath(path, ROOT)))


def main():
    normal = render_master(512 * SS, maskable=False)
    maskable = render_master(512 * SS, maskable=True)

    print("网页 / PWA 图标：")
    save(normal, 512, os.path.join(WEB_ICONS, "Icon-512.png"))
    save(normal, 192, os.path.join(WEB_ICONS, "Icon-192.png"))
    save(maskable, 512, os.path.join(WEB_ICONS, "Icon-maskable-512.png"))
    save(maskable, 192, os.path.join(WEB_ICONS, "Icon-maskable-192.png"))
    save(normal, 32, WEB_FAVICON)

    print("Android 启动图标：")
    for folder, px in (("mipmap-mdpi", 48), ("mipmap-hdpi", 72),
                       ("mipmap-xhdpi", 96), ("mipmap-xxhdpi", 144),
                       ("mipmap-xxxhdpi", 192)):
        save(normal, px, os.path.join(ANDROID_RES, folder, "ic_launcher.png"))

    # 预览图，方便肉眼检查（不参与打包）
    preview = render_master(512, maskable=False)
    preview.save(os.path.join(ROOT, "icon-preview.png"))
    print("\n预览已生成: icon-preview.png")


if __name__ == "__main__":
    main()
