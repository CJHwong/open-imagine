//! The dumbpipe wire contract: the ALPN, the handshake, and the transport both ends share.

pub const ALPN: &[u8] = b"DUMBPIPEV0";
pub const HANDSHAKE: [u8; 5] = *b"hello";

use std::time::Duration;

use iroh::endpoint::QuicTransportConfig;

/// How both ends notice a dead path. iroh keeps the relay path open as a backup and moves a
/// connection onto it only when the direct path is abandoned, and it abandons a path only when
/// that path's idle timer fires: 15 s by default, with a 5 s heartbeat. The phone and the studio
/// machine share a Wi-Fi network that drops traffic between them for 20 to 45 s at a time while
/// both still reach the internet, so every request stalled for the whole drop. A 1 s heartbeat
/// and a 3 s idle limit move a connection onto the relay about 3 s into a drop. The relay path
/// keeps iroh's own 30 s limit.
pub fn transport() -> QuicTransportConfig {
    QuicTransportConfig::builder()
        .default_path_keep_alive_interval(Duration::from_secs(1))
        .default_path_max_idle_timeout(Duration::from_secs(3))
        .keep_alive_interval(Duration::from_secs(2))
        .build()
}
