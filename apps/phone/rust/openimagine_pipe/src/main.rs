//! The Mac side of the pipe: generate a stable ticket, or listen for a phone.
//!
//! `generate-ticket` derives the ticket from IROH_SECRET without starting a
//! listener. `listen --port N` accepts iroh connections and forwards each one to
//! 127.0.0.1:N, which is the studio.

mod protocol;
mod relay;

use std::collections::HashMap;

use std::path::PathBuf;
use std::str::FromStr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use anyhow::{bail, Context, Result};
use iroh::{endpoint::presets, Endpoint, SecretKey};
use iroh_tickets::endpoint::EndpointTicket;
use tokio::io::AsyncReadExt;
use tokio::net::TcpStream;

use protocol::{transport, ALPN, HANDSHAKE};

fn secret_text() -> Result<String> {
    let text = std::env::var("IROH_SECRET").context("IROH_SECRET is not set")?;
    SecretKey::from_str(&text).context("IROH_SECRET is not a 32 byte hex key")?;
    Ok(text)
}

fn secret() -> Result<SecretKey> {
    SecretKey::from_str(&secret_text()?).context("IROH_SECRET is not a 32 byte hex key")
}

fn ticket_for(secret: &SecretKey) -> EndpointTicket {
    EndpointTicket::new(iroh::EndpointAddr::new(secret.public()))
}

async fn generate_ticket() -> Result<()> {
    println!("{}", ticket_for(&secret()?));
    Ok(())
}

async fn listen(port: u16, identity: Option<PathBuf>) -> Result<()> {
    let text = secret_text()?;
    let secret = SecretKey::from_str(&text).context("IROH_SECRET is not a 32 byte hex key")?;
    let ticket = ticket_for(&secret);
    let endpoint = Endpoint::builder(presets::N0)
        .secret_key(secret)
        .alpns(vec![ALPN.to_vec()])
        .transport_config(transport())
        .bind()
        .await?;
    println!("{ticket}");
    // The parent holds the write end of stdin. When it dies, the read sees EOF
    // and this listener exits, so a killed server cannot leave a listener with
    // an old identity behind.
    let mut stdin = tokio::io::stdin();
    let mut byte = [0u8; 1];
    let mut ticker = tokio::time::interval(Duration::from_secs(2));
    // One device is one row. Its browser opens several connections at once,
    // so count them and report the device active while any of them is.
    let active: Arc<Mutex<HashMap<String, usize>>> = Arc::new(Mutex::new(HashMap::new()));
    loop {
        let incoming = tokio::select! {
            _ = ticker.tick() => {
                if let Some(path) = &identity {
                    let stale = std::fs::read_to_string(path)
                        .map(|current| current.trim() != text)
                        .unwrap_or(true);
                    if stale {
                        break;
                    }
                }
                continue;
            }
            _ = stdin.read(&mut byte) => break,
            incoming = endpoint.accept() => incoming,
            _ = tokio::signal::ctrl_c() => break,
        };
        let Some(incoming) = incoming else {
            break;
        };
        let Ok(accepting) = incoming.accept() else {
            continue;
        };
        let active = Arc::clone(&active);
        tokio::spawn(async move {
            let Ok(connection) = accepting.await else {
                return;
            };
            let remote = connection.remote_id().to_string();
            if let Ok(mut devices) = active.lock() {
                *devices.entry(remote.clone()).or_insert(0) += 1;
            }
            device(&remote, "active");
            serve_connection(connection, port).await;
            let quiet = active
                .lock()
                .ok()
                .map(|mut devices| match devices.get_mut(&remote) {
                    Some(count) if *count > 1 => {
                        *count -= 1;
                        false
                    }
                    Some(_) => {
                        devices.remove(&remote);
                        true
                    }
                    None => false,
                })
                .unwrap_or(false);
            if quiet {
                device(&remote, "idle");
            }
        });
    }
    endpoint.close().await;
    // The blocking stdin read never returns while the parent lives, and a runtime
    // shutdown waits for it. The endpoint is closed, so leave now.
    std::process::exit(0);
}

fn device(id: &str, state: &str) {
    let at = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs())
        .unwrap_or(0);
    println!("{{\"kind\":\"device\",\"id\":\"{id}\",\"state\":\"{state}\",\"at\":{at}}}");
}

/// Every request a phone sends on one connection, each on its own stream, until it closes.
///
/// A current phone keeps one connection and opens a stream per request; an older one opens a
/// connection per request. Both end here when the phone closes. Holding the connection until
/// then also keeps the end of the last answer: dropping it as soon as a forward finished closed
/// it with that answer still in flight.
async fn serve_connection(connection: iroh::endpoint::Connection, port: u16) {
    eprintln!("listener: connection accepted");
    while let Ok((send, recv)) = connection.accept_bi().await {
        tokio::spawn(async move {
            if let Err(error) = forward_stream(send, recv, port).await {
                eprintln!("listener: forward failed: {error:#}");
            }
        });
    }
    eprintln!(
        "listener: connection closed: {:?}",
        connection.close_reason()
    );
}

async fn forward_stream(
    send: iroh::endpoint::SendStream,
    mut recv: iroh::endpoint::RecvStream,
    port: u16,
) -> Result<()> {
    let mut handshake = [0u8; HANDSHAKE.len()];
    recv.read_exact(&mut handshake).await?;
    if handshake != HANDSHAKE {
        bail!("invalid handshake");
    }
    let tcp = TcpStream::connect(("127.0.0.1", port))
        .await
        .with_context(|| format!("cannot connect to 127.0.0.1:{port}"))?;
    let (tcp_read, tcp_write) = tcp.into_split();
    relay::relay(recv, send, tcp_read, tcp_write).await?;
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    let arguments: Vec<String> = std::env::args().collect();
    match arguments.get(1).map(String::as_str) {
        Some("generate-ticket") => generate_ticket().await,
        Some("listen") => {
            let port = arguments
                .windows(2)
                .find(|pair| pair[0] == "--port")
                .and_then(|pair| pair[1].parse::<u16>().ok())
                .context("listen needs --port N")?;
            let identity = arguments
                .windows(2)
                .find(|pair| pair[0] == "--identity")
                .map(|pair| PathBuf::from(&pair[1]));
            listen(port, identity).await
        }
        _ => {
            eprintln!("usage: openimagine-pipe generate-ticket | listen --port N");
            std::process::exit(2);
        }
    }
}
