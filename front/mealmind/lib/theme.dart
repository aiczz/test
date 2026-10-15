import 'package:flutter/material.dart';

/// 食时共享配色：低饱和草木绿，搭配米白背景。
const green900 = Color(0xFF355C45);
const green700 = Color(0xFF50765B);
const green600 = Color(0xFF72916C);
const green100 = Color(0xFFEDF3E9);
const green50 = Color(0xFFF5F7F0);

// 品牌色用于按钮、标签、导航与重点区域。
const brand900 = green900;
const brand700 = green700;
const brand600 = green600;
const brand100 = green100;
const brand50 = green50;

const ink = Color(0xFF2D3830);
const muted = Color(0xFF747D72);
const line = Color(0xFFE7EBE2);
const cream = Color(0xFFFEFEFA);
const page = Color(0xFFFAFAF5);

// ---- 危险色（★ 只给「永久删除」这一类不可恢复的操作）----
// 危险操作保留独立红色，避免与保存等常规按钮混淆。
// ⚠️ 不要把它当第二个强调色用：这个颜色出现得越少，它挡误触的作用越大。
const danger = Color(0xFFC0392B); // 危险操作
const danger100 = Color(0xFFFDECEA); // 浅红：危险区块底 / 禁用态按钮底

// ---- 圆角规范 ----
const rTag = 8.0; // 小标签
const rCard = 20.0; // 卡片
const rBlock = 24.0; // 大区块 / 弹层
const rHero = 28.0; // hero 区

// ---- 卡片阴影（原来对应 CSS 的 0 8px 24px rgba(27,81,44,.07)）----
// 使用淡绿色阴影，与品牌配色保持一致。
const cardShadow = <BoxShadow>[
  BoxShadow(color: Color(0x0C355C45), blurRadius: 24, offset: Offset(0, 8)),
];

// ---- 可直接复用的装饰 ----

/// 白卡片：白底 + 1px 边线 + 20 圆角 + 柔和阴影
BoxDecoration cardDeco({double radius = rCard}) => BoxDecoration(
  color: Colors.white,
  border: Border.all(color: line),
  borderRadius: BorderRadius.circular(radius),
  boxShadow: cardShadow,
);

/// 浅绿标签（默认）。
/// 需要「当季 / 新鲜」这类绿色语义时，显式传 `bg: green100`。
BoxDecoration tagDeco({Color bg = brand100}) =>
    BoxDecoration(color: bg, borderRadius: BorderRadius.circular(rTag));
