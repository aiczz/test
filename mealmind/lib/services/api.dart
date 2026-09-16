import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/services.dart' show rootBundle;

import '../models/plan.dart';

/// =====================================================================
/// 接口层
///
/// ★ 后端接口好了之后，把 useMock 改成 false 就行 —— 只改这一行。
///   前端所有页面都已经按真接口的格式在跑，不需要动别的代码。
///
/// 技术选型对齐队友 `front指南.txt` 第 27 节：用 **Dio**（不是 http 包）。
///
/// ⚠️ 端点路径对齐第 25 节的约定：
///       POST /api/menu/plan      多日菜单生成
///       GET  /api/shopping-list  购物清单
///    但响应体在原契约（docs/接口契约.md）基础上做了扩展，增加了
///    nutrition / price_source / reason / meta 四块 ——
///    这些是"约束优化 + 官方公示价格"的落点，需要在接口评审时跟后端确认。
/// =====================================================================

/// true = 读 assets/mock/plan.json 里的假数据
/// false = 调真实后端接口
const bool useMock = true;

/// 后端地址。
/// ⚠️ 10.0.2.2 只对 Android 模拟器有效。
///    真机调试要改成【电脑的局域网 IP】，例如 http://192.168.1.5:8000
///    （电脑上跑 ipconfig 查 IPv4 地址；手机和电脑要连同一个 WiFi）
const String apiBase = 'http://10.0.2.2:8000';

final Dio _dio = Dio(
  BaseOptions(
    baseUrl: apiBase,
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 30),
    sendTimeout: const Duration(seconds: 15),
    contentType: 'application/json; charset=utf-8',
    responseType: ResponseType.json,
  ),
);

/// 拉取一周（或 N 天）方案
Future<Plan> fetchPlan({
  String userId = 'u01',
  String? week,
  int days = 7,
  int people = 3,
  List<String> preferences = const <String>[],
}) async {
  if (useMock) {
    final raw = await rootBundle.loadString('assets/mock/plan.json');
    // 模拟一点网络延迟，方便看加载状态（真实接口快的话可以删掉）
    await Future<void>.delayed(const Duration(milliseconds: 300));
    return Plan.fromJson(jsonDecode(raw) as Map<String, dynamic>);
  }

  try {
    final res = await _dio.post<Map<String, dynamic>>(
      '/api/menu/plan',
      data: <String, dynamic>{
        'user_id': userId,
        'week': week,
        'days': days,
        'people': people,
        'preferences': preferences,
      },
    );
    final data = res.data;
    if (data == null) {
      throw const PlanApiException(code: 'EMPTY', message: '接口返回空数据');
    }
    // Dio 的 JSON 转换器已按 UTF-8 解码，中文不会乱码
    return Plan.fromJson(data);
  } on DioException catch (e) {
    throw _toPlanApiException(e);
  }
}

PlanApiException _toPlanApiException(DioException e) {
  final res = e.response;

  // 409 = 求解器无解（契约里的 INFEASIBLE）—— 给用户不一样的提示
  if (res != null && res.statusCode == 409) {
    Map<String, dynamic>? err;
    final body = res.data;
    if (body is Map) {
      final raw = body['error'];
      if (raw is Map) err = raw.cast<String, dynamic>();
    }
    return PlanApiException(
      code: (err?['code'] as String?) ?? 'INFEASIBLE',
      message: (err?['message'] as String?) ?? '当前约束下无解',
      bindingConstraint: err?['binding_constraint'] as String?,
    );
  }

  final code = res?.statusCode;
  return PlanApiException(
    code: code == null ? 'NETWORK' : 'HTTP_$code',
    message: code == null ? '网络请求失败：${e.message}' : '接口返回 $code',
  );
}

/// 统一的接口异常（对应契约里的 error 结构）
class PlanApiException implements Exception {
  final String code;
  final String message;

  /// 求解器无解时后端会给这个，前端提示用户放宽哪条约束
  final String? bindingConstraint;

  const PlanApiException({
    required this.code,
    required this.message,
    this.bindingConstraint,
  });

  /// 是否属于"无解"（约束冲突）—— 这种情况给用户的提示不一样
  bool get isInfeasible => code == 'INFEASIBLE';

  @override
  String toString() => message;
}
