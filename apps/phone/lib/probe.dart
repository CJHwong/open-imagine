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
    // The studio trusts a Host that names its own port, and refuses one without
    // it. The tunnel listens on the studio's port, so it carries this one.
    socket.write(
      'GET /api/v1/studio HTTP/1.0\r\n'
      'Host: 127.0.0.1:$port\r\n'
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

/// The newest operation the studio reports, for a completion notice.
///
/// A finished run leaves the progress route as `running: false`, which says nothing
/// about how it ended. The state route carries the newest operation and its terminal
/// status, so a notice can say "succeeded" or "failed" instead of "finished" for both.
class RunOutcome {
  const RunOutcome({required this.id, required this.status});

  static RunOutcome? fromState(String body) {
    final data = jsonDecode(body);
    if (data is! Map<String, dynamic>) return null;
    final operations = data['operations'];
    if (operations is! List || operations.isEmpty) return null;
    final newest = operations.first;
    if (newest is! Map<String, dynamic>) return null;
    final id = newest['id'];
    final status = newest['status'];
    if (id is! String || id.isEmpty || status is! String) return null;
    return RunOutcome(id: id, status: status);
  }

  final String id;
  final String status;

  /// The first eight characters, which is how the page names an operation.
  String get shortId => id.length <= 8 ? id : id.substring(0, 8);
}

/// Read the newest operation through the pipe. Null when there is none to read.
Future<RunOutcome?> readOutcome(
  int port, {
  Duration timeout = const Duration(seconds: 3),
}) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 2);
  try {
    final request = await client
        .getUrl(Uri.parse('http://127.0.0.1:$port/api/v1/state'))
        .timeout(timeout);
    request.headers.set(HttpHeaders.connectionHeader, 'close');
    final response = await request.close().timeout(timeout);
    if (response.statusCode != HttpStatus.ok) {
      await response.drain<void>();
      return null;
    }
    final body = await response
        .transform(const Utf8Decoder(allowMalformed: true))
        .join()
        .timeout(timeout);
    return RunOutcome.fromState(body);
  } on Object catch (error) {
    if (kDebugMode) debugPrint('Outcome read failed: $error');
    return null;
  } finally {
    client.close(force: true);
  }
}
