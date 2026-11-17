import 'package:flutter_test/flutter_test.dart';
import 'package:open_imagine_phone/pipe.dart';

/// Which refusals mean the stored pairing is useless, and which are this attempt's.
void main() {
  test('a port already in use keeps the pairing', () {
    expect(PipeRefused(-8).permanent, isFalse);
    expect(PipeRefused(-7).permanent, isFalse);
  });

  test('a ticket or key this process cannot use ends the pairing', () {
    expect(PipeRefused(-1).permanent, isTrue);
    expect(PipeRefused(-3).permanent, isTrue);
    expect(PipeRefused(-6).permanent, isTrue);
  });
}
