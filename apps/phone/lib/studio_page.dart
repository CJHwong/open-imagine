import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
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
/// Install what the page needs from this view, and say whether it worked.
///
/// The input bridge is a native capability: without it the page cannot attach a file or
/// take a recording, and a page that looks loaded and silently cannot is worse than one
/// that reports the failure. It is retried once, because the navigation can land a moment
/// before the document is ready. The style is presentation only, so it is best effort.
Future<bool> installPage({
  required Future<void> Function() inputs,
  required Future<void> Function() style,
}) async {
  for (var attempt = 0; attempt < 2; attempt++) {
    try {
      await inputs();
      break;
    } catch (_) {
      if (attempt == 1) return true;
    }
  }
  try {
    await style();
  } catch (_) {
    // The page still works without the insets.
  }
  return false;
}

// SafeArea keeps this view off the system bars, so the page must not inset them a second
// time.
const _safeAreaStyle =
    "(() => { const style = document.createElement('style');"
    "style.textContent = '*{-webkit-tap-highlight-color: transparent !important;}'"
    " + ':root{--safe-top:0px;--safe-right:0px;--safe-bottom:0px;--safe-left:0px;}';"
    "document.head.appendChild(style); })()";

/// How many probes in a row without an answer mark the studio gone.
///
/// The probe is the only liveness check, so this is also how long a phone tolerates a
/// studio that is slow to answer. Three was too few: freeing a large model, or a radio
/// that stalls for a moment, cut a connection that would have recovered.
const int missesBeforeLost = 10;

bool studioIsGone(int misses) => misses >= missesBeforeLost;

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
  bool _receiving = false;
  int _incomingBytes = 0;
  String _savingName = 'download';
  String _savingMime = 'application/octet-stream';
  bool _loading = true;
  bool _checking = false;
  bool _reading = false;
  int _misses = 0;
  // Bumped when the page goes away. A read that finishes afterwards must not post a
  // notification for a run nobody is watching any more.
  int _epoch = 0;
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
              onPageFinished: (_) async {
                final failed = await installPage(
                  inputs: _inputs.install,
                  style: () => _controller.runJavaScript(_safeAreaStyle),
                );
                if (!mounted) return;
                setState(() {
                  _loading = false;
                  _error = failed
                      ? AppLocalizations.of(context).pageSetupFailed
                      : null;
                });
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
    // Native setup and the load both fail with a PlatformException, and an unhandled
    // asynchronous error leaves the page on a spinner with nothing to press.
    try {
      final platform = _controller.platform;
      if (platform is AndroidWebViewController) {
        await platform.setOnShowFileSelector(_inputs.pickFiles);
        await platform.setMediaPlaybackRequiresUserGesture(false);
        // The page keeps its own pinch zoom in the image viewer. Browser zoom
        // would scale the whole menu instead.
        await platform.enableZoom(false);
      }
      await _controller.loadRequest(Uri.parse(_origin));
    } catch (error) {
      if (!mounted) return;
      if (kDebugMode) debugPrint('Opening the studio failed: $error');
      setState(() {
        _loading = false;
        _error = AppLocalizations.of(context).couldNotReach;
      });
    }
  }

  Future<void> _read() async {
    if (_reading) return;
    _reading = true;
    final epoch = _epoch;
    try {
      final progress = await readProgress(widget.port);
      // A read started before dispose() finishes after it, and observing then would
      // bring the foreground notification back.
      if (!mounted || epoch != _epoch) return;
      // The progress route says a run ended, not how it ended. One more read names the
      // operation and its terminal status, so the notice does not call a failure
      // "finished".
      final outcome = progress.progress?.running == false
          ? await readOutcome(widget.port)
          : null;
      if (!mounted || epoch != _epoch) return;
      await RunNotifications.observe(progress, outcome: outcome);
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
      // A probe that misses is not a studio that is gone. The studio frees a model
      // while a workspace switch runs, and the phone's own radio can stall too, so a
      // few misses are normal. Only a minute of them ends the connection.
      if (!studioIsGone(_misses)) return;
      _heartbeat?.cancel();
      widget.onLost?.call();
      if (mounted) Navigator.of(context).pop();
    } finally {
      _checking = false;
    }
  }

  /// The largest download this page accepts. A result is a generated clip, not a
  /// library, and the whole thing is held in memory until it is saved.
  static const int maxDownloadBytes = 1024 * 1024 * 1024;

  Future<void> _receive(String message) async {
    final payload = jsonDecode(message) as Map<String, dynamic>;
    final l10n = AppLocalizations.of(context);
    final kind = payload['kind'];
    if (kind == 'begin') {
      _incoming.clear();
      _incomingBytes = 0;
      _receiving = true;
      _savingName = (payload['name'] as String?) ?? 'download';
      _savingMime = (payload['mime'] as String?) ?? 'application/octet-stream';
    } else if (kind == 'chunk') {
      if (!_receiving) return;
      final chunk = base64Decode(payload['data'] as String);
      _incomingBytes += chunk.length;
      if (_incomingBytes > maxDownloadBytes) {
        // A transfer past the cap is dropped whole, and its remaining chunks are
        // ignored until the next begin.
        _receiving = false;
        _incoming.clear();
        _notify(l10n.couldNotSave('the download is too large'));
        return;
      }
      _incoming.add(chunk);
    } else if (kind == 'end') {
      if (!_receiving) return;
      _receiving = false;
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
    _epoch++;
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
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        _error!,
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodyLarge,
                      ),
                      const SizedBox(height: 12),
                      FilledButton(
                        onPressed: () {
                          setState(() {
                            _loading = true;
                            _error = null;
                          });
                          unawaited(_open());
                        },
                        child: Text(AppLocalizations.of(context).retry),
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
}
