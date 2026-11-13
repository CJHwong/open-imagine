import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

/// What the run in flight is doing, as `/api/v1/progress` reports it.
class RunProgress {
  const RunProgress({
    required this.running,
    required this.stage,
    required this.step,
    required this.total,
    required this.kind,
  });

  factory RunProgress.fromJson(Map<String, dynamic> json) => RunProgress(
    running: json['running'] == true,
    stage: json['stage'] as String? ?? '',
    step: (json['step'] as num?)?.toInt() ?? 0,
    total: (json['total'] as num?)?.toInt() ?? 0,
    kind: json['kind'] as String? ?? '',
  );

  final bool running;
  final String stage;
  final int step;
  final int total;
  final String kind;

  /// Zero while the backend is still preparing.
  int get percent =>
      total <= 0 ? 0 : (step * 100 / total).round().clamp(0, 100);
}

/// One answer from the progress route.
class ProgressReply {
  const ProgressReply.read(RunProgress this.progress) : hidden = false;

  /// The run belongs to a caller with its own key. Show nothing.
  const ProgressReply.hidden() : progress = null, hidden = true;

  /// No usable answer. Leave the last notice alone.
  const ProgressReply.failed() : progress = null, hidden = false;

  final RunProgress? progress;
  final bool hidden;
}

/// Read the run in flight through the pipe.
Future<ProgressReply> readProgress(
  int port, {
  Duration timeout = const Duration(seconds: 3),
}) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 2);
  try {
    final request = await client
        .getUrl(Uri.parse('http://127.0.0.1:$port/api/v1/progress'))
        .timeout(timeout);
    request.headers.set(HttpHeaders.connectionHeader, 'close');
    final response = await request.close().timeout(timeout);
    if (response.statusCode == HttpStatus.notFound) {
      await response.drain<void>();
      return const ProgressReply.hidden();
    }
    if (response.statusCode != HttpStatus.ok) {
      await response.drain<void>();
      return const ProgressReply.failed();
    }
    final body = await response
        .transform(const Utf8Decoder(allowMalformed: true))
        .join()
        .timeout(timeout);
    final data = jsonDecode(body);
    if (data is! Map<String, dynamic>) return const ProgressReply.failed();
    return ProgressReply.read(RunProgress.fromJson(data));
  } on Object catch (error) {
    if (kDebugMode) debugPrint('Progress read failed: $error');
    return const ProgressReply.failed();
  } finally {
    client.close(force: true);
  }
}

/// Ask the studio for its status through the pipe.
///
/// A raw HTTP/1.0 request keeps one probe on one tunnel connection. The reply
/// is read only to its status line: a keep-alive server may never close.
Future<bool> probeStudio(
  int port, {
  Duration timeout = const Duration(seconds: 15),
}) async {
  Socket? socket;
  StreamIterator<String>? replies;
  try {
    socket = await Socket.connect(
      InternetAddress.loopbackIPv4,
      port,
      timeout: const Duration(seconds: 3),
    );
    socket.write(
      'GET /api/v1/studio HTTP/1.0\r\n'
      'Host: 127.0.0.1\r\n'
      'Connection: close\r\n\r\n',
    );
    await socket.flush();
    replies = StreamIterator(
      socket.cast<List<int>>().transform(
        const Utf8Decoder(allowMalformed: true),
      ),
    );
    final line = StringBuffer();
    while (await replies.moveNext().timeout(timeout)) {
      line.write(replies.current);
      final text = line.toString();
      final end = text.indexOf('\r\n');
      if (end >= 0) {
        return text.substring(0, end).contains(' 200 ');
      }
    }
    return false;
  } on Object catch (error) {
    if (kDebugMode) debugPrint('Probe failed: $error');
    return false;
  } finally {
    await replies?.cancel();
    socket?.destroy();
  }
}
