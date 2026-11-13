import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'l10n/app_localizations.dart';
import 'notifications.dart';
import 'pairing.dart';
import 'pipe.dart';
import 'probe.dart';
import 'scanner.dart';
import 'studio_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key, this.transport, this.probe});

  final PipeTransport? transport;
  final Future<bool> Function(int)? probe;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  static const _storage = FlutterSecureStorage();
  static const _key = 'pairing';

  late final PipeTransport _pipe = widget.transport ?? FFIPipeTransport();
  int _connectionVersion = 0;
  Pairing? _pairing;
  bool _loading = true;
  bool _busy = false;
  bool _connected = false;
  String _problem = "";
  final TextEditingController _debugTicket = TextEditingController();
  final TextEditingController _debugPort = TextEditingController(text: "8877");

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    Pairing? pairing;
    try {
      final raw = await _storage.read(key: _key);
      pairing = raw == null ? null : Pairing.parse(raw);
    } on Object {
      pairing = null;
    }
    if (!mounted) return;
    setState(() {
      _pairing = pairing;
      _loading = false;
    });
    if (pairing != null) await _connect(pairing, open: true);
  }

  Future<bool> _reachable(Pairing pairing) =>
      (widget.probe ?? probeStudio)(pairing.port);

  bool _current(int version) => mounted && version == _connectionVersion;

  Future<void> _connect(Pairing pairing, {bool open = false}) async {
    final version = ++_connectionVersion;
    // A pairing is the first moment this app has a studio worth a notice about.
    unawaited(RunNotifications.requestPermission());
    setState(() {
      _busy = true;
      _connected = false;
      _problem = "";
    });
    try {
      await _pipe.start(pairing.ticket, pairing.port);
      if (!_current(version)) return;
      final reachable = await _reachable(pairing);
      if (!_current(version)) return;
      if (!reachable) {
        throw StateError("The studio did not answer.");
      }
      if (mounted) setState(() => _connected = true);
      if (open) await _pushStudio(pairing);
    } catch (error) {
      if (!_current(version)) return;
      if (kDebugMode) debugPrint('Connect failed: $error');
      await _pipe.stop();
      if (!_current(version)) return;
      // A slow studio must not cost the pairing. Only a ticket this process
      // cannot use at all is worth deleting.
      final refused = error is PipeRefused;
      if (refused) await _storage.delete(key: _key);
      if (_current(version)) {
        setState(() {
          if (refused) _pairing = null;
          _connected = false;
          _problem = AppLocalizations.of(context).couldNotReach;
        });
      }
    } finally {
      if (_current(version)) setState(() => _busy = false);
    }
  }

  Future<void> _pushStudio(Pairing pairing) async {
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => StudioPage(port: pairing.port, onLost: _lost),
      ),
    );
  }

  Future<void> _lost() async {
    await _pipe.stop();
    if (!mounted) return;
    // A dropped connection is not a lost studio. Keep the pairing so the next
    // launch, and the card here, can reconnect.
    setState(() {
      _connected = false;
      _problem = AppLocalizations.of(context).connectionEnded;
    });
  }

  Future<void> _scan() async {
    final pairing = await Navigator.of(
      context,
    ).push<Pairing>(MaterialPageRoute(builder: (_) => const ScannerPage()));
    if (pairing == null) return;
    await _storage.write(key: _key, value: _pairingUri(pairing));
    if (!mounted) return;
    setState(() => _pairing = pairing);
    await _connect(pairing, open: true);
  }

  Future<void> _forget() async {
    _connectionVersion++;
    setState(() {
      _pairing = null;
      _busy = false;
      _connected = false;
      _problem = "";
    });
    await _pipe.stop();
    await _storage.delete(key: _key);
  }

  Future<void> _open() async {
    final pairing = _pairing;
    if (pairing == null || _busy) return;
    if (!_connected) await _connect(pairing);
    if (!mounted || _pairing != pairing || !_connected) return;
    await _pushStudio(_pairing!);
  }

  Future<void> _useDebugCode() async {
    final pairing = Pairing.parse(
      'openimagine://pair?v=1&ticket=${_debugTicket.text.trim()}&port=${_debugPort.text.trim()}',
    );
    if (pairing == null) return;
    await _storage.write(key: _key, value: _pairingUri(pairing));
    if (!mounted) return;
    setState(() => _pairing = pairing);
    await _connect(pairing, open: true);
  }

  @override
  void dispose() {
    _connectionVersion++;
    _pipe.stop();
    _debugTicket.dispose();
    _debugPort.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pairing = _pairing;
    final theme = Theme.of(context);
    final text = AppLocalizations.of(context);
    if (_loading) {
      return Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(28, 36, 28, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [_brand(theme)],
            ),
          ),
        ),
      );
    }
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(28, 36, 28, 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _brand(theme),
              const SizedBox(height: 44),
              Text(
                pairing == null ? text.connectAStudio : text.yourStudio,
                style: theme.textTheme.headlineMedium,
              ),
              const SizedBox(height: 12),
              if (pairing == null) ...[
                Text(
                  _problem.isEmpty ? text.scanHint : _problem,
                  style: theme.textTheme.bodyLarge?.copyWith(color: _ink2),
                ),
                const SizedBox(height: 32),
                FilledButton(
                  onPressed: _busy ? null : _scan,
                  child: Text(text.scanTheCode),
                ),
              ] else ...[
                _StudioCard(
                  label: _busy
                      ? text.connecting
                      : _connected
                      ? text.connected
                      : text.notConnected,
                  busy: _busy,
                  connected: _connected,
                  onTap: _busy ? null : _open,
                ),
                if (_problem.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(
                    _problem,
                    style: theme.textTheme.bodySmall?.copyWith(color: _ink2),
                  ),
                ],
                const SizedBox(height: 6),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    TextButton(
                      onPressed: _busy ? null : _scan,
                      style: TextButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 14),
                      ),
                      child: Text(text.scanNewCode),
                    ),
                    Container(width: 1, height: 14, color: _line),
                    TextButton(
                      onPressed: _forget,
                      style: TextButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 14),
                      ),
                      child: Text(text.disconnect),
                    ),
                  ],
                ),
              ],
              if (kDebugMode) ...[
                const SizedBox(height: 40),
                const Divider(height: 1, color: _line),
                const SizedBox(height: 20),
                TextField(
                  controller: _debugTicket,
                  decoration: const InputDecoration(
                    labelText: 'Ticket (debug)',
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: _debugPort,
                  decoration: const InputDecoration(labelText: 'Port (debug)'),
                  keyboardType: TextInputType.number,
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: _useDebugCode,
                  child: const Text('Use this code'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _brand(ThemeData theme) {
    return Row(
      children: [
        Image.asset('assets/logo.png', width: 26, height: 26),
        const SizedBox(width: 10),
        Text(
          'OPEN IMAGINE',
          style: theme.textTheme.bodySmall?.copyWith(
            letterSpacing: 2.4,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }

  String _pairingUri(Pairing pairing) =>
      'openimagine://pair?v=1&ticket=${pairing.ticket}&port=${pairing.port}';
}

const _ink2 = Color(0xFF4D4D4D);
const _line = Color(0xFFC7C1B8);
const _green = Color(0xFF3B6B4A);
const _amber = Color(0xFF9A6B2F);

/// The paired studio is the page's one control. Tap it to open the studio.
class _StudioCard extends StatelessWidget {
  const _StudioCard({
    required this.label,
    required this.busy,
    required this.connected,
    this.onTap,
  });

  final String label;
  final bool busy;
  final bool connected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: _line),
          ),
          child: Row(
            children: [
              if (busy)
                const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(
                    strokeWidth: 1.6,
                    color: _amber,
                  ),
                )
              else
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: connected ? _green : _line,
                    shape: BoxShape.circle,
                  ),
                ),
              const SizedBox(width: 14),
              Expanded(
                child: Text(
                  label,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
              if (!busy)
                const Icon(Icons.chevron_right, size: 20, color: _ink2),
            ],
          ),
        ),
      ),
    );
  }
}
