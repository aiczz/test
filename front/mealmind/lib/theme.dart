import 'package:flutter/material.dart';

/// =====================================================================
/// 食时 · 设计 token
///
/// ⚠️ 这些值逐字抄自队友的 `team/dist/styles.css` 的 `:root`。
///    改这里之前，先确认队友那边是不是也改了 —— 两边必须一致，
///    否则 Flutter App 和网页原型会长得不一样。
/// =====================================================================

// ---- 绿色系（主色）----
const green900 = Color(0xFF0B532F); // 深绿：品牌、hero 标题、侧栏
const green700 = Color(0xFF17733D); // 主绿：按钮、图标底
const green600 = Color(0xFF2E8B43); // 中绿
const green100 = Color(0xFFE8F5E3); // 浅绿：标签底色
const green50 = Color(0xFFF3F9EF); // 极浅绿：卡片底

// ---- 橙色（只用于 CTA / 季节标签，不要大面积用）----
const orange = Color(0xFFF5742E);
const orange100 = Color(0xFFFFF0E4);

// ---- 中性色 ----
const ink = Color(0xFF172019); // 正文
const muted = Color(0xFF687069); // 次级文字
const line = Color(0xFFE5EBE3); // 边框
const cream = Color(0xFFFFFDF8); // 米白
const page = Color(0xFFF4F7F1); // 页面背景

// ---- 圆角规范 ----
const rTag = 8.0; // 小标签
const rCard = 20.0; // 卡片
const rBlock = 24.0; // 大区块 / 弹层
const rHero = 28.0; // hero 区

// ---- 卡片阴影（对应 CSS 的 0 8px 24px rgba(27,81,44,.07)）----
const cardShadow = <BoxShadow>[
  BoxShadow(color: Color(0x121B512C), blurRadius: 24, offset: Offset(0, 8)),
];

// ---- 可直接复用的装饰 ----

/// 白卡片：白底 + 1px 边线 + 20 圆角 + 柔和阴影
BoxDecoration cardDeco({double radius = rCard}) => BoxDecoration(
      color: Colors.white,
      border: Border.all(color: line),
      borderRadius: BorderRadius.circular(radius),
      boxShadow: cardShadow,
    );

/// 浅绿标签
BoxDecoration tagDeco({Color bg = green100}) => BoxDecoration(
      color: bg,
      borderRadius: BorderRadius.circular(rTag),
    );
