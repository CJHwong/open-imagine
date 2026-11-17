import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:open_imagine_phone/probe.dart';

/// A studio that answers only the Host its own `_trusted_host` accepts, which
/// names the port. A probe that leaves the port out gets a refusal.
Future<HttpServer> studioLikeServer({bool checkHost = true}) async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  server.listen((request) async {
    final trusted = request.headers.value('host') == '127.0.0.1:${server.port}';
    request.response.statusCode = checkHost && !trusted ? 403 : 200;
    await request.response.close();
  });
  return server;
}

void main() {
  test('the probe names the port in the Host a studio trusts', () async {
    final server = await studioLikeServer();
    addTearDown(() => server.close(force: true));

    expect(await probeStudio(server.port), isTrue);
  });

  test('a refusal reads as unreachable', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    server.listen((request) async {
      request.response.statusCode = 403;
      await request.response.close();
    });

    expect(await probeStudio(server.port), isFalse);
  });

  test('a port with no listener reads as unreachable', () async {
    final server = await studioLikeServer();
    final port = server.port;
    await server.close(force: true);

    expect(await probeStudio(port), isFalse);
  });
}
