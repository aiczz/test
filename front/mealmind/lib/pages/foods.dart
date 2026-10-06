import 'dart:async';

import 'package:flutter/material.dart';

import '../models/content.dart';
import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../services/backend_api.dart';
import '../services/content_store.dart';
import '../theme.dart';
import '../widgets/dish_photo.dart';
import '../widgets/food_photo.dart';

/// 食材页：时令浏览 + 家中库存 + 选中食材交给 AI。
class FoodsPage extends StatefulWidget {
  final ValueChanged<List<String>> onAskAi;

  const FoodsPage({super.key, required this.onAskAi});

  @override
  State<FoodsPage> createState() => FoodsPageState();
}

/// 状态类做成公开的 —— 首页的食材卡片要能直接打开这里的详情弹层。
/// main.dart 用 GlobalKey 拿到它并调 [openFoodDetail]，
/// 这样两个地方点出来的详情长得完全一样，不用维护两份。
class FoodsPageState extends State<FoodsPage> {
  final TextEditingController _search = TextEditingController();
  final List<Food> _pantry = <Food>[];
  final Set<String> _selected = <String>{};
  final Map<String, int> _amounts = <String, int>{};
  String _category = '全部';
  bool _showPantry = false;
  int _foodPage = 0;
  static const _pageSize = 40;

  /// Food.id → 后端那条库存记录的 id。
  /// 删除要调 /api/my-foods/{item_id}，用的是记录 id 而不是 food_id。
  final Map<String, int> _serverItemIds = <String, int>{};

  /// 「时令」是和其他几项并列的一个特殊分支 ——
  /// 前几项按食材分类（category）切，它按「当季」切，
  /// 所以判定走 ContentStore.isSeasonal()，而不是比 category 字符串。
  static const _categories = <String>[
    '全部',
    '时令',
    '蔬菜',
    '水果',
    '肉蛋',
    '水产',
    '豆制品',
    '主食',
    '其他',
  ];

  /// 能不能和后端同步「我的食材」。三个条件缺一不可：
  ///   1. 后端连着 —— 否则同步到哪去
  ///   2. 登录了 —— /api/my-foods 需要 token
  ///   3. 用的是后端内容 —— 接口要数字 food_id，而本地假数据的 id
  ///      是 'lotus' 这种字符串，传不过去
  bool get _canSync =>
      ContentStore.instance.fromBackend && AuthStore.instance.isLoggedIn;

  @override
  void initState() {
    super.initState();
    unawaited(_loadPantryFromServer());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  /// 登录状态下从后端拉「我的食材」；拿不到就保持本页的临时列表。
  Future<void> _loadPantryFromServer() async {
    if (!_canSync) return;
    try {
      final items = await BackendApi.instance.fetchMyFoods();
      if (!mounted) return;
      setState(() {
        _pantry.clear();
        _serverItemIds.clear();
        for (final item in items) {
          final food = _matchLocalFood(item);
          if (food == null) continue;
          _pantry.add(food);
          _serverItemIds[food.id] = item.id;
          _amounts[food.id] = item.amount.round();
        }
      });
    } catch (error) {
      debugPrint('[FoodsPage] 我的食材加载失败，保持本地列表：$error');
    }
  }

  /// 后端条目 → 本地 Food。内容库里找不到就返回 null（避免渲染空图）。
  Food? _matchLocalFood(MyFoodEntry entry) {
    if (entry.foodId == null) return null;
    final id = '${entry.foodId}';
    for (final food in ContentStore.instance.foods) {
      if (food.id == id) return food;
    }
    return null;
  }

  Future<void> _syncAdd(Food food) async {
    if (!_canSync) return;
    final foodId = int.tryParse(food.id);
    if (foodId == null) return;
    try {
      final item = await BackendApi.instance.addMyFood(
        foodId: foodId,
        amount: (_amounts[food.id] ?? 1).toDouble(),
      );
      if (!mounted) return;
      if (_pantry.any((entry) => entry.id == food.id)) {
        _serverItemIds[food.id] = item.id;
      } else {
        // 用户可能在请求返回前又点了勾取消；此时把刚创建的服务端记录清掉。
        await BackendApi.instance.removeMyFood(item.id);
      }
    } catch (error) {
      debugPrint('[FoodsPage] 加入我的食材同步失败：$error');
    }
  }

  Future<void> _syncRemove(Food food) async {
    if (!_canSync) return;
    final itemId = _serverItemIds.remove(food.id);
    if (itemId == null) return;
    try {
      await BackendApi.instance.removeMyFood(itemId);
    } catch (error) {
      debugPrint('[FoodsPage] 移出我的食材同步失败：$error');
    }
  }

  List<Food> get _visibleFoods {
    final source = _showPantry ? _pantry : ContentStore.instance.foods;
    final query = _search.text.trim().toLowerCase();
    return source.where((food) {
      final categoryOk = switch (_category) {
        '全部' => true,
        '时令' => ContentStore.instance.isSeasonal(food),
        _ => food.category == _category,
      };
      final queryOk =
          query.isEmpty ||
          food.name.toLowerCase().contains(query) ||
          food.tags.any((tag) => tag.toLowerCase().contains(query));
      return categoryOk && queryOk;
    }).toList();
  }

  void _toggleSelected(Food food) {
    setState(() {
      if (!_selected.add(food.id)) _selected.remove(food.id);
    });
  }

  void _changeAmount(Food food, int delta) {
    final next = (_amounts[food.id] ?? 1) + delta;
    if (next < 1) return;
    setState(() => _amounts[food.id] = next);
  }

  void _removeFood(Food food) {
    setState(() {
      _pantry.removeWhere((item) => item.id == food.id);
      _selected.remove(food.id);
      _amounts.remove(food.id);
    });
    // 这里原本会弹一条「已将 X 从我的食材移除」的浮层提示。
    // 去掉了：卡片上的加号会立刻变回未选中态、食材也当场从列表里消失，
    // 视觉反馈已经足够；再压一条浮层只是挡住下面的内容。
    unawaited(_syncRemove(food));
  }

  void _togglePantry(Food food) {
    final isInPantry = _pantry.any((item) => item.id == food.id);
    if (isInPantry) {
      _removeFood(food);
    } else {
      _addToPantry(food);
    }
  }

  void _addToPantry(Food food) {
    if (_pantry.any((item) => item.id == food.id)) {
      _toast('${food.name}已经在我的食材里了');
      return;
    }
    setState(() {
      _pantry.add(food);
      _amounts[food.id] = 1;
    });
    // 这里原本弹「已将 X 添加到我的食材」。和移除那边对称地去掉：
    // 加号当场变 ✓、食材进列表，视觉反馈已经够了。
    unawaited(_syncAdd(food));
  }

  Future<void> _addFood() async {
    final name = TextEditingController();
    String category = '蔬菜';
    final result = await showDialog<Food>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('手动添加食材'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: name,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: '食材名称',
                  hintText: '例如：菠菜',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 14),
              const Text('分类', style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 7,
                children: _categories.skip(1).map((item) {
                  return ChoiceChip(
                    label: Text(item),
                    selected: category == item,
                    onSelected: (_) => setDialogState(() => category = item),
                  );
                }).toList(),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () {
                final value = name.text.trim();
                if (value.isEmpty) return;
                Navigator.pop(
                  context,
                  Food(
                    id: 'custom_${DateTime.now().millisecondsSinceEpoch}',
                    name: value,
                    image: 'assets/images/bokchoy-clean.jpg',
                    category: category,
                    tags: const ['手动添加'],
                  ),
                );
              },
              child: const Text('添加'),
            ),
          ],
        ),
      ),
    );
    name.dispose();
    if (result == null || !mounted) return;
    setState(() {
      _pantry.add(result);
      _amounts[result.id] = 1;
      _showPantry = true;
    });
    // 同上：不再弹「已添加 X」—— 自动切到「我的食材」这个动作本身就是反馈。
  }

  /// 打开食材详情弹层（时令、能做的菜、加入我的食材）。
  ///
  /// 公开方法 —— 首页的食材卡片也走这里，保证两处详情一致。
  ///
  /// ⚠️ 这个弹层以前有三处「编出来的话」，都改掉了：
  ///   1. 「应季指数 92」是写死的常量，不管打开哪个食材都是 92；
  ///   2. 「XX 正值当季，口感更鲜」对**每个**食材都说，哪怕是反季的；
  ///   3. 「适合做这些菜」在本地用 `recipe.ingredients` 反查 ——
  ///      可列表接口根本不返回 ingredients，于是永远匹配 0 条，
  ///      静默退化成「取前两道菜」，点任何食材看到的都是同两道。
  ///   现在指数用后端的 season_score，「能做的菜」走后端关联，
  ///   两样都拿不到时如实说明，不编。
  void openFoodDetail(Food food) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => DraggableScrollableSheet(
        initialChildSize: 0.72,
        minChildSize: 0.5,
        maxChildSize: 0.9,
        expand: false,
        builder: (context, controller) => Container(
          decoration: const BoxDecoration(
            color: page,
            borderRadius: BorderRadius.vertical(top: Radius.circular(rBlock)),
          ),
          child: ListView(
            controller: controller,
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 30),
            children: [
              Center(
                child: Container(
                  width: 42,
                  height: 4,
                  decoration: BoxDecoration(
                    color: line,
                    borderRadius: BorderRadius.circular(99),
                  ),
                ),
              ),
              const SizedBox(height: 18),
              ClipRRect(
                borderRadius: BorderRadius.circular(rCard),
                child: AspectRatio(
                  aspectRatio: 1.8,
                  child: FoodPhoto(asset: food.image),
                ),
              ),
              const SizedBox(height: 18),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      food.name,
                      style: const TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w900,
                        color: orange900,
                      ),
                    ),
                  ),
                  // 「当季推荐」只在**确实是当季**时才挂，不是每个食材都挂
                  if (ContentStore.instance.isSeasonal(food))
                    const _DetailSeasonBadge(),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                _seasonBlurb(food),
                style: const TextStyle(fontSize: 14, color: muted, height: 1.7),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final tag in food.tags) _Tag(text: tag),
                  // 应季指数用后端算出来的真实分值；拿不到就不显示
                  if (food.seasonScore != null)
                    _Tag(text: '应季指数 ${food.seasonScore}'),
                ],
              ),
              const SizedBox(height: 24),
              const Text(
                '适合做这些菜',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 12),
              _FoodRecipeSuggestions(food: food),
            ],
          ),
        ),
      ),
    );
  }

  /// 食材详情里那句介绍。
  ///
  /// 当季 / 不当季说的话不一样 —— 以前不管三七二十一都说「正值当季」。
  String _seasonBlurb(Food food) {
    if (ContentStore.instance.isSeasonal(food)) {
      return '${food.name}正值当季，口感更鲜、运输距离更短。'
          '适合安排进本周菜单，也可以优先消耗家中库存。';
    }
    if (food.season != null && food.season!.isNotEmpty) {
      return '${food.name}的时令是${food.season}，现在不是它最好的时候 —— '
          '反季的也能吃，但风味和价格通常不如当季。';
    }
    // 后端不返回季节名（只返回应季指数），这时不硬说当季还是反季
    return '${food.name}的营养数据、可做菜谱都来自清洗后的食材库。';
  }

  /// 从“我的”页统计卡进入时，直接展示库存，而不是仍停留在推荐列表。
  void openPantry() {
    if (!mounted) return;
    setState(() => _showPantry = true);
  }

  void _sendToAi() {
    final names = _pantry
        .where((food) => _selected.contains(food.id))
        .map((food) => food.name)
        .toList();
    if (names.isEmpty) {
      _toast('请先选择至少一种食材');
      return;
    }
    widget.onAskAi(names);
  }

  void _toast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        backgroundColor: orange900,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final foods = _visibleFoods;
    final pageCount = foods.isEmpty ? 1 : (foods.length / _pageSize).ceil();
    final currentPage = _foodPage.clamp(0, pageCount - 1);
    final pageFoods = foods
        .skip(currentPage * _pageSize)
        .take(_pageSize)
        .toList();
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 120),
                children: [
                  _FoodsHeader(
                    showPantry: _showPantry,
                    pantryCount: _pantry.length,
                    onChanged: (value) => setState(() {
                      _showPantry = value;
                      _foodPage = 0;
                    }),
                    onAdd: _addFood,
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _search,
                    onChanged: (_) => setState(() => _foodPage = 0),
                    decoration: InputDecoration(
                      hintText: '搜索食材或营养特点',
                      prefixIcon: const Icon(Icons.search),
                      suffixIcon: _search.text.isEmpty
                          ? null
                          : IconButton(
                              onPressed: () {
                                _search.clear();
                                setState(() => _foodPage = 0);
                              },
                              icon: const Icon(Icons.close),
                            ),
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(16),
                        borderSide: const BorderSide(color: line),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(16),
                        borderSide: const BorderSide(color: line),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final category in _categories)
                        _CategoryChip(
                          category: category,
                          selected: _category == category,
                          onSelected: () => setState(() {
                            _category = category;
                            _foodPage = 0;
                          }),
                        ),
                    ],
                  ),
                  const SizedBox(height: 22),
                  Row(
                    children: [
                      Container(
                        width: 38,
                        height: 38,
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [orange, orange700],
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          ),
                          borderRadius: BorderRadius.circular(13),
                          boxShadow: const [
                            BoxShadow(
                              color: Color(0x25D2601F),
                              blurRadius: 10,
                              offset: Offset(0, 4),
                            ),
                          ],
                        ),
                        child: Icon(
                          _showPantry
                              ? Icons.inventory_2_rounded
                              : Icons.eco_rounded,
                          color: Colors.white,
                          size: 21,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        _showPantry
                            ? '我家的食材'
                            : (_category == '全部' ? '全部食材' : _category),
                        style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const Spacer(),
                      Text(
                        '${foods.length} 项',
                        style: const TextStyle(fontSize: 12, color: muted),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (foods.isEmpty)
                    _EmptyFoods(
                      pantryIsEmpty: _showPantry && _pantry.isEmpty,
                      onBrowse: () => setState(() {
                        _showPantry = false;
                        _category = '全部';
                        _search.clear();
                      }),
                    )
                  else
                    LayoutBuilder(
                      builder: (context, constraints) {
                        const spacing = 12.0;
                        final cardWidth = (constraints.maxWidth - spacing) / 2;
                        final imageHeight = cardWidth / 1.8;
                        final contentHeight = _showPantry ? 154.0 : 132.0;
                        return GridView.builder(
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          itemCount: pageFoods.length,
                          gridDelegate:
                              SliverGridDelegateWithFixedCrossAxisCount(
                                crossAxisCount: 2,
                                crossAxisSpacing: spacing,
                                mainAxisSpacing: spacing,
                                mainAxisExtent: imageHeight + contentHeight,
                              ),
                          itemBuilder: (context, index) {
                            final food = pageFoods[index];
                            return _FoodInventoryCard(
                              food: food,
                              pantryMode: _showPantry,
                              inPantry: _pantry.any(
                                (item) => item.id == food.id,
                              ),
                              selected: _selected.contains(food.id),
                              amount: _amounts[food.id] ?? 1,
                              onTap: () => openFoodDetail(food),
                              onToggle: () => _toggleSelected(food),
                              onAdd: () => _togglePantry(food),
                              onMinus: () => _changeAmount(food, -1),
                              onPlus: () => _changeAmount(food, 1),
                              onDelete: () => _removeFood(food),
                            );
                          },
                        );
                      },
                    ),
                  if (pageCount > 1)
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        TextButton(
                          onPressed: currentPage > 0
                              ? () =>
                                    setState(() => _foodPage = currentPage - 1)
                              : null,
                          child: const Text('上一页'),
                        ),
                        Text('${currentPage + 1} / $pageCount 页'),
                        TextButton(
                          onPressed: currentPage + 1 < pageCount
                              ? () =>
                                    setState(() => _foodPage = currentPage + 1)
                              : null,
                          child: const Text('下一页'),
                        ),
                      ],
                    ),
                  if (_showPantry) ...[
                    const SizedBox(height: 14),
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: orange50,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: const Row(
                        children: [
                          Icon(Icons.lightbulb_outline, color: orange700),
                          SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              '及时更新库存和数量，AI 才能优先消耗临期食材。',
                              style: TextStyle(fontSize: 12, color: muted),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
      floatingActionButton: AnimatedSwitcher(
        duration: const Duration(milliseconds: 180),
        child: _showPantry
            ? SizedBox(
                key: const ValueKey('cook'),
                width: 300,
                child: FilledButton.icon(
                  onPressed: _sendToAi,
                  style: FilledButton.styleFrom(
                    backgroundColor: orange,
                    padding: const EdgeInsets.symmetric(vertical: 15),
                    shape: const StadiumBorder(),
                  ),
                  icon: const Icon(Icons.auto_awesome),
                  label: Text('用已选 ${_selected.length} 种食材做菜'),
                ),
              )
            : const SizedBox.shrink(key: ValueKey('empty')),
      ),
    );
  }
}

class _FoodsHeader extends StatelessWidget {
  final bool showPantry;
  final int pantryCount;
  final ValueChanged<bool> onChanged;
  final VoidCallback onAdd;

  const _FoodsHeader({
    required this.showPantry,
    required this.pantryCount,
    required this.onChanged,
    required this.onAdd,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [orange50, Color(0xFFFFF2D9)],
        ),
        borderRadius: BorderRadius.circular(rBlock),
        boxShadow: cardShadow,
      ),
      child: Stack(
        children: [
          Positioned(
            right: -38,
            top: -52,
            child: Container(
              width: 150,
              height: 150,
              decoration: const BoxDecoration(
                color: Color(0x33FFFFFF),
                shape: BoxShape.circle,
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 18, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 9,
                              vertical: 5,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: .72),
                              borderRadius: BorderRadius.circular(99),
                              border: Border.all(
                                color: Colors.white.withValues(alpha: .9),
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  showPantry
                                      ? Icons.inventory_2_outlined
                                      : Icons.eco_outlined,
                                  size: 13,
                                  color: orange700,
                                ),
                                const SizedBox(width: 5),
                                Text(
                                  showPantry ? '家庭库存' : '杭州 · 秋季',
                                  style: const TextStyle(
                                    color: orange700,
                                    fontSize: 10.5,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 10),
                          Text(
                            showPantry ? '我家的食材' : '全部食材',
                            style: const TextStyle(
                              color: orange900,
                              fontSize: 28,
                              fontWeight: FontWeight.w900,
                              letterSpacing: -1,
                            ),
                          ),
                          const SizedBox(height: 5),
                          Text(
                            showPantry ? '随手记录库存，做饭更省心' : '挑选正当季的新鲜味道',
                            style: const TextStyle(
                              color: muted,
                              fontSize: 12.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    const SizedBox(
                      width: 128,
                      height: 104,
                      child: Stack(
                        clipBehavior: Clip.none,
                        children: [
                          Positioned(
                            right: 0,
                            top: 0,
                            child: _FoodBubble(
                              asset: 'assets/images/pumpkin-clean.jpg',
                              size: 78,
                            ),
                          ),
                          Positioned(
                            left: 0,
                            bottom: 0,
                            child: _FoodBubble(
                              asset: 'assets/images/lotus-clean.jpg',
                              size: 64,
                            ),
                          ),
                          Positioned(
                            left: 48,
                            bottom: -1,
                            child: _FoodBubble(
                              asset: 'assets/images/bokchoy-clean.jpg',
                              size: 48,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: Container(
                        height: 48,
                        padding: const EdgeInsets.all(4),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: .74),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: Colors.white.withValues(alpha: .9),
                          ),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: _FoodHeaderTab(
                                selected: !showPantry,
                                icon: Icons.eco_rounded,
                                label: '全部食材',
                                onTap: () => onChanged(false),
                              ),
                            ),
                            const SizedBox(width: 4),
                            Expanded(
                              child: _FoodHeaderTab(
                                selected: showPantry,
                                icon: Icons.inventory_2_rounded,
                                label: '我的 $pantryCount',
                                onTap: () => onChanged(true),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    if (showPantry) ...[
                      const SizedBox(width: 8),
                      IconButton.filled(
                        onPressed: onAdd,
                        tooltip: '手动添加食材',
                        style: IconButton.styleFrom(
                          backgroundColor: orange,
                          foregroundColor: Colors.white,
                          minimumSize: const Size(48, 48),
                        ),
                        icon: const Icon(Icons.add_rounded),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FoodBubble extends StatelessWidget {
  final String asset;
  final double size;

  const _FoodBubble({required this.asset, required this.size});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: Colors.white,
        shape: BoxShape.circle,
        boxShadow: const [
          BoxShadow(
            color: Color(0x26D2601F),
            blurRadius: 12,
            offset: Offset(0, 5),
          ),
        ],
      ),
      child: ClipOval(
        child: Image.asset(
          asset,
          fit: BoxFit.cover,
          filterQuality: FilterQuality.high,
        ),
      ),
    );
  }
}

class _FoodHeaderTab extends StatelessWidget {
  final bool selected;
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _FoodHeaderTab({
    required this.selected,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          decoration: BoxDecoration(
            color: selected ? orange700 : Colors.transparent,
            borderRadius: BorderRadius.circular(12),
          ),
          alignment: Alignment.center,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 17, color: selected ? Colors.white : orange700),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w800,
                    color: selected ? Colors.white : ink,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FoodInventoryCard extends StatelessWidget {
  final Food food;
  final bool pantryMode;
  final bool inPantry;
  final bool selected;
  final int amount;
  final VoidCallback onTap;
  final VoidCallback onToggle;
  final VoidCallback onAdd;
  final VoidCallback onMinus;
  final VoidCallback onPlus;
  final VoidCallback onDelete;

  const _FoodInventoryCard({
    required this.food,
    required this.pantryMode,
    required this.inPantry,
    required this.selected,
    required this.amount,
    required this.onTap,
    required this.onToggle,
    required this.onAdd,
    required this.onMinus,
    required this.onPlus,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(rCard),
        child: Container(
          clipBehavior: Clip.antiAlias,
          decoration: cardDeco(),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              AspectRatio(
                aspectRatio: 1.8,
                child: FoodPhoto(asset: food.image),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.all(11),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              food.name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                          if (pantryMode) ...[
                            IconButton.filledTonal(
                              onPressed: onToggle,
                              tooltip: selected ? '取消选择' : '选中用于做菜',
                              constraints: const BoxConstraints.tightFor(
                                width: 32,
                                height: 32,
                              ),
                              padding: EdgeInsets.zero,
                              icon: Icon(
                                selected
                                    ? Icons.check_circle_rounded
                                    : Icons.radio_button_unchecked_rounded,
                                size: 19,
                                color: selected ? orange700 : muted,
                              ),
                            ),
                            const SizedBox(width: 5),
                            IconButton(
                              onPressed: onDelete,
                              tooltip: '删除${food.name}',
                              constraints: const BoxConstraints.tightFor(
                                width: 32,
                                height: 32,
                              ),
                              padding: EdgeInsets.zero,
                              style: IconButton.styleFrom(
                                backgroundColor: orange100,
                                foregroundColor: orange,
                              ),
                              icon: const Icon(
                                Icons.delete_outline_rounded,
                                size: 18,
                              ),
                            ),
                          ] else
                            _AddFoodButton(added: inPantry, onTap: onAdd),
                        ],
                      ),
                      const SizedBox(height: 7),
                      if (food.tags.isNotEmpty)
                        Wrap(
                          spacing: 5,
                          runSpacing: 5,
                          children: [
                            for (final tag in food.tags.take(2))
                              _Tag(text: tag),
                          ],
                        ),
                      const Spacer(),
                      if (pantryMode)
                        Row(
                          children: [
                            _AmountButton(icon: Icons.remove, onTap: onMinus),
                            Expanded(
                              child: Text(
                                '$amount',
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700,
                                  color: orange700,
                                ),
                              ),
                            ),
                            _AmountButton(icon: Icons.add, onTap: onPlus),
                          ],
                        ),
                      // 食材卡片不再展示星级，底部留白由 Spacer 统一对齐。
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AddFoodButton extends StatelessWidget {
  final bool added;
  final VoidCallback onTap;

  const _AddFoodButton({required this.added, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: added ? '从我的食材中移除' : '添加到我的食材',
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          customBorder: const CircleBorder(),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: added ? orange700 : Colors.white,
              shape: BoxShape.circle,
              border: Border.all(color: added ? orange700 : line),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x22D2601F),
                  blurRadius: 10,
                  offset: Offset(0, 4),
                ),
              ],
            ),
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 160),
              child: Icon(
                added ? Icons.check_rounded : Icons.add_rounded,
                key: ValueKey(added),
                size: 20,
                color: added ? Colors.white : orange700,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _CategoryChip extends StatelessWidget {
  final String category;
  final bool selected;
  final VoidCallback onSelected;

  const _CategoryChip({
    required this.category,
    required this.selected,
    required this.onSelected,
  });

  IconData get _icon => switch (category) {
    '蔬菜' => Icons.grass_rounded,
    '肉蛋' => Icons.egg_alt_rounded,
    '水产' => Icons.set_meal_rounded,
    '豆制品' => Icons.breakfast_dining_rounded,
    _ => Icons.apps_rounded,
  };

  Color get _iconColor => switch (category) {
    '肉蛋' => const Color(0xFFE76543),
    '水产' => const Color(0xFF3587A4),
    '豆制品' => const Color(0xFFC88A2D),
    _ => orange700,
  };

  @override
  Widget build(BuildContext context) {
    return ChoiceChip(
      avatar: Icon(
        selected ? Icons.check_circle_rounded : _icon,
        size: 17,
        color: selected ? orange700 : _iconColor,
      ),
      label: Text(category),
      selected: selected,
      showCheckmark: false,
      selectedColor: orange100,
      backgroundColor: Colors.white,
      side: BorderSide(color: selected ? orange100 : line),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
      labelStyle: TextStyle(
        color: selected ? orange700 : ink,
        fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
        fontSize: 12,
      ),
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 8),
      onSelected: (_) => onSelected(),
    );
  }
}

class _AmountButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;

  const _AmountButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(9),
      child: Container(
        width: 28,
        height: 28,
        decoration: BoxDecoration(
          color: orange50,
          borderRadius: BorderRadius.circular(9),
        ),
        child: Icon(icon, size: 16, color: orange700),
      ),
    );
  }
}

/// 食材详情里的「适合做这些菜」。
///
/// 为什么是一个自己拉数据的 StatefulWidget：
///   列表接口 `/api/recipes` 不返回 ingredients，本地反查一定是 0 条
///   （见 [FoodsPageState.openFoodDetail] 的注释）。真正算好的关联在
///   `/api/foods/{id}` 的 `recommended_recipes` 里，所以要单独拉一次。
///
/// 三种状态都要说实话：
///   加载中 → 转圈；拿到了 → 列出来；没拿到 → 说明「暂时查不到」，
///   **不**拿两道不相干的菜来充数（以前就是这么干的）。
class _FoodRecipeSuggestions extends StatefulWidget {
  final Food food;

  const _FoodRecipeSuggestions({required this.food});

  @override
  State<_FoodRecipeSuggestions> createState() => _FoodRecipeSuggestionsState();
}

class _FoodRecipeSuggestionsState extends State<_FoodRecipeSuggestions> {
  List<Recipe>? _recipes;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    // 后端不在线时不要发请求，直接说查不到 —— 本地假数据里没有这种关联
    if (!BackendStatus.instance.online) {
      if (mounted) setState(() => _failed = true);
      return;
    }
    try {
      final recipes = await BackendApi.instance.fetchFoodRecipes(
        widget.food.id,
      );
      if (!mounted) return;
      setState(() => _recipes = recipes);
    } catch (error) {
      debugPrint('[FoodsPage] 食材推荐菜谱加载失败：$error');
      if (mounted) setState(() => _failed = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final recipes = _recipes;
    if (recipes == null && !_failed) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 18),
        child: Center(
          child: SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      );
    }
    if (recipes == null || recipes.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 14),
        child: Text(
          '暂时查不到用这个食材做的菜谱。可以去「菜谱」页按分类找找，'
          '或者把食材加到「我的食材」再让 AI 助手帮你配。',
          style: TextStyle(fontSize: 13, color: muted, height: 1.7),
        ),
      );
    }

    return Column(
      children: [
        for (final recipe in recipes)
          Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(10),
            decoration: cardDeco(),
            child: Row(
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: SizedBox(
                    width: 82,
                    height: 64,
                    child: DishPhoto(asset: recipe.image),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        recipe.name,
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        recipe.metaLine,
                        style: const TextStyle(fontSize: 12, color: muted),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _DetailSeasonBadge extends StatelessWidget {
  const _DetailSeasonBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: orange100,
        borderRadius: BorderRadius.circular(99),
      ),
      child: const Text(
        '当季推荐',
        style: TextStyle(
          color: orange,
          fontSize: 11,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  final String text;

  const _Tag({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: tagDeco(),
      child: Text(
        text,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        softWrap: false,
        style: const TextStyle(
          fontSize: 10,
          color: orange700,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _EmptyFoods extends StatelessWidget {
  final bool pantryIsEmpty;
  final VoidCallback onBrowse;

  const _EmptyFoods({required this.pantryIsEmpty, required this.onBrowse});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 42),
      decoration: cardDeco(),
      child: Column(
        children: [
          Container(
            width: 58,
            height: 58,
            decoration: const BoxDecoration(
              color: orange100,
              shape: BoxShape.circle,
            ),
            child: Icon(
              pantryIsEmpty
                  ? Icons.add_shopping_cart_rounded
                  : Icons.search_off_rounded,
              size: 29,
              color: orange700,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            pantryIsEmpty ? '我的食材还是空的' : '没有找到匹配的食材',
            style: const TextStyle(color: ink, fontWeight: FontWeight.w800),
          ),
          if (pantryIsEmpty) ...[
            const SizedBox(height: 6),
            const Text(
              '去推荐食材点击右上角 + 添加',
              style: TextStyle(fontSize: 12, color: muted),
            ),
            const SizedBox(height: 14),
            FilledButton.icon(
              onPressed: onBrowse,
              icon: const Icon(Icons.spa_rounded, size: 18),
              label: const Text('去看推荐食材'),
            ),
          ],
        ],
      ),
    );
  }
}
