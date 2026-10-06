// 首页推荐流与 AI 配菜的数据模型。
//
// 这些结构对应后端本次新增的字段：
//   GET  /api/home          → HomeFeed（含 weather / meta / reason / highlights）
//   POST /api/ai/recommend  → AiComposeResult（含 trace / used_foods）
//
// 【为什么不复用 models/content.dart】
// content.dart 里的 Food / Recipe 是「内容实体」，全 App 都在用。
// 这里多出来的是「为什么推荐它」这类**推荐上下文**（理由、命中因素、算法来源），
// 混进实体模型会让详情页、菜谱页也被迫携带一堆用不到的字段。
// 所以单独放一层，需要时再组合。

import 'content.dart';

/// 今天的天气上下文（来自后端，后端取不到实时天气时会标注 estimated）。
class HomeWeather {
  final String? city;
  final String date;

  /// cold / hot / rain / snow / dry / mild / unknown
  final String kind;
  final String description;
  final String advice;
  final double? temperatureC;

  /// live（实时） / estimated（按季节估算） / unknown
  final String source;

  const HomeWeather({
    required this.city,
    required this.date,
    required this.kind,
    required this.description,
    required this.advice,
    required this.source,
    this.temperatureC,
  });

  factory HomeWeather.fromJson(Map<String, dynamic> j) => HomeWeather(
    city: j['city'] as String?,
    date: j['date'] as String? ?? '',
    kind: j['kind'] as String? ?? 'unknown',
    description: j['description'] as String? ?? '',
    advice: j['advice'] as String? ?? '',
    source: j['source'] as String? ?? 'unknown',
    temperatureC: (j['temperature_c'] as num?)?.toDouble(),
  );

  /// 天气图标（按后端给的饮食意图选，而不是按天气码 —— 我们只用得着这个粒度）
  String get emoji => const {
    'cold': '❄️',
    'snow': '🌨️',
    'hot': '☀️',
    'rain': '🌧️',
    'dry': '🍂',
    'mild': '🌤️',
  }[kind] ?? '🌤️';

  /// 来源标签。后端如实标注，前端也如实显示 —— 不假装是实时天气。
  String get sourceLabel => const {
    'live': '实时天气',
    'estimated': '按季节估算',
  }[source] ?? '天气未知';
}

/// 一条「算法 + AI」的动作记录。
class HomeAlgoStep {
  final String step;
  final String detail;
  final int ms;

  const HomeAlgoStep({
    required this.step,
    required this.detail,
    required this.ms,
  });

  factory HomeAlgoStep.fromJson(Map<String, dynamic> j) => HomeAlgoStep(
    step: j['step'] as String? ?? '',
    detail: j['detail'] as String? ?? '',
    ms: (j['ms'] as num?)?.toInt() ?? 0,
  );
}

/// 首页一次推荐的整体结果。
class HomeFeed {
  final String seasonName;
  final int month;

  final List<HomePick<Food>> foods;
  final List<HomePick<Recipe>> recipes;

  final String aiTipTitle;
  final String aiTip;
  final HomeWeather? weather;

  /// ai（真的调了模型）/ cached（命中当天缓存）/ algorithm（没配 AI 或调用失败）
  final String source;
  final String? model;
  final int aiMs;
  final String? cacheKey;
  final int shortlistFoods;
  final int shortlistDishes;
  final List<HomeAlgoStep> steps;

  /// 生成这份推荐时用的日期（后端返回，不是前端本地日期 ——
  /// 否则跨时区时前端会以为「今天的推荐」是昨天的）
  final String date;
  final String region;

  const HomeFeed({
    required this.seasonName,
    required this.month,
    required this.foods,
    required this.recipes,
    required this.aiTipTitle,
    required this.aiTip,
    required this.source,
    required this.date,
    required this.region,
    this.weather,
    this.model,
    this.aiMs = 0,
    this.cacheKey,
    this.shortlistFoods = 0,
    this.shortlistDishes = 0,
    this.steps = const <HomeAlgoStep>[],
  });

  /// 来源说明 —— 界面上如实标注，不把「算法结果」说成「AI 推荐」。
  String get sourceLabel => switch (source) {
    'ai' => '算法 + AI（每日一次）',
    'cached' => '算法 + AI（今日已缓存）',
    _ => '本地算法（AI 未启用）',
  };

  String get weatherLine => weather == null
      ? ''
      : '${weather!.emoji} ${weather!.description} · ${weather!.advice}';
}

/// 带推荐理由的条目（食材 / 菜谱通用）。
class HomePick<T> {
  final T item;
  final String reason;
  final List<String> highlights;
  final double? score;

  const HomePick({
    required this.item,
    required this.reason,
    this.highlights = const <String>[],
    this.score,
  });
}

/// 配菜结果里的一道菜。
class RecipeRecommendation {
  final Recipe recipe;
  final String reason;
  final List<String> highlights;
  final double? score;

  /// 这道菜用到了你已有食材里的哪几样
  final List<String> matchedFoods;

  const RecipeRecommendation({
    required this.recipe,
    required this.reason,
    this.highlights = const <String>[],
    this.score,
    this.matchedFoods = const <String>[],
  });
}

/// AI 配菜的完整结果。
class AiComposeResult {
  final String answer;
  final List<RecipeRecommendation> recommendations;
  final List<AgentStep> trace;

  /// ai / algorithm
  final String source;
  final String? model;
  final List<String> usedFoods;
  final List<String> filteredOut;

  const AiComposeResult({
    required this.answer,
    required this.recommendations,
    this.trace = const <AgentStep>[],
    this.source = 'algorithm',
    this.model,
    this.usedFoods = const <String>[],
    this.filteredOut = const <String>[],
  });

  bool get fromAi => source == 'ai';
}
