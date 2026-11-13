import 'dart:async';
import 'dart:ffi';
import 'dart:io';
import 'dart:math';

import 'package:ffi/ffi.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The phone-side transport. It runs the iroh forwarding loop inside this
/// process, because a standalone dumbpipe process aborts on Android without the
/// Java VM and application context.
abstract class PipeTransport {
  Future<void> start(String ticket, int port);
  Future<void> stop();
  bool get running;
  String? get error;
}

/// The ticket itself is unusable locally, so the saved pairing is worthless.
class PipeRefused implements Exception {
  PipeRefused(this.code);

  final int code;

  @override
  String toString() => 'The pipe refused the ticket (code $code).';
}

typedef _StartNative = Int32 Function(Pointer<Utf8>, Uint16, Pointer<Utf8>);
typedef _Start = int Function(Pointer<Utf8>, int, Pointer<Utf8>);
typedef _StopNative = Void Function();
typedef _Stop = void Function();

class FFIPipeTransport implements PipeTransport {
  static const MethodChannel _channel = MethodChannel('open_imagine/native');
  static const FlutterSecureStorage _storage = FlutterSecureStorage();
  static const _secretKey = 'endpoint_secret';

  _Start? _start;
  _Stop? _stop;
  bool _running = false;
  int _generation = 0;
  String? _error;

  @override
  bool get running => _running;

  @override
  String? get error => _error;

  /// One identity per device. A new one on every start would make the studio
  /// show the same phone as a new device after each restart.
  Future<String> _identity() async {
    final stored = await _storage.read(key: _secretKey);
    if (stored != null && RegExp(r'^[0-9a-f]{64}$').hasMatch(stored)) {
      return stored;
    }
    final random = Random.secure();
    final secret = List.generate(
      32,
      (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
    await _storage.write(key: _secretKey, value: secret);
    return secret;
  }

  Future<void> _load() async {
    if (_start != null) return;
    final directory =
        await _channel.invokeMethod<String>('nativeLibraryDir') ?? '';
    final library = DynamicLibrary.open('$directory/libopenimagine_pipe.so');
    _start = library.lookupFunction<_StartNative, _Start>('oi_pipe_start');
    _stop = library.lookupFunction<_StopNative, _Stop>('oi_pipe_stop');
  }

  @override
  Future<void> start(String ticket, int port) async {
    final generation = ++_generation;
    _stopCurrent();
    _error = null;
    await _load();
    if (generation != _generation) return;
    final identity = await _identity();
    if (generation != _generation) return;
    final text = ticket.toNativeUtf8();
    final secret = identity.toNativeUtf8();
    try {
      final code = _start!(text, port, secret);
      if (code != 0) {
        throw PipeRefused(code);
      }
    } finally {
      malloc.free(text);
      malloc.free(secret);
    }
    _running = true;
    try {
      await _waitForPort(port, generation);
    } catch (error) {
      if (generation != _generation) return;
      _running = false;
      _error = '$error';
      rethrow;
    }
  }

  @override
  Future<void> stop() async {
    _generation++;
    _stopCurrent();
  }

  void _stopCurrent() {
    _stop?.call();
    _running = false;
  }

  Future<void> _waitForPort(int port, int generation) async {
    final deadline = DateTime.now().add(const Duration(seconds: 6));
    while (generation == _generation && DateTime.now().isBefore(deadline)) {
      try {
        final socket = await Socket.connect(
          InternetAddress.loopbackIPv4,
          port,
          timeout: const Duration(seconds: 1),
        );
        socket.destroy();
        return;
      } on SocketException {
        await Future<void>.delayed(const Duration(milliseconds: 250));
      }
    }
    if (generation != _generation) return;
    throw TimeoutException('The studio did not answer through the ticket.');
  }
}
