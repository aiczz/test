import 'package:flutter/material.dart';

import '../theme.dart';

/// =====================================================================
/// 「本周菜单」入口卡片
///
/// 【为什么要做成公共组件】
/// 首页和「我的」页各需要一个 —— 这两处的用户都会想去看完整方案：
///   · 首页：浏览完「今日推荐食材 / 菜品」，下一步就是行动
///   · 「我的」页：刚改完家庭档案，提示说「菜单已按新约束重算」，
///     自然想看看重算成了什么
/// 同一类「点一下去别处」的行，在项目里应该长得一样，所以只写一份。
///
/// 【它修的是什么】
/// menu.dart 那一页（权衡滑杆 / 钠摄入进度条 / 每项价格的来源与置信度 /
/// 购物清单）此前是【死代码】—— 底部导航 5 项里没有它，也没有任何按钮
/// 指向它，而「我的」页却一直对用户说「菜单与购物清单已按新约束重算」。
/// 等于反复承诺一个永远打不开的页面。
///
/// 样式对齐首页的家庭约束条：图标方块 + 主副标题 + 右侧「去看看」+ 箭头。
/// =====================================================================
class MenuEntryCard extends StatelessWidget {
  final VoidCallback onTap;

  const MenuEntryCard({super.key, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(rCard),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
        decoration: cardDeco(),
        child: Row(
          children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                color: orange100,
                borderRadius: BorderRadius.circular(11),
              ),
              child: const Icon(
                Icons.calendar_month_rounded,
                size: 18,
                color: orange700,
              ),
            ),
            const SizedBox(width: 10),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '本周菜单',
                    style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w800,
                      color: ink,
                    ),
                  ),
                  SizedBox(height: 3),
                  Text(
                    '按家庭档案算好的一周怎么吃，含买菜清单',
                    style: TextStyle(fontSize: 10.5, color: muted),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            const Text(
              '去看看',
              style: TextStyle(
                fontSize: 11,
                color: orange700,
                fontWeight: FontWeight.w700,
              ),
            ),
            const Icon(Icons.chevron_right, size: 16, color: orange700),
          ],
        ),
      ),
    );
  }
}
