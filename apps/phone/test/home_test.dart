import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:open_imagine_phone/home.dart';
import 'package:open_imagine_phone/l10n/app_localizations.dart';
import 'package:open_imagine_phone/pipe.dart';
import 'package:open_imagine_phone/studio_page.dart';

class PendingPipe implements PipeTransport {
  final starts = <Completer<void>>[];
  int stops = 0;

  @override
  bool get running => false;
  @override
  String? get error => null;

  @override
  Future<void> start(String ticket, int port) {
    final pending = Completer<void>();
    starts.add(pending);
    return pending.future;
  }

  @override
  Future<void> stop() async {
    stops++;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const notifications = MethodChannel(
    'dexterous.com/flutter/local_notifications',
  );
  late PendingPipe pipe;

  setUp(() {
    AndroidFlutterLocalNotificationsPlugin.registerWith();
    pipe = PendingPipe();
    FlutterSecureStorage.setMockInitialValues({
      'pairing': 'openimagine://pair?v=1&ticket=endpoint${'a' * 56}&port=8897',
    });
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(notifications, (_) async => true);
  });

  Future<void> mount(
    WidgetTester tester,
    Future<bool> Function(int) probe,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: HomePage(transport: pipe, probe: probe),
      ),
    );
    await tester.pump();
  }

  testWidgets('Disconnect cancels a pending transport before the probe', (
    tester,
  ) async {
    var probes = 0;
    await mount(tester, (_) async {
      probes++;
      return true;
    });
    expect(pipe.starts, hasLength(1));
    final disconnect = find.widgetWithText(TextButton, 'Disconnect');
    expect(tester.widget<TextButton>(disconnect).onPressed, isNotNull);
    await tester.tap(disconnect);
    await tester.pumpAndSettle();
    expect(find.text('Scan the code'), findsOneWidget);
    expect(pipe.stops, 1);
    pipe.starts.single.complete();
    await tester.pumpAndSettle();
    expect(probes, 0);
    expect(find.byType(StudioPage), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a successful probe cannot reopen a cancelled connection', (
    tester,
  ) async {
    final probe = Completer<bool>();
    await mount(tester, (_) => probe.future);
    pipe.starts.single.complete();
    await tester.pump();
    await tester.tap(find.widgetWithText(TextButton, 'Disconnect'));
    await tester.pumpAndSettle();
    probe.complete(true);
    await tester.pumpAndSettle();
    expect(find.text('Scan the code'), findsOneWidget);
    expect(find.byType(StudioPage), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a cancelled failure adds no error or extra transport stop', (
    tester,
  ) async {
    final probe = Completer<bool>();
    await mount(tester, (_) => probe.future);
    pipe.starts.single.complete();
    await tester.pump();
    await tester.tap(find.widgetWithText(TextButton, 'Disconnect'));
    await tester.pumpAndSettle();
    probe.completeError(StateError('A late probe failure'));
    await tester.pumpAndSettle();
    expect(find.text('Scan the code'), findsOneWidget);
    expect(pipe.stops, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a cancelled attempt cannot clear the next attempt busy state', (
    tester,
  ) async {
    await mount(tester, (_) async => false);
    await tester.tap(find.widgetWithText(TextButton, 'Disconnect'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Ticket (debug)'),
      'endpoint${'b' * 56}',
    );
    await tester.tap(find.text('Use this code'));
    await tester.pump();
    expect(pipe.starts, hasLength(2));
    pipe.starts.first.complete();
    await tester.pump();
    expect(find.text('Connecting'), findsOneWidget);
    expect(
      tester
          .widget<TextButton>(find.widgetWithText(TextButton, 'Disconnect'))
          .onPressed,
      isNotNull,
    );
    await tester.tap(find.widgetWithText(TextButton, 'Disconnect'));
    pipe.starts.last.complete();
    await tester.pumpAndSettle();
    expect(find.text('Scan the code'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
