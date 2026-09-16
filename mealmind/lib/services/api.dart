import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:http/http.dart' as http;

import '../models/plan.dart';

/// =====================================================================
/// 接口层
///
/// ★ 后端接口好了之后，把 useMock 改成 false 就行 —— 只改这一行。
///   前端所有页面都已经按真接口的格式在跑，不需要动别的代码。
/// =====================================================================

/// true = 读 assets/mock/plan.json 里的假数据
/// false = 调真实后端接口
const bool useMock = true;

/// 后端地址。
/// ⚠️ 10.0.2.2 只对 Android 模拟器有效。
///    真机调试要改成【电脑的局域网 IP】，例如 http://192.168.1.5:8000
///    （电脑上跑 ipconfig 查 IPv4 地址；手机和电脑要连同一个 WiFi）
const String apiBase = 'http://10.0.2.2:8000';

/// 拉取一周方案
Future<Plan> fetchPlan({String userId = 'u01', String? week}) async {
  if (useMock) {
    final raw = await rootBundle.loadString('assets/mock/plan.json');
    // 模拟一点网络延迟，方便看加载状态（真实接口快的话可以删掉）
    await Future.delayed(const Duration(milliseconds: 300));
    return Plan.fromJson(jsonDecode(raw) as Map<String, dynamic>);
  }

  final uri = Uri.parse('$apiBase/api/plan').replace(
    queryParameters: <String, String>{
      'user_id': userId,
      if (week != null) 'week': week,
    },
  );

  final res = await http.get(uri).timeout(const Duration(seconds: 30));

  if (res.statusCode != 200) {
    throw PlanApiException(
      code: 'HTTP_${res.statusCode}',
      message: '接口返回 ${res.statusCode}',
    );
  }

  // ⚠️ 必须用 utf8.decode(res.bodyBytes)，直接 res.body 中文会乱码
  return Plan.fromJson(
    jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>,
  );
}

/// 统一的接口异常（对应契约里的 error 结构）
class PlanApiException implements Exception {
  final String code;
  final String message;

  /// 求解器无解时后端会给这个，前端可以提示用户放宽哪条约束
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
