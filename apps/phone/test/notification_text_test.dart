import 'package:flutter_test/flutter_test.dart';
import 'package:open_imagine_phone/notifications.dart';
import 'package:open_imagine_phone/probe.dart';

void main() {
  test('a failed run is named as a failure, with its operation', () {
    const outcome = RunOutcome(id: '3f2a1b07c9', status: 'failed');

    expect(
      RunNotifications.completionTitle('video', outcome.status),
      'Video failed',
    );
    expect(
      RunNotifications.completionBody(outcome),
      'Operation 3f2a1b07 failed. Tap to return to the studio.',
    );
  });

  test('a stopped run is named as stopped', () {
    const outcome = RunOutcome(id: 'abc', status: 'cancelled');

    expect(
      RunNotifications.completionTitle('image', outcome.status),
      'Image stopped',
    );
    expect(RunNotifications.completionBody(outcome), contains('was stopped'));
  });

  test('a completion with no operation to read still names the media', () {
    expect(RunNotifications.completionTitle('voice', ''), 'Audio finished');
    expect(
      RunNotifications.completionBody(null),
      'Tap to return to the studio.',
    );
  });
}
