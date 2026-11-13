import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

class StudioInputs with WidgetsBindingObserver {
  StudioInputs({
    required String origin,
    required this.currentUrl,
    required this.runJavaScript,
    this.onError,
  }) : _origin = Uri.parse(origin) {
    WidgetsBinding.instance.addObserver(this);
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'clipboardChanged') await notifyClipboardChange();
    });
  }

  static const _channel = MethodChannel('open_imagine/inputs');
  final Uri _origin;
  final Future<String?> Function() currentUrl;
  final Future<void> Function(String) runJavaScript;
  final void Function(String)? onError;
  bool _disposed = false;
  int _document = 0;

  void navigationStarted() {
    _document++;
  }

  bool allowsUrl(String address) {
    final uri = Uri.tryParse(address);
    return uri != null &&
        uri.scheme == _origin.scheme &&
        uri.host == _origin.host &&
        uri.port == _origin.port &&
        uri.userInfo.isEmpty;
  }

  Future<bool> _atStudio() async {
    if (_disposed) return false;
    final address = await currentUrl();
    return !_disposed && address != null && allowsUrl(address);
  }

  Future<bool> allowMicrophone(Set<WebViewPermissionResourceType> types) async {
    final document = _document;
    if (types.length != 1 ||
        !types.contains(WebViewPermissionResourceType.microphone)) {
      return false;
    }
    if (!await _atStudio()) return false;
    try {
      final granted = await _channel.invokeMethod<bool>('microphone') ?? false;
      return granted && document == _document && await _atStudio();
    } on PlatformException catch (error) {
      onError?.call(error.code);
      return false;
    }
  }

  Future<List<String>> pickFiles(FileSelectorParams params) async {
    final document = _document;
    if (!await _atStudio()) return [];
    try {
      final selected = await _channel.invokeListMethod<String>('pickFiles', {
        'acceptTypes': params.acceptTypes,
        'multiple': params.mode == FileSelectorMode.openMultiple,
      });
      return document == _document && await _atStudio() ? selected ?? [] : [];
    } on PlatformException catch (error) {
      onError?.call(error.code);
      return [];
    }
  }

  Future<void> receive(String message) async {
    final document = _document;
    final Object? decoded;
    try {
      decoded = jsonDecode(message);
    } on FormatException {
      return;
    }
    if (decoded is! Map<String, dynamic> || decoded['id'] is! int) return;
    if (decoded['document'] != document) return;
    final method = decoded['method'];
    if (method != 'clipboardDescribe' && method != 'clipboardRead') return;
    if (document != _document || !await _atStudio()) return;
    Map<String, Object?> reply;
    try {
      reply = {
        'ok': true,
        'value': await _channel.invokeMethod<Object?>(method as String),
      };
    } on PlatformException catch (error) {
      reply = {'ok': false, 'error': error.code};
    }
    if (document != _document || !await _atStudio()) return;
    await runJavaScript(
      'window.StudioInputReply?.($document, ${decoded['id']}, ${jsonEncode(reply)});',
    );
  }

  Future<void> install() async {
    if (!await _atStudio()) return;
    await runJavaScript(
      _clipboardScript.replaceAll('__STUDIO_DOCUMENT__', _document.toString()),
    );
  }

  Future<void> notifyClipboardChange() async {
    if (!await _atStudio()) return;
    await runJavaScript(
      "window.dispatchEvent(new Event('studio-clipboard-changed'));",
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) notifyClipboardChange();
  }

  void dispose() {
    if (_disposed) return;
    _disposed = true;
    WidgetsBinding.instance.removeObserver(this);
    _channel.setMethodCallHandler(null);
  }
}

const _clipboardScript = r'''
(() => {
  if (window.StudioClipboard) return;
  const documentId = __STUDIO_DOCUMENT__;
  let serial = 0;
  const pending = new Map();
  const request = method => new Promise((resolve, reject) => {
    const id = ++serial;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error('clipboard_timeout'));
    }, 15000);
    pending.set(id, {resolve, reject, timer});
    StudioInputsBridge.postMessage(JSON.stringify({document: documentId, id, method}));
  });
  window.StudioInputReply = (document, id, reply) => {
    if (document !== documentId) return;
    const waiting = pending.get(id);
    if (!waiting) return;
    pending.delete(id);
    clearTimeout(waiting.timer);
    if (reply.ok) waiting.resolve(reply.value);
    else waiting.reject(new Error(reply.error));
  };
  window.StudioClipboard = {
    describe: () => request('clipboardDescribe'),
    read: () => request('clipboardRead'),
  };
  window.dispatchEvent(new Event('studio-clipboard-changed'));
})();
''';
