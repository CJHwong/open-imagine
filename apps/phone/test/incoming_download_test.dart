import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:open_imagine_phone/incoming_download.dart';

Map<String, dynamic> begin({
  String id = 'transfer-1',
  int? bytes = 6,
  String name = 'clip.mp4',
}) => {
  'kind': 'begin',
  'id': id,
  'name': name,
  'mime': 'video/mp4',
  'bytes': bytes,
};

void main() {
  test('the chunks are assembled into the declared file', () {
    final download = IncomingDownload.begin(begin());

    expect(download.owns('transfer-1'), isTrue);
    expect(download.add([1, 2, 3]), isTrue);
    expect(download.add([4, 5, 6]), isTrue);
    expect(download.finish(), Uint8List.fromList([1, 2, 3, 4, 5, 6]));
    expect(download.name, 'clip.mp4');
    expect(download.mime, 'video/mp4');
  });

  test('a chunk from another transfer is not this one', () {
    final download = IncomingDownload.begin(begin());

    expect(download.owns('transfer-2'), isFalse);
    expect(download.owns(null), isFalse);
  });

  test('a page that declares no size still transfers', () {
    final download = IncomingDownload.begin(begin(bytes: null));

    expect(download.add([1, 2, 3]), isTrue);
    expect(download.finish(), Uint8List.fromList([1, 2, 3]));
  });

  test('a transfer past its declared size is dropped whole', () {
    final download = IncomingDownload.begin(begin(bytes: 4));

    expect(download.add([1, 2, 3]), isTrue);
    expect(download.add([4, 5]), isFalse);
    expect(download.finish(), isNull);
  });

  test('an end that arrives short of the declared size saves nothing', () {
    final download = IncomingDownload.begin(begin(bytes: 6));

    expect(download.add([1, 2, 3]), isTrue);

    expect(download.finish(), isNull);
  });

  test('a transfer that passes the cap is refused', () {
    final download = IncomingDownload.begin(
      begin(bytes: IncomingDownload.maxBytes + 1),
    );

    expect(
      download.add(List<int>.filled(IncomingDownload.maxBytes + 1, 0)),
      isFalse,
    );
    expect(download.finish(), isNull);
  });

  test('the begin message survives an older page that sends no id', () {
    final download = IncomingDownload.begin(
      jsonDecode('{"kind": "begin", "name": "a.png"}'),
    );

    expect(download.owns(null), isTrue);
    expect(download.name, 'a.png');
    expect(download.mime, 'application/octet-stream');
    expect(download.expectedBytes, isNull);
  });
}
