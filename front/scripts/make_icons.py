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

# Android 各密度的基准尺寸（传统图标的 48dp）
ADAPTIVE_FOLDERS = (
    ("mipmap-mdpi", 48),
    ("mipmap-hdpi", 72),
    ("mipmap-xhdpi", 96),
    ("mipmap-xxhdpi", 144),
    ("mipmap-xxxhdpi", 192),
)
# 自适应图标的前景层是 108dp，所以是传统图标的 2.25 倍
ADAPTIVE_SCALE = 108 / 48.0

# 主体内容在画布中的缩放系数。
#
# ⚠️ 这里不能按「主体跨度占比」算，必须按【主体离画布中心的最远距离】去卡安全圆。
#    原因：设计稿自带留白（主体只占画布约 53%~57%），而且主体重心偏下
#    （碗在下、筷子在上，内容中心在 y≈0.526 而不是 0.5）。
#    第一版就是只看了跨度、没看重心，结果 Android 圆裁切把碗底切平了。
#
#    实测（最远距离 / 安全圆半径）：
#      normal      圆角方图，可见区就是整张画布          k=1.00
#      maskable    PWA 要求落在中心 80% 圆内 R=0.4000    k=1.23  余量 5.1%
#      foreground  Android 安全区 72/108 圆内 R=0.3335   k=1.02  余量 5.6%
#
#    最远距离与 k 成正比。改完这些系数，脚本末尾的 verify() 会自己校验并报错。
CONTENT_K = {
    "normal": 1.0,
    "maskable": 1.23,
    "foreground": 1.02,
}

# 各自的安全圆半径（画布归一化单位）
SAFE_RADIUS = {
    "maskable": 0.80 / 2,      # PWA maskable：内容须落在中心 80% 圆内
    "foreground": 0.667 / 2,   # Android 自适应：安全区 72/108 = 66.7%
}

ADAPTIVE_XML = """<?xml version="1.0" encoding="utf-8"?>
<!-- 由 scripts/make_icons.py 生成，请勿手改 -->
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
"""

BG_XML = """<?xml version="1.0" encoding="utf-8"?>
<!-- 由 scripts/make_icons.py 生成，请勿手改 -->
<resources>
    <color name="ic_launcher_background">#17733D</color>
</resources>
"""


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _rounded_line(draw, p1, p2, width, fill):
    """画一条两端带圆头的粗线（Pillow 的 line 没有 line-cap）。"""
    draw.line([p1, p2], fill=fill, width=width)
    r = width / 2.0
    for (x, y) in (p1, p2):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def render_master(px, mode="normal"):
    """渲染一张 px×px 的主图。

    mode="normal"      圆角方底 + 主体，内容可见区域就是整张画布
    mode="maskable"    底色铺满（不做圆角），主体放大到中心 80% 圆内，
                       适配 PWA 被系统裁成圆形 / 方形 / squircle 的情况
    mode="foreground"  透明底 + 主体，供 Android 自适应图标当前景层，
                       底色由 ic_launcher_background 提供

    ⚠️ 注意这里的主体是【放大】而不是缩小：设计稿本身已经自带留白
       （内容只占画布高度的 56.8%），所以安全区越严格，系数反而要越大。
    """
    S = px
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # ---- 1. 背景：竖向渐变，用圆角矩形做遮罩 ----
    if mode != "foreground":
        grad = Image.new("RGB", (S, S))
        gd = ImageDraw.Draw(grad)
        for y in range(S):
            gd.line([(0, y), (S, y)],
                    fill=_lerp(GREEN_700, GREEN_900, y / (S - 1)))
        bg_mask = Image.new("L", (S, S), 0)
        radius = 0 if mode == "maskable" else int(S * 0.22)
        ImageDraw.Draw(bg_mask).rounded_rectangle(
            [0, 0, S - 1, S - 1], radius=radius, fill=255)
        img.paste(grad, (0, 0), bg_mask)

    d = ImageDraw.Draw(img)
    k = CONTENT_K[mode]

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


def write_text(path, text):
    """写文本文件（统一 LF，避免 Windows 上产生 CRLF 噪音）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("       {}".format(os.path.relpath(path, ROOT)))


def _farthest_from_center(path, pick):
    """求主体像素离画布中心的最远距离（归一化，0.5 = 画布边缘中点）。

    pick="alpha"  取不透明像素 —— 前景层用（底色透明，可以直接按 alpha 判）
    pick="cream"  取米白像素   —— maskable 用（底色不透明，按 alpha 判会得到整张画布）
    """
    im = Image.open(path).convert("RGBA")
    size = im.size[0]
    worst = 0.0
    for idx, (r, g, b, a) in enumerate(im.getdata()):
        if pick == "alpha":
            if a <= 128:
                continue
        elif not (r > 200 and g > 200 and b > 200):
            continue
        dx = (idx % size) / size - 0.5
        dy = (idx // size) / size - 0.5
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > worst:
            worst = dist
    return worst


def verify(targets):
    """校验主体没有超出安全圆。

    这是本脚本最重要的一步：主体一旦越界，Android / PWA 的圆形裁切会把
    图案切掉一块（碗底被切平），而且只有装到手机上看才发现。这里直接量出来。
    """
    print("\n安全区自检：")
    overflowed = []
    for mode, pick, path in targets:
        radius = SAFE_RADIUS[mode]
        worst = _farthest_from_center(path, pick)
        margin = (radius - worst) / radius * 100
        verdict = "OK" if worst <= radius else "溢出！"
        print("  {:<11} 最远 {:.4f} / 安全 {:.4f}   余量 {:>5.1f}%   {}".format(
            mode, worst, radius, margin, verdict))
        if worst > radius:
            overflowed.append(mode)
    if overflowed:
        raise SystemExit(
            "\n构建失败：{} 的主体超出安全区，请调小 CONTENT_K 后重跑。".format(
                "、".join(overflowed)))
    print("  主体均在安全区内 ✓")


def main():
    normal = render_master(512 * SS, mode="normal")
    maskable = render_master(512 * SS, mode="maskable")
    # 前景层最大要 432px（108dp @ xxxhdpi）
    foreground = render_master(432 * SS, mode="foreground")

    print("网页 / PWA 图标：")
    save(normal, 512, os.path.join(WEB_ICONS, "Icon-512.png"))
    save(normal, 192, os.path.join(WEB_ICONS, "Icon-192.png"))
    save(maskable, 512, os.path.join(WEB_ICONS, "Icon-maskable-512.png"))
    save(maskable, 192, os.path.join(WEB_ICONS, "Icon-maskable-192.png"))
    save(normal, 32, WEB_FAVICON)

    print("Android 传统图标（Android 7 及以下，兼兜底）：")
    for folder, px in ADAPTIVE_FOLDERS:
        save(normal, px, os.path.join(ANDROID_RES, folder, "ic_launcher.png"))

    print("Android 自适应图标（Android 8.0+）：")
    for folder, px in ADAPTIVE_FOLDERS:
        save(foreground, int(px * ADAPTIVE_SCALE),
             os.path.join(ANDROID_RES, folder, "ic_launcher_foreground.png"))
    write_text(
        os.path.join(ANDROID_RES, "mipmap-anydpi-v26", "ic_launcher.xml"),
        ADAPTIVE_XML)
    write_text(
        os.path.join(ANDROID_RES, "values", "ic_launcher_background.xml"),
        BG_XML)

    # ★ 自检：主体越界的话，Android / PWA 的圆形裁切会把图案切掉一块
    verify([
        ("maskable", "cream",
         os.path.join(WEB_ICONS, "Icon-maskable-512.png")),
        ("foreground", "alpha",
         os.path.join(ANDROID_RES, "mipmap-xxxhdpi",
                      "ic_launcher_foreground.png")),
    ])

    # 预览图，方便肉眼检查（不参与打包）
    render_master(512, mode="normal").save(
        os.path.join(ROOT, "icon-preview.png"))
    print("\n预览已生成: icon-preview.png")


if __name__ == "__main__":
    main()
