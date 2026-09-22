// 城市选择器。
//
// 手动列表 + 一个「用当前位置」按钮：
//   · 定位成功 → 按经纬度粗匹配到最近的内置城市
//   · 定位失败 / 平台不支持 → 如实说明，用户可以手动选（所有平台都能用）
//
// ⚠️ 为什么不做真实逆地理编码：那需要地图 API key。而且后端的时令数据
//    只到全国级，城市名目前只影响显示 —— 为一个显示值接一个 API 不值得。

import 'package:flutter/material.dart';

import '../services/city.dart';
import '../services/geolocation.dart';
import '../theme.dart';

Future<void> showCityPicker(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (_) => const _CityPickerSheet(),
  );
}

class _CityPickerSheet extends StatefulWidget {
  const _CityPickerSheet();

  @override
  State<_CityPickerSheet> createState() => _CityPickerSheetState();
}

class _CityPickerSheetState extends State<_CityPickerSheet> {
  Future<void> _detect() async {
    final store = CityStore.instance;
    if (store.detecting) return;
    store.setDetecting(true);

    try {
      final coords = await currentCoordinates();
      if (!mounted) return;

      if (coords == null) {
        store.setDetectError(geolocationUnsupportedHint);
        return;
      }
      store.selectByCoordinates(coords.$1, coords.$2);
      if (mounted) Navigator.of(context).pop();
    } catch (error) {
      if (mounted) store.setDetectError('定位失败：$error');
    } finally {
      // ★ 放在 finally 里：成功、失败、抛异常三条路径都要复位，
      //   否则按钮会永远卡在「正在定位…」的禁用状态。
      if (store.detecting) store.setDetecting(false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: CityStore.instance,
      builder: (context, _) {
        final store = CityStore.instance;

        return Container(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
          decoration: const BoxDecoration(
            color: page,
            borderRadius: BorderRadius.vertical(top: Radius.circular(rBlock)),
          ),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
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
                const Text(
                  '选择城市',
                  style: TextStyle(fontSize: 19, fontWeight: FontWeight.w900),
                ),
                const SizedBox(height: 4),
                Text(
                  store.autoDetected
                      ? '当前「${store.city.name}」是根据定位推荐的'
                      : '当前「${store.city.name}」是你手动选的',
                  style: const TextStyle(fontSize: 11.5, color: muted),
                ),
                const SizedBox(height: 14),

                // ---- 用当前位置 ----
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: store.detecting ? null : _detect,
                    icon: store.detecting
                        ? const SizedBox(
                            width: 15,
                            height: 15,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: orange700,
                            ),
                          )
                        : const Icon(
                            Icons.my_location,
                            size: 17,
                            color: orange700,
                          ),
                    label: Text(
                      store.detecting ? '正在定位…' : '用当前位置',
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 13,
                      ),
                    ),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: ink,
                      side: const BorderSide(color: orange700),
                      padding: const EdgeInsets.symmetric(vertical: 13),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(13),
                      ),
                    ),
                  ),
                ),

                if (store.detectError != null) ...[
                  const SizedBox(height: 9),
                  Text(
                    store.detectError!,
                    style: const TextStyle(fontSize: 11, color: orange),
                  ),
                ],

                const SizedBox(height: 18),
                const Text(
                  '或手动选择',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: muted,
                  ),
                ),
                const SizedBox(height: 10),

                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final city in kCities)
                      GestureDetector(
                        onTap: () {
                          store.select(city);
                          Navigator.of(context).pop();
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 15,
                            vertical: 9,
                          ),
                          decoration: BoxDecoration(
                            color: store.city.name == city.name
                                ? orange700
                                : Colors.white,
                            borderRadius: BorderRadius.circular(999),
                            border: Border.all(
                              color: store.city.name == city.name
                                  ? orange700
                                  : line,
                            ),
                          ),
                          child: Text(
                            city.name,
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                              color: store.city.name == city.name
                                  ? Colors.white
                                  : ink,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),

                const SizedBox(height: 16),
                const Text(
                  '说明：时令数据目前是全国级的，城市只影响顶部显示 —— '
                  '接入城市级农时数据后，这里会真的改变推荐结果。',
                  style: TextStyle(fontSize: 10, color: muted, height: 1.5),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
