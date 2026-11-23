import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

import 'l10n/app_localizations.dart';
import 'notifications.dart';
import 'incoming_download.dart';
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

/// How long one load of the page may take before it counts as stuck.
const Duration pageLoadLimit = Duration(seconds: 20);

/// A load that neither finishes nor fails. One script stuck on a dead connection keeps the
/// WebView from reporting either, and the page stays undrawn with nothing to press. The
/// first stuck load reloads the page. The second shows the error and its Retry button.
class LoadWatchdog {
  LoadWatchdog({
    required this.reload,
    required this.giveUp,
    this.limit = pageLoadLimit,
  });

  final VoidCallback reload;
  final VoidCallback giveUp;
  final Duration limit;
  Timer? _timer;
  bool _reloaded = false;

  /// A load began. A second call restarts the limit.
  void started() {
    _timer?.cancel();
    _timer = Timer(limit, _expired);
  }

  /// The load ended, with the page or with an error the view already shows.
  void ended({required bool loaded}) {
    _timer?.cancel();
    _timer = null;
    if (loaded) _reloaded = false;
  }

  void dispose() => _timer?.cancel();

  void _expired() {
    _timer = null;
    if (_reloaded) {
      _reloaded = false;
      giveUp();
      return;
    }
    _reloaded = true;
    reload();
  }
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
  IncomingDownload? _download;
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
  late final LoadWatchdog _watchdog;

  String get _origin => 'http://127.0.0.1:${widget.port}';

  @override
  void initState() {
    super.initState();
    _watchdog = LoadWatchdog(
      reload: () {
        if (kDebugMode) {
          debugPrint('The studio page load stalled; reloading it.');
        }
        unawaited(_controller.reload());
      },
      giveUp: () {
        if (!mounted) return;
        setState(() {
          _loading = false;
          _error = AppLocalizations.of(context).couldNotReach;
        });
      },
    );
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
                _watchdog.started();
                _inputs.navigationStarted();
                if (mounted) {
                  setState(() {
                    _loading = true;
                    _error = null;
                  });
                }
              },
              onPageFinished: (_) async {
                _watchdog.ended(loaded: true);
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
                  _watchdog.ended(loaded: false);
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
      // Armed before the request: a document that never answers starts no page either.
      _watchdog.started();
      await _controller.loadRequest(Uri.parse(_origin));
    } catch (error) {
      _watchdog.ended(loaded: false);
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

  Future<void> _receive(String message) async {
    final payload = jsonDecode(message) as Map<String, dynamic>;
    final l10n = AppLocalizations.of(context);
    final kind = payload['kind'];
    if (kind == 'begin') {
      _download = IncomingDownload.begin(payload);
    } else if (kind == 'chunk') {
      final download = _download;
      if (download == null || !download.owns(payload['id'])) return;
      if (!download.add(base64Decode(payload['data'] as String))) {
        // The transfer is dropped whole, and its remaining chunks are ignored until
        // the next begin.
        _download = null;
        _notify(l10n.couldNotSave('the download is too large'));
      }
    } else if (kind == 'end') {
      final download = _download;
      if (download == null || !download.owns(payload['id'])) return;
      _download = null;
      final bytes = download.finish();
      if (bytes == null) {
        _notify(l10n.couldNotSave('the download did not arrive whole'));
        return;
      }
      try {
        await _files.invokeMethod<String>('save', {
          'name': download.name,
          'mime': download.mime,
          'bytes': bytes,
        });
        _notify(l10n.saved(download.name));
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
    _watchdog.dispose();
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
