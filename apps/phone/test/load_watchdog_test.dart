import 'package:flutter_test/flutter_test.dart';
import 'package:open_imagine_phone/studio_page.dart';

/// A load that neither finishes nor fails left the page undrawn with nothing to press.
void main() {
  const limit = Duration(milliseconds: 40);
  const past = Duration(milliseconds: 80);

  test('a stuck load reloads once, and a second stuck load gives up', () async {
    var reloads = 0;
    var gaveUp = 0;
    final watchdog = LoadWatchdog(
      reload: () => reloads++,
      giveUp: () => gaveUp++,
      limit: limit,
    );

    watchdog.started();
    await Future<void>.delayed(past);
    expect((reloads, gaveUp), (1, 0));

    watchdog.started();
    await Future<void>.delayed(past);
    expect((reloads, gaveUp), (1, 1));
    watchdog.dispose();
  });

  test('a load that finishes in time does nothing', () async {
    var fired = 0;
    final watchdog = LoadWatchdog(
      reload: () => fired++,
      giveUp: () => fired++,
      limit: limit,
    );

    watchdog.started();
    watchdog.ended(loaded: true);
    await Future<void>.delayed(past);
    expect(fired, 0);
  });

  test(
    'a page that loads after a reload earns a fresh reload next time',
    () async {
      var reloads = 0;
      var gaveUp = 0;
      final watchdog = LoadWatchdog(
        reload: () => reloads++,
        giveUp: () => gaveUp++,
        limit: limit,
      );

      watchdog.started();
      await Future<void>.delayed(past);
      watchdog.started();
      watchdog.ended(loaded: true);
      watchdog.started();
      await Future<void>.delayed(past);

      expect((reloads, gaveUp), (2, 0));
      watchdog.dispose();
    },
  );

  test(
    'a load that fails leaves the error to the view and does not reload',
    () async {
      var fired = 0;
      final watchdog = LoadWatchdog(
        reload: () => fired++,
        giveUp: () => fired++,
        limit: limit,
      );

      watchdog.started();
      watchdog.ended(loaded: false);
      await Future<void>.delayed(past);
      expect(fired, 0);
    },
  );
}
