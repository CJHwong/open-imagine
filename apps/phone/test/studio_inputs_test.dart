import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:open_imagine_phone/studio_inputs.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('open_imagine/inputs');
  late StudioInputs inputs;
  late List<MethodCall> calls;
  late List<String> scripts;
  late String currentUrl;

  setUp(() {
    calls = [];
    scripts = [];
    currentUrl = 'http://127.0.0.1:8765/';
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          return switch (call.method) {
            'microphone' => true,
            'pickFiles' => ['content://documents/image/42'],
            'clipboardDescribe' => {
              'types': ['image/png'],
              'token': '42',
            },
            'clipboardRead' => [],
            _ => null,
          };
        });
    inputs = StudioInputs(
      origin: 'http://127.0.0.1:8765',
      currentUrl: () async => currentUrl,
      runJavaScript: (script) async => scripts.add(script),
    );
  });

  tearDown(() {
    inputs.dispose();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  test(
    'microphone requests Android permission before granting WebView access',
    () async {
      expect(
        await inputs.allowMicrophone({
          WebViewPermissionResourceType.microphone,
        }),
        isTrue,
      );
      expect(calls.single.method, 'microphone');
      expect(
        await inputs.allowMicrophone({WebViewPermissionResourceType.camera}),
        isFalse,
      );
      expect(calls, hasLength(1));
    },
  );

  test('the origin check rejects prefix matches and other ports', () async {
    for (final url in [
      'http://127.0.0.1:87650/',
      'http://127.0.0.1:8765.evil.test/',
      'https://example.com/',
    ]) {
      currentUrl = url;
      expect(
        await inputs.allowMicrophone({
          WebViewPermissionResourceType.microphone,
        }),
        isFalse,
      );
    }
    expect(calls, isEmpty);
  });

  test(
    'the picker keeps MIME filters, multiple selection and content URIs',
    () async {
      final selected = await inputs.pickFiles(
        const FileSelectorParams(
          isCaptureEnabled: false,
          acceptTypes: ['image/*', '.heic'],
          mode: FileSelectorMode.openMultiple,
        ),
      );
      expect(selected, ['content://documents/image/42']);
      expect(calls.single.arguments, {
        'acceptTypes': ['image/*', '.heic'],
        'multiple': true,
      });
    },
  );

  test('clipboard detection requests metadata only', () async {
    await inputs.receive(
      jsonEncode({'document': 0, 'id': 1, 'method': 'clipboardDescribe'}),
    );
    expect(calls.single.method, 'clipboardDescribe');
    expect(scripts.single, contains('image/png'));
    expect(scripts.single, contains('StudioInputReply'));
  });

  test('clipboard messages cannot invoke unrelated native methods', () async {
    await inputs.receive(
      jsonEncode({'document': 0, 'id': 1, 'method': 'pickFiles'}),
    );
    await inputs.receive('invalid JSON');
    expect(calls, isEmpty);
  });

  test('clipboard replies stop after navigation and disposal', () async {
    currentUrl = 'https://example.com/';
    await inputs.receive(
      jsonEncode({'document': 0, 'id': 1, 'method': 'clipboardRead'}),
    );
    expect(calls, isEmpty);
    expect(scripts, isEmpty);
    inputs.dispose();
    currentUrl = 'http://127.0.0.1:8765/';
    await inputs.receive(
      jsonEncode({'document': 0, 'id': 2, 'method': 'clipboardRead'}),
    );
    expect(calls, isEmpty);
  });

  test(
    'a same-origin reload discards the previous document clipboard reply',
    () async {
      final result = Completer<Object?>();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (_) => result.future);
      final reply = inputs.receive(
        jsonEncode({'document': 0, 'id': 1, 'method': 'clipboardRead'}),
      );
      await Future<void>.delayed(Duration.zero);
      inputs.navigationStarted();
      result.complete([
        {'mime': 'image/png', 'base64': 'AA=='},
      ]);
      await reply;
      expect(scripts, isEmpty);
    },
  );

  test(
    'permission and picker failures return a refusal or cancellation',
    () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            channel,
            (_) async => throw PlatformException(code: 'unavailable'),
          );
      expect(
        await inputs.allowMicrophone({
          WebViewPermissionResourceType.microphone,
        }),
        isFalse,
      );
      expect(
        await inputs.pickFiles(
          const FileSelectorParams(
            isCaptureEnabled: false,
            acceptTypes: [],
            mode: FileSelectorMode.open,
          ),
        ),
        isEmpty,
      );
      await inputs.receive(
        jsonEncode({'document': 0, 'id': 3, 'method': 'clipboardRead'}),
      );
      expect(scripts.single, contains('unavailable'));
    },
  );
}
