import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

import 'l10n/app_localizations.dart';
import 'notifications.dart';
import 'probe.dart';
import 'studio_inputs.dart';

PlatformWebViewWidgetCreationParams studioWebViewParameters(
  WebViewController controller,
) {
  final params = PlatformWebViewWidgetCreationParams(
    controller: controller.platform,
  );
  if (controller.platform is! AndroidWebViewController) return params;
  // Texture composition can leave page updates unpainted until another gesture.
  return AndroidWebViewWidgetCreationParams.fromPlatformWebViewWidgetCreationParams(
    params,
    displayWithHybridComposition: true,
  );
}

/// The studio fills the screen. The page is the only chrome: no address, no
/// back button and no reload button. The system back gesture leaves the app.
class StudioPage extends StatefulWidget {
  const StudioPage({super.key, required this.port, this.onLost});

  final int port;
  final VoidCallback? onLost;

  @override
  State<StudioPage> createState() => _StudioPageState();
}

class _StudioPageState extends State<StudioPage> {
  static const MethodChannel _files = MethodChannel('open_imagine/files');

  late final WebViewController _controller;
  late final StudioInputs _inputs;
  final BytesBuilder _incoming = BytesBuilder(copy: false);
  String _savingName = 'download';
  String _savingMime = 'application/octet-stream';
  bool _loading = true;
  bool _checking = false;
  bool _reading = false;
  int _misses = 0;
  String? _error;
  Timer? _heartbeat;
  Timer? _progress;

  String get _origin => 'http://127.0.0.1:${widget.port}';

  @override
  void initState() {
    super.initState();
    _inputs = StudioInputs(
      origin: _origin,
      currentUrl: () => _controller.currentUrl(),
      runJavaScript: (script) => _controller.runJavaScript(script),
      onError: (_) {
        if (mounted) _notify(AppLocalizations.of(context).inputUnavailable);
      },
    );
    _controller =
        WebViewController(
            onPermissionRequest: (request) async {
              if (await _inputs.allowMicrophone(request.types)) {
                await request.grant();
              } else {
                await request.deny();
                if (mounted) {
                  _notify(AppLocalizations.of(context).microphoneDenied);
                }
              }
            },
          )
          ..setJavaScriptMode(JavaScriptMode.unrestricted)
          ..setBackgroundColor(const Color(0xFF101413))
          ..addJavaScriptChannel(
            'StudioInputsBridge',
            onMessageReceived: (message) => _inputs.receive(message.message),
          )
          ..addJavaScriptChannel(
            'StudioBridge',
            onMessageReceived: (message) {
              _receive(message.message);
            },
          )
          ..setNavigationDelegate(
            NavigationDelegate(
              onPageStarted: (_) {
                _inputs.navigationStarted();
                if (mounted) {
                  setState(() {
                    _loading = true;
                    _error = null;
                  });
                }
              },
              onPageFinished: (_) {
                unawaited(_inputs.install());
                unawaited(
                  _controller.runJavaScript(
                    "(() => { const style = document.createElement('style');"
                    // SafeArea keeps this view off the system bars, so the page
                    // must not inset them a second time.
                    "style.textContent = '*{-webkit-tap-highlight-color: transparent !important;}'"
                    " + ':root{--safe-top:0px;--safe-right:0px;--safe-bottom:0px;--safe-left:0px;}';"
                    "document.head.appendChild(style); })()",
                  ),
                );
                if (mounted) setState(() => _loading = false);
              },
              onWebResourceError: (error) {
                if (error.isForMainFrame ?? true) {
                  if (mounted) {
                    setState(() {
                      _loading = false;
                      _error = AppLocalizations.of(context).couldNotReach;
                    });
                  }
                }
              },
              onNavigationRequest: (request) {
                // The page is local. A link elsewhere opens nothing here.
                return _inputs.allowsUrl(request.url) ||
                        request.url.startsWith('about:')
                    ? NavigationDecision.navigate
                    : NavigationDecision.prevent;
              },
            ),
          );
    unawaited(_open());
    _heartbeat = Timer.periodic(const Duration(seconds: 3), (_) => _check());
    // Android can suspend the WebView while a run continues on the Mac.
    _progress = Timer.periodic(const Duration(seconds: 1), (_) => _read());
  }

  Future<void> _open() async {
    final platform = _controller.platform;
    if (platform is AndroidWebViewController) {
      await platform.setOnShowFileSelector(_inputs.pickFiles);
      await platform.setMediaPlaybackRequiresUserGesture(false);
      // The page keeps its own pinch zoom in the image viewer. Browser zoom
      // would scale the whole menu instead.
      await platform.enableZoom(false);
    }
    await _controller.loadRequest(Uri.parse(_origin));
  }

  Future<void> _read() async {
    if (_reading) return;
    _reading = true;
    try {
      await RunNotifications.observe(await readProgress(widget.port));
    } finally {
      _reading = false;
    }
  }

  Future<void> _check() async {
    if (_checking) return;
    _checking = true;
    try {
      if (await probeStudio(widget.port, timeout: const Duration(seconds: 5))) {
        _misses = 0;
        return;
      }
      _misses++;
      // One slow reply is not the end. Three in a row is.
      if (_misses < 3) return;
      _heartbeat?.cancel();
      widget.onLost?.call();
      if (mounted) Navigator.of(context).pop();
    } finally {
      _checking = false;
    }
  }

  Future<void> _receive(String message) async {
    final payload = jsonDecode(message) as Map<String, dynamic>;
    final l10n = AppLocalizations.of(context);
    final kind = payload['kind'];
    if (kind == 'begin') {
      _incoming.clear();
      _savingName = (payload['name'] as String?) ?? 'download';
      _savingMime = (payload['mime'] as String?) ?? 'application/octet-stream';
    } else if (kind == 'chunk') {
      _incoming.add(base64Decode(payload['data'] as String));
    } else if (kind == 'end') {
      final bytes = _incoming.takeBytes();
      try {
        await _files.invokeMethod<String>('save', {
          'name': _savingName,
          'mime': _savingMime,
          'bytes': bytes,
        });
        _notify(l10n.saved(_savingName));
      } on PlatformException catch (error) {
        _notify(l10n.couldNotSave(error.message ?? ''));
      }
    }
  }

  void _notify(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  void dispose() {
    _inputs.dispose();
    _heartbeat?.cancel();
    _progress?.cancel();
    unawaited(RunNotifications.clear());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: Colors.transparent,
      ),
      child: Scaffold(
        body: SafeArea(
          child: Stack(
            children: [
              WebViewWidget.fromPlatformCreationParams(
                params: studioWebViewParameters(_controller),
              ),
              if (_loading) const Center(child: CircularProgressIndicator()),
              if (_error != null)
                Center(
                  child: Text(
                    _error!,
                    style: Theme.of(context).textTheme.bodyLarge,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
