class Pairing {
  const Pairing({required this.ticket, required this.port});

  final String ticket;
  final int port;

  static Pairing? parse(String raw) {
    final uri = Uri.tryParse(raw.trim());
    if (uri == null || uri.scheme != 'openimagine' || uri.host != 'pair') {
      return null;
    }
    if (uri.queryParameters['v'] != '1') return null;
    final ticket = uri.queryParameters['ticket'] ?? '';
    final port = int.tryParse(uri.queryParameters['port'] ?? '');
    final shaped = ticket.startsWith('endpoint') || ticket.startsWith('node');
    if (!shaped || ticket.length <= 40) return null;
    if (port == null || port < 1 || port > 65535) return null;
    return Pairing(ticket: ticket, port: port);
  }
}
