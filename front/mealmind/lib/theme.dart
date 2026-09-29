import 'package:flutter/material.dart';

/// =====================================================================
/// 食时 · 设计 token
///
/// ⚠️ 这些值原本逐字抄自队友的 `team/dist/styles.css` 的 `:root`。
///    改这里之前，先确认队友那边是不是也改了 —— 两边必须一致，
///    否则 Flutter App 和网页原型会长得不一样。
///
/// ★ 暖化调整（2026-09）：中性色从「冷绿灰」调成「暖米」——
///   页面背景、正文、次级文字、边框，外加 green50（原来是最浅的绿）。
///   目的只是把整体色温调暖，**品牌绿（green900/700/600/100）和
///   橙色（orange/orange100）一个都没动**，所以绿色的品牌识别还在。
///
///   ⚠️ 这意味着 theme.dart 与 `dist/styles.css` 的 `:root` 不再逐字一致。
///   要和网页原型同步的话，得把下面这几个值也搬过去。
/// =====================================================================

// ---- 橙色系（★ 方案 B：从「点缀色」升为「主色」）----
// 原来这里只有两个值，注释还写着「只用于 CTA / 季节标签，不要大面积用」。
// 现在暖色成为主色，所以补齐了整个色阶。
const orange900 = Color(0xFF8A3D12); // 深焦糖：品牌、hero 标题、深色区块
const orange700 = Color(0xFFD2601F); // ★ 主色：按钮、选中态、CTA
const orange = Color(0xFFF5742E); // 亮橙：强调、季节标签
const orange100 = Color(0xFFFFF0E4); // 浅橙：标签底色
const orange50 = Color(0xFFF6F1E9); // 次级区域底：暖砂

// ---- 绿色（★ 已降为「语义色」）----
// 只留给「当季 / 新鲜 / 健康」这类真正需要绿色的含义。
// ⚠️ 新的主色位置一律用 orange700，不要再往 green700 上加调用点了。
const green900 = Color(0xFF0B532F);
const green700 = Color(0xFF17733D);
const green600 = Color(0xFF2E8B43);
const green100 = Color(0xFFE8F5E3); // 浅绿：至今仍是「当季」类标签的底色
const green50 = Color(0xFFF3F9EF);

// ---- 中性色（★ 暖化重点：原本都是带绿调的冷色）----
const ink = Color(0xFF2A241E); // 正文：暖黑（原 #172019 是绿黑）
const muted = Color(0xFF7C7168); // 次级文字：暖灰（原 #687069 偏冷）
const line = Color(0xFFF0E7DE); // 边框：暖灰（原 #E5EBE3 偏冷）
const cream = Color(0xFFFFFCF6); // 米白
const page = Color(0xFFFBF7F1); // 页面背景：暖米（★ 原 #F4F7F1 是冷绿灰）

// ---- 圆角规范 ----
const rTag = 8.0; // 小标签
const rCard = 20.0; // 卡片
const rBlock = 24.0; // 大区块 / 弹层
const rHero = 28.0; // hero 区

// ---- 卡片阴影（原来对应 CSS 的 0 8px 24px rgba(27,81,44,.07)）----
// 阴影色从带绿的 0x1B512C 换成暖棕 0x4A3423 ——
// 冷色阴影压在暖色底上会发灰发脏。
const cardShadow = <BoxShadow>[
  BoxShadow(color: Color(0x144A3423), blurRadius: 24, offset: Offset(0, 8)),
];

// ---- 可直接复用的装饰 ----

/// 白卡片：白底 + 1px 边线 + 20 圆角 + 柔和阴影
BoxDecoration cardDeco({double radius = rCard}) => BoxDecoration(
      color: Colors.white,
      border: Border.all(color: line),
      borderRadius: BorderRadius.circular(radius),
      boxShadow: cardShadow,
    );

/// 浅橙标签（默认）。
/// 需要「当季 / 新鲜」这类绿色语义时，显式传 `bg: green100`。
BoxDecoration tagDeco({Color bg = orange100}) => BoxDecoration(
      color: bg,
      borderRadius: BorderRadius.circular(rTag),
    );
