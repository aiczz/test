// 真后端的业务接口。
//
// 只有在 `BackendStatus.online` 为 true 时才会被调用；任何失败都向上抛，
// 由 ContentStore 统一降级到本地假数据 —— 所以线上 PWA（没有后端）
// 和本地演示（起了后端）共用同一套界面代码。
//
// 字段映射集中在 _foodFromJson / _recipeFromJson 两个函数里：
// 后端按说明书的字段名返回（image / duration_minutes / servings），
// 前端模型用的是自己的字段名（image / time / people）。

import 'package:dio/dio.dart';

import '../models/content.dart';
import 'api_config.dart';
import 'auth_store.dart';

/// 前端分类（中文）→ 后端分类（说明书 §7.3 的英文枚举）
const Map<String, String> _categoryToBackend = <String, String>{
  '蔬菜': 'vegetable',
  '水果': 'fruit',
  '肉蛋': 'meat_egg',
  '水产': 'aquatic',
  '豆制品': 'soy',
  '主食': 'grain',
  '调味': 'seasoning',
};

/// 后端分类（英文）→ 前端分类（中文）
const Map<String, String> _categoryFromBackend = <String, String>{
  'vegetable': '蔬菜',
  'fruit': '水果',
  'meat_egg': '肉蛋',
  'aquatic': '水产',
  'soy': '豆制品',
  'grain': '主食',
  'seasoning': '调味',
};

String? toBackendCategory(String? chinese) =>
    chinese == null ? null : _categoryToBackend[chinese];

String fromBackendCategory(String? english) =>
    _categoryFromBackend[english] ?? (english ?? '其他');

class BackendApi {
  BackendApi._();

  static final BackendApi instance = BackendApi._();

  Dio get _dio => Dio(
    BaseOptions(
      baseUrl: BackendStatus.instance.apiBase,
      connectTimeout: const Duration(seconds: 6),
      receiveTimeout: const Duration(seconds: 10),
      contentType: 'application/json; charset=utf-8',
    ),
  );

  Options get _auth =>
      Options(headers: Map<String, String>.from(AuthStore.instance.authHeaders));

  // ---------------------------------------------------------------- 食材

  /// GET /api/foods（说明书 §10.1）
  Future<List<Food>> fetchFoods({
    String? category,
    String? keyword,
    int pageSize = 50,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/api/foods',
      queryParameters: <String, dynamic>{
        if (category != null && category != '全部')
          'category': toBackendCategory(category) ?? category,
        if (keyword != null && keyword.trim().isNotEmpty)
          'keyword': keyword.trim(),
        'page_size': pageSize,
      },
    );
    final items = (res.data?['items'] as List?) ?? const <dynamic>[];
    return items
        .whereType<Map<String, dynamic>>()
        .map(_foodFromJson)
        .toList();
  }

  /// GET /api/foods/seasonal（说明书 §10.2）
  Future<List<Food>> fetchSeasonalFoods({int month = 9, int limit = 10}) async {
    final res = await _dio.get<List<dynamic>>(
      '/api/foods/seasonal',
      queryParameters: <String, dynamic>{'month': month, 'limit': limit},
    );
    return (res.data ?? const <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(_foodFromJson)
        .toList();
  }

  // ---------------------------------------------------------------- 菜谱

  /// GET /api/recipes（说明书 §11.1）
  Future<List<Recipe>> fetchRecipes({
    int? maxDuration,
    String? season,
    int pageSize = 50,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/api/recipes',
      queryParameters: <String, dynamic>{
        'max_duration': ?maxDuration,
        if (season != null && season.isNotEmpty) 'season': season,
        'page_size': pageSize,
      },
    );
    final items = (res.data?['items'] as List?) ?? const <dynamic>[];
    return items
        .whereType<Map<String, dynamic>>()
        .map(_recipeFromJson)
        .toList();
  }

  // ---------------------------------------------------------------- 现有食材

  /// GET /api/my-foods —— 需要登录
  Future<List<MyFoodEntry>> fetchMyFoods() async {
    final res = await _dio.get<List<dynamic>>('/api/my-foods', options: _auth);
    return (res.data ?? const <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(
          (json) => MyFoodEntry(
            id: json['id'] as int? ?? 0,
            foodId: json['food_id'] as int?,
            name: json['name'] as String? ?? '',
            amount: (json['amount'] as num?)?.toDouble() ?? 1,
            unit: json['unit'] as String? ?? '份',
            expireHint: json['expire_hint'] as String?,
          ),
        )
        .toList();
  }

  /// POST /api/my-foods —— 需要登录
  Future<void> addMyFood({
    required int foodId,
    double amount = 1,
    String unit = '份',
  }) async {
    await _dio.post<Map<String, dynamic>>(
      '/api/my-foods',
      data: <String, dynamic>{'food_id': foodId, 'amount': amount, 'unit': unit},
      options: _auth,
    );
  }

  /// DELETE /api/my-foods/{id} —— 需要登录
  Future<void> removeMyFood(int itemId) async {
    await _dio.delete<void>('/api/my-foods/$itemId', options: _auth);
  }

  // ---------------------------------------------------------------- AI

  /// POST /api/ai/chat（说明书 §20）。登录可选。
  Future<AiChatResult> chat(String message) async {
    final res = await _dio.post<Map<String, dynamic>>(
      '/api/ai/chat',
      data: <String, dynamic>{'message': message},
      options: _auth,
    );
    final data = res.data ?? const <String, dynamic>{};
    final recipes = (data['recipes'] as List?) ?? const <dynamic>[];
    return AiChatResult(
      answer: data['answer'] as String? ?? '',
      intent: data['intent'] as String? ?? 'general',
      toolsUsed: ((data['tools_used'] as List?) ?? const <dynamic>[])
          .map((e) => e.toString())
          .toList(),
      recipes: recipes
          .whereType<Map<String, dynamic>>()
          .map(_recipeFromJson)
          .toList(),
    );
  }

  // ---------------------------------------------------------------- 映射

  static Food _foodFromJson(Map<String, dynamic> json) => Food(
    // 前端模型用 String id，后端是 int —— 统一转成字符串
    id: '${json['id']}',
    name: json['name'] as String? ?? '',
    image: json['image'] as String? ?? '',
    category: fromBackendCategory(json['category'] as String?),
    tags: ((json['tags'] as List?) ?? const <dynamic>[])
        .map((e) => e.toString())
        .toList(),
  );

  static Recipe _recipeFromJson(Map<String, dynamic> json) => Recipe(
    id: '${json['id']}',
    name: json['name'] as String? ?? '',
    image: json['image'] as String? ?? '',
    desc: json['description'] as String? ?? '',
    // 后端给的是分钟数，前端展示用「60分钟」这种文案
    time: '${json['duration_minutes'] ?? 0}分钟',
    people: json['servings'] as String? ?? '',
    tags: ((json['tags'] as List?) ?? const <dynamic>[])
        .map((e) => e.toString())
        .toList(),
    difficulty: json['difficulty'] as String? ?? '简单',
    ingredients: ((json['ingredients'] as List?) ?? const <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(_ingredientText)
        .toList(),
    steps: ((json['steps'] as List?) ?? const <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map((s) => s['description']?.toString() ?? '')
        .where((text) => text.isNotEmpty)
        .toList(),
  );

  /// 后端配料是 {name, amount, unit}，前端的 ingredients 是「莲藕 1节」这种文案
  static String _ingredientText(Map<String, dynamic> json) {
    final name = json['name']?.toString() ?? '';
    final amount = json['amount']?.toString() ?? '';
    final unit = json['unit']?.toString() ?? '';
    final quantity = '$amount$unit';
    return quantity.isEmpty ? name : '$name $quantity';
  }
}

/// 后端「我的食材」一条记录
class MyFoodEntry {
  final int id;
  final int? foodId;
  final String name;
  final double amount;
  final String unit;
  final String? expireHint;

  const MyFoodEntry({
    required this.id,
    this.foodId,
    required this.name,
    required this.amount,
    required this.unit,
    this.expireHint,
  });
}

/// 后端 AI 回复
class AiChatResult {
  final String answer;
  final String intent;
  final List<String> toolsUsed;
  final List<Recipe> recipes;

  const AiChatResult({
    required this.answer,
    required this.intent,
    this.toolsUsed = const <String>[],
    this.recipes = const <Recipe>[],
  });
}
