import 'dart:async';

import 'package:flutter/material.dart';

import '../models/content.dart';
import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../services/backend_api.dart';
import '../services/content_store.dart';
import '../theme.dart';

/// =====================================================================
/// 菜谱页 —— 对应队友原型 `recipesPage()`
///
/// 搜索 + 分类筛选 + 收藏 + 菜谱详情弹层
/// =====================================================================

const _categories = <String>['全部', '快手菜', '汤品', '低脂', '家常', '秋季推荐'];

class RecipesPage extends StatefulWidget {
  const RecipesPage({super.key});

  @override
  State<RecipesPage> createState() => _RecipesPageState();
}

class _RecipesPageState extends State<RecipesPage> {
  String _category = '全部';
  String _query = '';
  final TextEditingController _search = TextEditingController();

  /// 收藏。
  /// ⚠️ 以前初始值是 {'soup'} —— 相当于「默认已经收藏了莲藕排骨汤」，
  ///    一个假状态。现在初始为空；收藏接口后端已经有了，
  ///    登录后可以接上（见 back/README.md 的 /api/favorites）。
  final Set<String> _favorites = <String>{};

  bool get _canSyncFavorites =>
      BackendStatus.instance.online && AuthStore.instance.isLoggedIn;

  @override
  void initState() {
    super.initState();
    unawaited(_loadFavorites());
  }

  Future<void> _loadFavorites() async {
    if (!_canSyncFavorites) return;
    try {
      final ids = await BackendApi.instance.fetchFavoriteIds();
      if (!mounted) return;
      setState(() {
        _favorites
          ..clear()
          ..addAll(ids);
      });
    } catch (error) {
      debugPrint('[RecipesPage] 收藏加载失败：$error');
    }
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  List<Recipe> get _visible {
    Iterable<Recipe> list = ContentStore.instance.recipes;

    if (_category != '全部') {
      // 「汤品」不是标签，用 id 兜一下（与原型逻辑一致）
      list = list.where(
        (r) =>
            r.tags.contains(_category) || (_category == '汤品' && r.id == 'soup'),
      );
    }

    if (_query.isNotEmpty) {
      final q = _query.toLowerCase();
      list = list.where(
        (r) => '${r.name}${r.desc}${r.tags.join()}'.toLowerCase().contains(q),
      );
    }

    return list.toList();
  }

  Future<void> _toggleFavorite(String id) async {
    final adding = !_favorites.contains(id);
    setState(() {
      if (adding) {
        _favorites.add(id);
      } else {
        _favorites.remove(id);
      }
    });
    if (!_canSyncFavorites) return;
    try {
      await BackendApi.instance.setFavorite(id, favorite: adding);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        if (adding) {
          _favorites.remove(id);
        } else {
          _favorites.add(id);
        }
      });
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('收藏同步失败，请稍后重试')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final list = _visible;

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
          children: [
            // ---- 标题区 ----
            Container(
              clipBehavior: Clip.antiAlias,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFFEDF7E8), Color(0xFFFFF3DF)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(rBlock),
                boxShadow: cardShadow,
              ),
              child: Stack(
                children: [
                  Positioned(
                    left: -35,
                    bottom: -55,
                    child: Container(
                      width: 130,
                      height: 130,
                      decoration: const BoxDecoration(
                        color: Color(0x26FFFFFF),
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 18, 16, 18),
                    child: Row(
                      children: [
                        const Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    Icons.local_dining_rounded,
                                    size: 15,
                                    color: green700,
                                  ),
                                  SizedBox(width: 6),
                                  Text(
                                    '时令菜谱',
                                    style: TextStyle(
                                      fontSize: 11.5,
                                      fontWeight: FontWeight.w800,
                                      color: green700,
                                      letterSpacing: .4,
                                    ),
                                  ),
                                ],
                              ),
                              SizedBox(height: 9),
                              Text(
                                '家常菜谱',
                                style: TextStyle(
                                  fontSize: 29,
                                  fontWeight: FontWeight.w900,
                                  color: green900,
                                  height: 1.05,
                                  letterSpacing: -1,
                                ),
                              ),
                              SizedBox(height: 8),
                              Text(
                                '应季食材，简单好做\n把每一餐吃得温暖。',
                                style: TextStyle(
                                  fontSize: 12.5,
                                  color: muted,
                                  height: 1.55,
                                ),
                              ),
                              SizedBox(height: 12),
                              Wrap(
                                spacing: 6,
                                runSpacing: 6,
                                children: [
                                  _RecipeHeaderTag(
                                    icon: Icons.eco_outlined,
                                    text: '当季',
                                  ),
                                  _RecipeHeaderTag(
                                    icon: Icons.schedule_outlined,
                                    text: '好做',
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 12),
                        Container(
                          width: 126,
                          height: 150,
                          clipBehavior: Clip.antiAlias,
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(22),
                            border: Border.all(
                              color: Colors.white.withValues(alpha: .9),
                              width: 3,
                            ),
                            boxShadow: const [
                              BoxShadow(
                                color: Color(0x2A6A5A36),
                                blurRadius: 16,
                                offset: Offset(0, 7),
                              ),
                            ],
                          ),
                          child: Stack(
                            fit: StackFit.expand,
                            children: [
                              Image.asset(
                                'assets/images/tomato-egg.jpg',
                                fit: BoxFit.cover,
                                filterQuality: FilterQuality.high,
                              ),
                              const DecoratedBox(
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    begin: Alignment.topCenter,
                                    end: Alignment.bottomCenter,
                                    colors: [
                                      Colors.transparent,
                                      Color(0xB8122F20),
                                    ],
                                    stops: [.5, 1],
                                  ),
                                ),
                              ),
                              const Positioned(
                                left: 10,
                                right: 10,
                                bottom: 10,
                                child: Text(
                                  '今天也要\n好好吃饭',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 12.5,
                                    height: 1.25,
                                    fontWeight: FontWeight.w900,
                                  ),
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
            const SizedBox(height: 16),

            // ---- 搜索框 ----
            TextField(
              controller: _search,
              onChanged: (v) => setState(() => _query = v.trim()),
              decoration: InputDecoration(
                hintText: '搜索菜名或食材',
                hintStyle: const TextStyle(fontSize: 14, color: muted),
                prefixIcon: const Icon(Icons.search, size: 20, color: muted),
                filled: true,
                fillColor: Colors.white,
                contentPadding: const EdgeInsets.symmetric(vertical: 14),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(16),
                  borderSide: const BorderSide(color: line),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(16),
                  borderSide: const BorderSide(color: line),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(16),
                  borderSide: const BorderSide(color: green600, width: 1.5),
                ),
              ),
            ),
            const SizedBox(height: 14),

            // ---- 分类 chips ----
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  for (final c in _categories) ...[
                    _CategoryChip(
                      label: c,
                      active: _category == c,
                      onTap: () => setState(() => _category = c),
                    ),
                    const SizedBox(width: 8),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 20),

            // ---- 列表标题 ----
            Row(
              children: [
                Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: green100,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.eco, size: 18, color: green700),
                ),
                const SizedBox(width: 10),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _category == '全部' ? '秋季推荐' : _category,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                        color: ink,
                      ),
                    ),
                    const SizedBox(height: 2),
                    const Text(
                      '时令鲜味 · 家常好做',
                      style: TextStyle(fontSize: 12, color: muted),
                    ),
                  ],
                ),
                const Spacer(),
                Text(
                  '${list.length} 道',
                  style: const TextStyle(fontSize: 12, color: muted),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // ---- 菜谱列表 ----
            if (list.isEmpty)
              Container(
                padding: const EdgeInsets.symmetric(vertical: 38),
                alignment: Alignment.center,
                child: Column(
                  children: [
                    const Icon(Icons.search_off, size: 36, color: muted),
                    const SizedBox(height: 12),
                    Text(
                      _query.isEmpty
                          ? '「$_category」下面还没有菜谱'
                          : '没有找到和「$_query」匹配的菜谱',
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 13, color: muted),
                    ),
                    const SizedBox(height: 10),
                    // 有筛选条件时给一个「一键回到全部」——
                    // 比以前只说一句「没有找到」强，用户不用自己猜怎么退出去
                    TextButton.icon(
                      onPressed: () => setState(() {
                        _category = '全部';
                        _query = '';
                        _search.clear();
                      }),
                      icon: const Icon(Icons.refresh, size: 16),
                      label: const Text('清空筛选，看全部菜谱'),
                      style: TextButton.styleFrom(
                        foregroundColor: green700,
                        textStyle: const TextStyle(
                          fontSize: 12.5,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
              )
            else
              for (final r in list) ...[
                _RecipeListCard(
                  recipe: r,
                  favorite: _favorites.contains(r.id),
                  onFavorite: () => unawaited(_toggleFavorite(r.id)),
                  onOpen: () => openRecipeDetail(context, r),
                ),
                const SizedBox(height: 12),
              ],
          ],
        ),
      ),
    );
  }
}

class _RecipeHeaderTag extends StatelessWidget {
  final IconData icon;
  final String text;

  const _RecipeHeaderTag({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: .72),
        borderRadius: BorderRadius.circular(99),
        border: Border.all(color: Colors.white.withValues(alpha: .9)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: green700),
          const SizedBox(width: 4),
          Text(
            text,
            style: const TextStyle(
              fontSize: 10.5,
              color: green700,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// 分类 chip
// =====================================================================

class _CategoryChip extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback onTap;

  const _CategoryChip({
    required this.label,
    required this.active,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 9),
        decoration: BoxDecoration(
          color: active ? green700 : Colors.white,
          border: Border.all(color: active ? green700 : line),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: active ? FontWeight.w700 : FontWeight.w500,
            color: active ? Colors.white : const Color(0xFF435047),
          ),
        ),
      ),
    );
  }
}

// =====================================================================
// 菜谱列表卡片（横向，带收藏按钮）
// =====================================================================

class _RecipeListCard extends StatelessWidget {
  final Recipe recipe;
  final bool favorite;
  final VoidCallback onFavorite;
  final VoidCallback onOpen;

  const _RecipeListCard({
    required this.recipe,
    required this.favorite,
    required this.onFavorite,
    required this.onOpen,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(rCard),
      onTap: onOpen,
      child: Container(
        height: 136,
        clipBehavior: Clip.antiAlias,
        decoration: cardDeco(),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              width: 116,
              child: Image.asset(
                recipe.image,
                fit: BoxFit.cover,
                filterQuality: FilterQuality.high,
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 4, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text(
                            recipe.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w800,
                              color: ink,
                            ),
                          ),
                        ),
                        IconButton(
                          onPressed: onFavorite,
                          iconSize: 18,
                          visualDensity: VisualDensity.compact,
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(
                            minWidth: 32,
                            minHeight: 32,
                          ),
                          icon: Icon(
                            favorite ? Icons.favorite : Icons.favorite_border,
                            color: favorite ? orange : muted,
                          ),
                        ),
                      ],
                    ),
                    Text(
                      recipe.desc,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12, color: muted),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 5,
                      runSpacing: 5,
                      children: [
                        for (var i = 0; i < recipe.tags.length && i < 2; i++)
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 7,
                              vertical: 3,
                            ),
                            decoration: tagDeco(
                              bg: i == 0 ? orange100 : green100,
                            ),
                            child: Text(
                              recipe.tags[i],
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                                color: i == 0 ? orange : green700,
                              ),
                            ),
                          ),
                      ],
                    ),
                    const Spacer(),
                    Row(
                      children: [
                        const Icon(Icons.schedule, size: 12, color: muted),
                        const SizedBox(width: 3),
                        Text(
                          recipe.time,
                          style: const TextStyle(fontSize: 11, color: muted),
                        ),
                        const SizedBox(width: 10),
                        const Icon(
                          Icons.people_outline,
                          size: 12,
                          color: muted,
                        ),
                        const SizedBox(width: 3),
                        Text(
                          recipe.people,
                          style: const TextStyle(fontSize: 11, color: muted),
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
    );
  }
}

// =====================================================================
// 菜谱详情弹层
// =====================================================================

/// 打开菜谱详情弹层。
///
/// 公开函数 —— 菜单页的菜品格子也走这里，
/// 保证「从菜谱页点」和「从菜单点」看到的是同一个详情。
void openRecipeDetail(BuildContext context, Recipe recipe) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.white,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(rBlock)),
    ),
    builder: (_) => _RecipeDetailLoader(recipe: recipe),
  );
}

class _RecipeDetailLoader extends StatefulWidget {
  final Recipe recipe;

  const _RecipeDetailLoader({required this.recipe});

  @override
  State<_RecipeDetailLoader> createState() => _RecipeDetailLoaderState();
}

class _RecipeDetailLoaderState extends State<_RecipeDetailLoader> {
  late Future<Recipe> _future = _load();

  Future<Recipe> _load() {
    if (!ContentStore.instance.fromBackend ||
        int.tryParse(widget.recipe.id) == null) {
      return Future<Recipe>.value(widget.recipe);
    }
    return BackendApi.instance.fetchRecipeDetail(widget.recipe.id);
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Recipe>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.hasData) {
          return _RecipeDetailSheet(recipe: snapshot.data!);
        }
        if (snapshot.hasError) {
          return SizedBox(
            height: 420,
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.cloud_off_outlined, color: muted, size: 34),
                  const SizedBox(height: 12),
                  const Text('菜谱详情加载失败', style: TextStyle(color: ink)),
                  const SizedBox(height: 10),
                  TextButton.icon(
                    onPressed: () => setState(() => _future = _load()),
                    icon: const Icon(Icons.refresh),
                    label: const Text('重新加载'),
                  ),
                ],
              ),
            ),
          );
        }
        return const SizedBox(
          height: 420,
          child: Center(child: CircularProgressIndicator(color: green700)),
        );
      },
    );
  }
}

class _RecipeDetailSheet extends StatelessWidget {
  final Recipe recipe;

  const _RecipeDetailSheet({required this.recipe});

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.9,
      maxChildSize: 0.95,
      minChildSize: 0.5,
      builder: (context, controller) {
        return ListView(
          controller: controller,
          padding: EdgeInsets.zero,
          children: [
            // ---- 大图 + 关闭按钮 ----
            Stack(
              children: [
                SizedBox(
                  height: 200,
                  width: double.infinity,
                  child: Image.asset(
                    recipe.image,
                    fit: BoxFit.cover,
                    filterQuality: FilterQuality.high,
                  ),
                ),
                Positioned(
                  top: 12,
                  right: 12,
                  child: Material(
                    color: Colors.white.withAlpha(235),
                    shape: const CircleBorder(),
                    child: InkWell(
                      customBorder: const CircleBorder(),
                      onTap: () => Navigator.pop(context),
                      child: const SizedBox(
                        width: 36,
                        height: 36,
                        child: Icon(Icons.close, size: 18, color: ink),
                      ),
                    ),
                  ),
                ),
              ],
            ),

            Padding(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '秋季时令 · 家常好味',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: green700,
                      letterSpacing: 0.5,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    recipe.name,
                    style: const TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.w900,
                      color: ink,
                      height: 1.15,
                      letterSpacing: -0.5,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '${recipe.desc}。选用当季食材，味道清甜自然，适合一家人慢慢享用。',
                    style: const TextStyle(
                      fontSize: 13.5,
                      color: muted,
                      height: 1.7,
                    ),
                  ),
                  const SizedBox(height: 14),

                  // ---- 标签 ----
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (var i = 0; i < recipe.tags.length; i++)
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 9,
                            vertical: 5,
                          ),
                          decoration: tagDeco(
                            bg: i == 0 ? orange100 : green100,
                          ),
                          child: Text(
                            recipe.tags[i],
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: i == 0 ? orange : green700,
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 18),

                  // ---- 三个事实 ----
                  Row(
                    children: [
                      _Fact(icon: Icons.schedule, label: recipe.time),
                      const SizedBox(width: 8),
                      _Fact(icon: Icons.people_outline, label: recipe.people),
                      const SizedBox(width: 8),
                      _Fact(
                        icon: Icons.local_fire_department,
                        label: recipe.difficulty,
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),

                  // ---- 所需食材 ----
                  if (recipe.ingredients.isNotEmpty) ...[
                    const _SectionTitle(text: '所需食材'),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final ing in recipe.ingredients)
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 11,
                              vertical: 8,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF4F6F3),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Text(
                              ing,
                              style: const TextStyle(
                                fontSize: 12.5,
                                color: ink,
                              ),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 24),
                  ],

                  // ---- 做法步骤 ----
                  if (recipe.steps.isNotEmpty) ...[
                    const _SectionTitle(text: '做法步骤'),
                    const SizedBox(height: 12),
                    for (var i = 0; i < recipe.steps.length; i++)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 14),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              width: 26,
                              height: 26,
                              alignment: Alignment.center,
                              decoration: const BoxDecoration(
                                color: Color(0xFF77AD4C),
                                shape: BoxShape.circle,
                              ),
                              child: Text(
                                '${i + 1}',
                                style: const TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w800,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Padding(
                                padding: const EdgeInsets.only(top: 3),
                                child: Text(
                                  recipe.steps[i],
                                  style: const TextStyle(
                                    fontSize: 13.5,
                                    color: ink,
                                    height: 1.7,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    const SizedBox(height: 10),
                  ],

                  // ---- 底部操作 ----
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: () {
                            Navigator.pop(context);
                            _snack(context, '已加入今日菜单');
                          },
                          style: OutlinedButton.styleFrom(
                            side: const BorderSide(color: Color(0xFFCFE3C8)),
                            padding: const EdgeInsets.symmetric(vertical: 14),
                            shape: const StadiumBorder(),
                          ),
                          child: const Text(
                            '加入今日菜单',
                            style: TextStyle(
                              color: green700,
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: FilledButton(
                          onPressed: () {
                            Navigator.pop(context);
                            _snack(context, '已加入购物清单');
                          },
                          style: FilledButton.styleFrom(
                            backgroundColor: orange,
                            padding: const EdgeInsets.symmetric(vertical: 14),
                            shape: const StadiumBorder(),
                          ),
                          child: const Text(
                            '加入购物清单',
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String text;

  const _SectionTitle({required this.text});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w800,
        color: ink,
      ),
    );
  }
}

class _Fact extends StatelessWidget {
  final IconData icon;
  final String label;

  const _Fact({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 13),
        decoration: BoxDecoration(
          color: green50,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          children: [
            Icon(icon, size: 17, color: green700),
            const SizedBox(height: 6),
            Text(
              label,
              style: const TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
                color: ink,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

void _snack(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(message),
      duration: const Duration(milliseconds: 1400),
      behavior: SnackBarBehavior.floating,
      backgroundColor: const Color(0xFF163A26),
      shape: const StadiumBorder(),
    ),
  );
}
