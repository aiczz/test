import 'package:flutter/material.dart';

import '../data/mock.dart';
import '../models/content.dart';
import '../theme.dart';

/// 食材页：时令浏览 + 家中库存 + 选中食材交给 AI。
class FoodsPage extends StatefulWidget {
  final ValueChanged<List<String>> onAskAi;

  const FoodsPage({super.key, required this.onAskAi});

  @override
  State<FoodsPage> createState() => _FoodsPageState();
}

class _FoodsPageState extends State<FoodsPage> {
  final TextEditingController _search = TextEditingController();
  final List<Food> _pantry = List<Food>.from(mockFoods);
  final Set<String> _selected = <String>{'tomato', 'egg'};
  final Map<String, int> _amounts = <String, int>{
    for (final food in mockFoods) food.id: 1,
  };
  String _category = '全部';
  bool _showPantry = false;

  static const _categories = <String>['全部', '蔬菜', '肉蛋', '水产', '豆制品'];

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  List<Food> get _visibleFoods {
    final source = _showPantry ? _pantry : mockFoods;
    final query = _search.text.trim().toLowerCase();
    return source.where((food) {
      final categoryOk = _category == '全部' || food.category == _category;
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
    _toast('已从现有食材中移除${food.name}');
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
                    image: 'assets/images/bokchoy.jpg',
                    category: category,
                    qty: '1份',
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
    _toast('已添加${result.name}');
  }

  void _showFoodDetail(Food food) {
    final matched = mockRecipes.where(
      (recipe) => recipe.ingredients.any((item) => item.contains(food.name)),
    );
    final suggestions = matched.isEmpty ? mockRecipes.take(2) : matched;
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
                  child: ColoredBox(
                    color: const Color(0xFFFFF8EC),
                    child: Image.asset(
                      food.image,
                      fit: BoxFit.contain,
                      alignment: Alignment.center,
                      filterQuality: FilterQuality.high,
                    ),
                  ),
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
                        color: green900,
                      ),
                    ),
                  ),
                  const _SeasonBadge(),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                '${food.name}正值当季，口感更鲜、运输距离更短。适合安排进本周菜单，也可以优先消耗家中库存。',
                style: const TextStyle(fontSize: 14, color: muted, height: 1.7),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final tag in food.tags) _Tag(text: tag),
                  const _Tag(text: '应季指数 92'),
                ],
              ),
              const SizedBox(height: 24),
              const Text(
                '适合做这些菜',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 12),
              for (final recipe in suggestions)
                Container(
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.all(10),
                  decoration: cardDeco(),
                  child: Row(
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(12),
                        child: Image.asset(
                          recipe.image,
                          width: 82,
                          height: 64,
                          fit: BoxFit.cover,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              recipe.name,
                              style: const TextStyle(
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              '${recipe.time} · ${recipe.people}',
                              style: const TextStyle(
                                fontSize: 12,
                                color: muted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
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
        backgroundColor: const Color(0xFF163A26),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final foods = _visibleFoods;
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
                    onChanged: (value) => setState(() => _showPantry = value),
                    onAdd: _addFood,
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _search,
                    onChanged: (_) => setState(() {}),
                    decoration: InputDecoration(
                      hintText: '搜索食材或营养特点',
                      prefixIcon: const Icon(Icons.search),
                      suffixIcon: _search.text.isEmpty
                          ? null
                          : IconButton(
                              onPressed: () {
                                _search.clear();
                                setState(() {});
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
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: [
                        for (final category in _categories) ...[
                          ChoiceChip(
                            label: Text(category),
                            selected: _category == category,
                            selectedColor: green100,
                            labelStyle: TextStyle(
                              color: _category == category ? green700 : muted,
                              fontWeight: _category == category
                                  ? FontWeight.w700
                                  : FontWeight.w500,
                            ),
                            onSelected: (_) =>
                                setState(() => _category = category),
                          ),
                          const SizedBox(width: 7),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 22),
                  Row(
                    children: [
                      Icon(
                        _showPantry ? Icons.kitchen : Icons.eco,
                        color: green700,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        _showPantry ? '我家的食材' : '秋季时令食材',
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
                    const _EmptyFoods()
                  else
                    GridView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: foods.length,
                      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: 2,
                        crossAxisSpacing: 12,
                        mainAxisSpacing: 12,
                        childAspectRatio: _showPantry ? 0.78 : 0.88,
                      ),
                      itemBuilder: (context, index) {
                        final food = foods[index];
                        return _FoodInventoryCard(
                          food: food,
                          pantryMode: _showPantry,
                          selected: _selected.contains(food.id),
                          amount: _amounts[food.id] ?? 1,
                          onTap: () => _showFoodDetail(food),
                          onToggle: () => _toggleSelected(food),
                          onMinus: () => _changeAmount(food, -1),
                          onPlus: () => _changeAmount(food, 1),
                          onDelete: () => _removeFood(food),
                        );
                      },
                    ),
                  if (_showPantry) ...[
                    const SizedBox(height: 14),
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: green50,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: const Row(
                        children: [
                          Icon(Icons.lightbulb_outline, color: green700),
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
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFE7F5E2), Color(0xFFFFF1D9)],
        ),
        borderRadius: BorderRadius.circular(rBlock),
        boxShadow: cardShadow,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            showPantry ? '我家的食材' : '时令食材',
            style: const TextStyle(
              color: green900,
              fontSize: 28,
              fontWeight: FontWeight.w900,
              letterSpacing: -1,
            ),
          ),
          const SizedBox(height: 5),
          Text(
            showPantry ? '记录家中库存，减少浪费' : '应季鲜美，营养更自然',
            style: const TextStyle(color: muted, fontSize: 13),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: SegmentedButton<bool>(
                  segments: [
                    const ButtonSegment(
                      value: false,
                      icon: Icon(Icons.eco_outlined),
                      label: Text('推荐'),
                    ),
                    ButtonSegment(
                      value: true,
                      icon: const Icon(Icons.kitchen_outlined),
                      label: Text('我的 $pantryCount'),
                    ),
                  ],
                  selected: <bool>{showPantry},
                  onSelectionChanged: (value) => onChanged(value.first),
                ),
              ),
              if (showPantry) ...[
                const SizedBox(width: 8),
                IconButton.filled(
                  onPressed: onAdd,
                  tooltip: '手动添加食材',
                  icon: const Icon(Icons.add),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _FoodInventoryCard extends StatelessWidget {
  final Food food;
  final bool pantryMode;
  final bool selected;
  final int amount;
  final VoidCallback onTap;
  final VoidCallback onToggle;
  final VoidCallback onMinus;
  final VoidCallback onPlus;
  final VoidCallback onDelete;

  const _FoodInventoryCard({
    required this.food,
    required this.pantryMode,
    required this.selected,
    required this.amount,
    required this.onTap,
    required this.onToggle,
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
              Stack(
                children: [
                  AspectRatio(
                    aspectRatio: 1.8,
                    child: ColoredBox(
                      color: const Color(0xFFFFF8EC),
                      child: Image.asset(
                        food.image,
                        fit: BoxFit.contain,
                        alignment: Alignment.center,
                        filterQuality: FilterQuality.high,
                      ),
                    ),
                  ),
                  Positioned(
                    right: 7,
                    top: 7,
                    child: pantryMode
                        ? IconButton.filledTonal(
                            onPressed: onToggle,
                            tooltip: selected ? '取消选择' : '选中用于做菜',
                            constraints: const BoxConstraints.tightFor(
                              width: 34,
                              height: 34,
                            ),
                            padding: EdgeInsets.zero,
                            icon: Icon(
                              selected
                                  ? Icons.check_circle
                                  : Icons.radio_button_unchecked,
                              size: 20,
                              color: selected ? green700 : muted,
                            ),
                          )
                        : const _SeasonBadge(),
                  ),
                ],
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
                              style: const TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                          if (pantryMode)
                            InkWell(
                              onTap: onDelete,
                              child: const Icon(
                                Icons.delete_outline,
                                size: 19,
                                color: muted,
                              ),
                            ),
                        ],
                      ),
                      const SizedBox(height: 7),
                      if (food.tags.isNotEmpty) _Tag(text: food.tags.first),
                      const Spacer(),
                      if (pantryMode)
                        Row(
                          children: [
                            _AmountButton(icon: Icons.remove, onTap: onMinus),
                            Expanded(
                              child: Text(
                                '$amount ${food.qty}',
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700,
                                  color: green700,
                                ),
                              ),
                            ),
                            _AmountButton(icon: Icons.add, onTap: onPlus),
                          ],
                        )
                      else
                        Row(
                          children: const [
                            Icon(
                              Icons.star,
                              color: Color(0xFFFFB12B),
                              size: 16,
                            ),
                            Icon(
                              Icons.star,
                              color: Color(0xFFFFB12B),
                              size: 16,
                            ),
                            Icon(
                              Icons.star,
                              color: Color(0xFFFFB12B),
                              size: 16,
                            ),
                            Icon(
                              Icons.star,
                              color: Color(0xFFFFB12B),
                              size: 16,
                            ),
                            Icon(
                              Icons.star_half,
                              color: Color(0xFFFFB12B),
                              size: 16,
                            ),
                          ],
                        ),
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
          color: green50,
          borderRadius: BorderRadius.circular(9),
        ),
        child: Icon(icon, size: 16, color: green700),
      ),
    );
  }
}

class _SeasonBadge extends StatelessWidget {
  const _SeasonBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: orange,
        borderRadius: BorderRadius.circular(99),
      ),
      child: const Text(
        '当季',
        style: TextStyle(
          color: Colors.white,
          fontSize: 10,
          fontWeight: FontWeight.w700,
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
        style: const TextStyle(
          fontSize: 10,
          color: green700,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _EmptyFoods extends StatelessWidget {
  const _EmptyFoods();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 42),
      decoration: cardDeco(),
      child: const Column(
        children: [
          Icon(Icons.search_off, size: 42, color: muted),
          SizedBox(height: 10),
          Text('没有找到匹配的食材', style: TextStyle(color: muted)),
        ],
      ),
    );
  }
}
