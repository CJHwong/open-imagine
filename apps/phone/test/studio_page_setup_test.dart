import 'package:flutter_test/flutter_test.dart';
import 'package:open_imagine_phone/studio_page.dart';

/// The page setup runs after navigation, where a failure used to be invisible: the page
/// looked loaded and the native input bridge was simply absent.
void main() {
  test('a setup that fails once is retried, and the style still runs', () async {
    var attempts = 0;
    var styled = 0;

    final failed = await installPage(
      inputs: () async {
        attempts++;
        if (attempts == 1) throw StateError('the document was not ready');
      },
      style: () async => styled++,
    );

    expect(failed, isFalse);
    expect(attempts, 2);
    expect(styled, 1);
  });

  test('a setup that fails twice is reported', () async {
    var attempts = 0;
    var styled = 0;

    final failed = await installPage(
      inputs: () async {
        attempts++;
        throw StateError('no bridge');
      },
      style: () async => styled++,
    );

    expect(failed, isTrue);
    expect(attempts, 2);
    expect(styled, 0, reason: 'nothing else is worth doing without the input bridge');
  });

  test('a style that fails is not a page failure', () async {
    final failed = await installPage(
      inputs: () async {},
      style: () async => throw StateError('no document'),
    );

    expect(failed, isFalse);
  });
}
