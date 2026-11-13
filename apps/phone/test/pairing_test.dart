import 'package:flutter_test/flutter_test.dart';
import 'package:open_imagine_phone/pairing.dart';

void main() {
  test('a pairing code from the studio parses', () {
    final pairing = Pairing.parse(
      'openimagine://pair?v=1&ticket=endpoint${'a' * 56}&port=8765',
    );

    expect(pairing, isNotNull);
    expect(pairing!.port, 8765);
    expect(pairing.ticket.length, 64);
  });

  test('a code from another app is refused', () {
    expect(
      Pairing.parse('https://example.com/?ticket=${'a' * 60}&port=8765'),
      isNull,
    );
    expect(
      Pairing.parse('openimagine://pair?v=2&ticket=endpoint${'a' * 56}'),
      isNull,
    );
    expect(
      Pairing.parse('openimagine://pair?v=1&ticket=short&port=8765'),
      isNull,
    );
    expect(
      Pairing.parse('openimagine://pair?v=1&ticket=endpoint${'a' * 56}&port=0'),
      isNull,
    );
  });
}
