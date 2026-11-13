import 'package:flutter_test/flutter_test.dart';
import 'package:open_imagine_phone/studio_page.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

class AndroidController extends Fake implements AndroidWebViewController {}

class Controller extends Fake implements WebViewController {
  Controller(this.platform);
  @override
  final AndroidWebViewController platform;
}

void main() {
  test(
    'the Android studio uses native composition for asynchronous page updates',
    () {
      final platform = AndroidController();
      final params = studioWebViewParameters(Controller(platform));
      expect(params, isA<AndroidWebViewWidgetCreationParams>());
      final android = params as AndroidWebViewWidgetCreationParams;
      expect(android.controller, same(platform));
      expect(android.displayWithHybridComposition, isTrue);
    },
  );
}
