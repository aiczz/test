import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../services/image_store.dart';

class LazyPhoto extends StatefulWidget {
  final String kind;
  final String name;
  final String? fallback;
  final BoxFit fit;
  const LazyPhoto({
    super.key,
    required this.kind,
    required this.name,
    this.fallback,
    this.fit = BoxFit.cover,
  });
  @override
  State<LazyPhoto> createState() => _LazyPhotoState();
}

class _LazyPhotoState extends State<LazyPhoto> {
  final _positions = <ScrollPosition>[];
  Animation<double>? _routeAnimation;
  Timer? _timer;
  String? _url;
  bool _loading = false;
  bool _finished = false;
  bool _onScreen = false;
  int _revision = 0;

  @override
  void initState() {
    super.initState();
    BackendStatus.instance.addListener(_connectionChanged);
    AuthStore.instance.addListener(_connectionChanged);
  }

  void _scheduleCheck() =>
      WidgetsBinding.instance.addPostFrameCallback((_) => _check());

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _routeAnimation?.removeListener(_scheduleCheck);
    _routeAnimation = ModalRoute.of(context)?.animation;
    // A bottom sheet can still be below the viewport on its first frame.
    // Recheck while the route enters, even when the user does not scroll.
    _routeAnimation?.addListener(_scheduleCheck);
    for (final position in _positions) {
      position.removeListener(_scheduleCheck);
    }
    _positions.clear();
    context.visitAncestorElements((element) {
      if (element is StatefulElement && element.state is ScrollableState) {
        final position = (element.state as ScrollableState).position;
        if (!_positions.contains(position)) {
          _positions.add(position);
          position.addListener(_scheduleCheck);
        }
      }
      return true;
    });
    _scheduleCheck();
  }

  @override
  void didUpdateWidget(covariant LazyPhoto oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.kind != widget.kind ||
        oldWidget.name != widget.name ||
        oldWidget.fallback != widget.fallback) {
      _revision++;
      _url = null;
      _loading = false;
      _finished = false;
      _timer?.cancel();
      _scheduleCheck();
    }
  }

  void _connectionChanged() {
    if (!mounted) return;
    _revision++;
    _loading = false;
    _finished = false;
    _scheduleCheck();
  }

  bool get _visible {
    var hidden = false;
    context.visitAncestorElements((element) {
      final ancestor = element.widget;
      if (ancestor is Offstage && ancestor.offstage ||
          ancestor is Visibility && !ancestor.visible) {
        hidden = true;
      }
      return !hidden;
    });
    if (hidden) return false;
    final box = context.findRenderObject();
    if (box is! RenderBox || !box.attached || !box.hasSize) return false;
    var area = (box.localToGlobal(Offset.zero) & box.size).intersect(
      Offset.zero & MediaQuery.sizeOf(context),
    );
    final viewport = RenderAbstractViewport.maybeOf(box);
    if (viewport is RenderBox) {
      final viewportBox = viewport as RenderBox;
      area = area.intersect(
        viewportBox.localToGlobal(Offset.zero) & viewportBox.size,
      );
    }
    return !area.isEmpty;
  }

  void _check() {
    if (!mounted) return;
    final visible = _visible;
    if (_onScreen != visible) setState(() => _onScreen = visible);
    if (_loading ||
        _finished ||
        !visible ||
        !BackendStatus.instance.online ||
        widget.name.trim().isEmpty) {
      return;
    }
    // Existing server-hosted photos are already persistent; simply lazy-load them.
    final fallback = widget.fallback ?? '';
    if (fallback.startsWith('https://') ||
        fallback.startsWith('http://') ||
        fallback.startsWith('/')) {
      _finished = true;
      return;
    }
    _load();
  }

  Future<void> _load() async {
    _loading = true;
    final revision = _revision;
    final base = BackendStatus.instance.apiBase.replaceFirst(RegExp(r'/$'), '');
    final result = await ImageStore.resolve(widget.kind, widget.name);
    if (!mounted || revision != _revision) return;
    _loading = false;
    if (result['status'] == 'ready' && result['url'] is String) {
      setState(() {
        _url = '$base${result['url']}';
        _finished = true;
      });
    } else if (const [
      'generating',
      'busy',
      'limited',
      'unavailable',
    ].contains(result['status'])) {
      _timer?.cancel();
      _timer = Timer(
        Duration(seconds: result['status'] == 'generating' ? 5 : 60),
        _check,
      );
    } else if (result['status'] == 'failed' && result['can_retry'] == true) {
      _timer?.cancel();
      final seconds = (result['retry_after'] as num?)?.toInt() ?? 300;
      _timer = Timer(Duration(seconds: seconds.clamp(30, 3600)), _check);
    } else {
      _finished = true;
    }
  }

  Widget _placeholder() => const ColoredBox(
    color: Color(0xFFF1F5EF),
    child: Center(
      child: Icon(Icons.restaurant_outlined, color: Color(0xFF78917C)),
    ),
  );

  Widget _fallback() {
    final path = widget.fallback?.trim() ?? '';
    if (path.isEmpty) return _placeholder();
    final source = path.startsWith('/')
        ? '${BackendStatus.instance.apiBase.replaceFirst(RegExp(r'/$'), '')}$path'
        : path;
    if (source.startsWith('http://') || source.startsWith('https://')) {
      return Image.network(
        source,
        fit: widget.fit,
        width: double.infinity,
        height: double.infinity,
        errorBuilder: (_, _, _) => _placeholder(),
      );
    }
    return Image.asset(
      source,
      fit: widget.fit,
      width: double.infinity,
      height: double.infinity,
      errorBuilder: (_, _, _) => _placeholder(),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_onScreen) return _placeholder();
    if (_url == null) return _fallback();
    return Image.network(
      _url!,
      fit: widget.fit,
      width: double.infinity,
      height: double.infinity,
      loadingBuilder: (_, child, progress) =>
          progress == null ? child : _fallback(),
      errorBuilder: (_, _, _) => _fallback(),
    );
  }

  @override
  void dispose() {
    _revision++;
    _routeAnimation?.removeListener(_scheduleCheck);
    _timer?.cancel();
    for (final position in _positions) {
      position.removeListener(_scheduleCheck);
    }
    BackendStatus.instance.removeListener(_connectionChanged);
    AuthStore.instance.removeListener(_connectionChanged);
    super.dispose();
  }
}
