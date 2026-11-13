//! The dumbpipe wire contract: the ALPN, the handshake and the ticket type.

pub const ALPN: &[u8] = b"DUMBPIPEV0";
pub const HANDSHAKE: [u8; 5] = *b"hello";
