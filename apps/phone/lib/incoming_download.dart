import 'dart:typed_data';

/// One download the page hands the app, assembled from the bridge's messages.
///
/// The page names each transfer, declares how many bytes it will send and labels every
/// chunk with that name. A chunk from another transfer, a transfer that passes the size
/// cap, or an end whose byte count differs from the declared one is refused, so a stale
/// or interleaved message can never be saved as a file.
class IncomingDownload {
  IncomingDownload._({
    required this.id,
    required this.name,
    required this.mime,
    required this.expectedBytes,
  });

  /// The largest download the app accepts. A result is a generated clip, not a
  /// library, and the whole thing is held in memory until it is saved.
  static const int maxBytes = 1024 * 1024 * 1024;

  /// The begin message. A page that declares no byte count still transfers; only the
  /// cap and the id are enforced for it.
  factory IncomingDownload.begin(Map<String, dynamic> message) =>
      IncomingDownload._(
        id: (message['id'] as String?) ?? '',
        name: (message['name'] as String?) ?? 'download',
        mime: (message['mime'] as String?) ?? 'application/octet-stream',
        expectedBytes: switch (message['bytes']) {
          final int bytes when bytes >= 0 => bytes,
          _ => null,
        },
      );

  final String id;
  final String name;
  final String mime;

  /// How many bytes the page declared, or null when it declared none.
  final int? expectedBytes;

  final BytesBuilder _bytes = BytesBuilder();
  bool _refused = false;

  int get received => _bytes.length;

  /// Whether this message belongs to this transfer. A begin with no id matches a
  /// message with no id, so an older page still works.
  bool owns(Object? messageId) => (messageId ?? '') == id;

  /// Add one chunk. False means the transfer stops: the cap or the declared size
  /// was passed, and nothing this transfer held is saved.
  bool add(List<int> chunk) {
    if (_refused) return false;
    final total = received + chunk.length;
    if (total > maxBytes || (expectedBytes != null && total > expectedBytes!)) {
      _refused = true;
      _bytes.clear();
      return false;
    }
    _bytes.add(chunk);
    return true;
  }

  /// The whole file, or null when it did not arrive whole.
  Uint8List? finish() {
    if (_refused || (expectedBytes != null && received != expectedBytes)) {
      _bytes.clear();
      return null;
    }
    return _bytes.takeBytes();
  }
}
