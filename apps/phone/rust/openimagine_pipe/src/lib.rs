//! The phone side of a dumbpipe connection, in this process.
//!
//! A standalone dumbpipe process aborts on Android because iroh needs the Java
//! VM and application context for DNS. This library receives both from
//! MainActivity, then runs the same connect-tcp loop as dumbpipe: bind a local
//! TCP port and forward every accepted connection to the ticket's endpoint.

use std::ffi::{c_char, c_int, c_void, CStr};
use std::str::FromStr;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, Once};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::Result;
use iroh::{
    endpoint::{presets, Connection},
    Endpoint, EndpointAddr, SecretKey,
};
use iroh_tickets::endpoint::EndpointTicket;
use jni::objects::JObject;
use jni::JNIEnv;
use tokio::net::TcpListener;
use tokio_util::sync::CancellationToken;

mod log;
mod protocol;
mod relay;

use protocol::{transport, ALPN, HANDSHAKE};

struct Pipe {
    token: CancellationToken,
    runtime: tokio::runtime::Runtime,
}

static PIPE: Mutex<Option<Pipe>> = Mutex::new(None);
static INIT: Once = Once::new();

/// Store the Java VM and application context that iroh's Android resolver needs.
#[no_mangle]
pub extern "system" fn Java_com_hoss_open_1imagine_1phone_MainActivity_nativeInit(
    env: JNIEnv,
    _this: JObject,
    context: JObject,
) {
    // An activity relaunch calls onCreate again. The Android context store
    // panics on a second initialization, so set it once per process.
    INIT.call_once(|| {
        let Ok(vm) = env.get_java_vm() else {
            return;
        };
        let Ok(global) = env.new_global_ref(context) else {
            return;
        };
        // A local reference dies with this call. The resolver uses the context on
        // other threads, so keep a global reference for the process lifetime.
        let context_ptr = global.as_raw() as *mut c_void;
        std::mem::forget(global);
        unsafe {
            ndk_context::initialize_android_context(
                vm.get_java_vm_pointer() as *mut c_void,
                context_ptr,
            );
        }
    });
}

/// Start forwarding the local port to the ticket. 0 means the runtime started.
/// `secret` is the device's own stable 32 byte hex key, so one device keeps one
/// identity across app restarts.
///
/// # Safety
/// Non-null pointers must refer to valid, null-terminated strings for this call.
#[no_mangle]
pub unsafe extern "C" fn oi_pipe_start(
    ticket: *const c_char,
    port: u16,
    secret: *const c_char,
) -> c_int {
    if ticket.is_null() || secret.is_null() {
        return -1;
    }
    let Ok(text) = (unsafe { CStr::from_ptr(ticket) }).to_str() else {
        return -2;
    };
    let Ok(ticket) = text.parse::<EndpointTicket>() else {
        return -3;
    };
    let Ok(secret_text) = (unsafe { CStr::from_ptr(secret) }).to_str() else {
        return -6;
    };
    let Ok(secret) = SecretKey::from_str(secret_text) else {
        return -6;
    };
    let Ok(runtime) = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
    else {
        return -4;
    };
    oi_pipe_stop();
    // Bind before returning. A port already in use and an endpoint that cannot start
    // are answers the app can show; a task that fails after this call returns is a
    // timeout six seconds later with no cause.
    let endpoint = match runtime.block_on(
        Endpoint::builder(presets::N0)
            .secret_key(secret)
            .alpns(vec![ALPN.to_vec()])
            .transport_config(transport())
            .bind(),
    ) {
        Ok(endpoint) => endpoint,
        Err(_) => return -7,
    };
    let listener = match runtime.block_on(TcpListener::bind(("127.0.0.1", port))) {
        Ok(listener) => listener,
        Err(_) => return -8,
    };
    let token = CancellationToken::new();
    let cancel = token.clone();
    runtime.spawn(async move {
        if let Err(error) = run(ticket, endpoint, listener, cancel).await {
            log::line(&format!("listener stopped: {error}"));
        }
    });
    if let Ok(mut slot) = PIPE.lock() {
        *slot = Some(Pipe { token, runtime });
        0
    } else {
        -5
    }
}

/// Stop the listener and shut its runtime down. Safe to call more than once.
#[no_mangle]
pub extern "C" fn oi_pipe_stop() {
    let pipe = PIPE.lock().ok().and_then(|mut slot| slot.take());
    if let Some(pipe) = pipe {
        pipe.token.cancel();
        pipe.runtime
            .shutdown_timeout(std::time::Duration::from_secs(1));
    }
}

async fn run(
    ticket: EndpointTicket,
    endpoint: Endpoint,
    listener: TcpListener,
    token: CancellationToken,
) -> Result<()> {
    let studio = Arc::new(Studio {
        endpoint: endpoint.clone(),
        addr: ticket.endpoint_addr().clone(),
        connection: tokio::sync::Mutex::new(None),
        awake: Awake::new(now_ms()),
    });
    let ticking = Arc::clone(&studio);
    tokio::spawn(async move {
        let mut ticker = tokio::time::interval(Duration::from_secs(1));
        loop {
            ticker.tick().await;
            ticking.awake.tick(now_ms());
        }
    });
    // A listener that keeps failing would spin a core while the studio is unreachable.
    let mut failures: u32 = 0;
    loop {
        let accepted = tokio::select! {
            _ = token.cancelled() => break,
            result = listener.accept() => result,
        };
        let (tcp, _) = match accepted {
            Ok(pair) => {
                failures = 0;
                pair
            }
            Err(error) => {
                failures += 1;
                if failures >= 32 {
                    return Err(anyhow::anyhow!(
                        "the listener failed 32 times in a row: {error}"
                    ));
                }
                tokio::time::sleep(std::time::Duration::from_millis(
                    100 * u64::from(failures.min(10)),
                ))
                .await;
                continue;
            }
        };
        let studio = Arc::clone(&studio);
        tokio::spawn(async move {
            // A forward ends when either side closes. The cause is kept as one line, with
            // no ticket or prompt in it.
            match forward(tcp, &studio).await {
                Err(error) if !asker_left(&error) => {
                    log::line(&format!("forward failed: {error:#}"))
                }
                _ => {}
            }
        });
    }
    endpoint.close().await;
    Ok(())
}

/// The studio machine and the one connection every request shares.
///
/// A connection per request sent each handshake to the cached direct address only, and when the
/// shared Wi-Fi dropped traffic between the two machines, every new request waited out the
/// handshake timeout. One long-lived connection already holds the relay path, so when the
/// direct path dies its requests move to the relay with no new handshake.
struct Studio {
    endpoint: Endpoint,
    addr: EndpointAddr,
    connection: tokio::sync::Mutex<Option<Connection>>,
    awake: Awake,
}

/// A gap in the wall clock between two ticks this long means the process did not run.
const PAUSED_AFTER_MS: u64 = 3000;

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_millis() as u64)
        .unwrap_or(0)
}

/// Whether the process stopped running since the last request.
///
/// Android freezes the app while it is in the background, the image picker included. A frozen
/// process answers nothing, so the studio closes the connection after its idle limit, but the
/// phone's own timers stop with it and it still holds that connection when it wakes. Requests
/// sent then went into the dead connection and failed: an upload picked in the picker was lost.
/// The wall clock keeps running through a freeze and a deep sleep, so a gap between ticks shows
/// both.
struct Awake {
    last: AtomicU64,
    paused: AtomicBool,
}

impl Awake {
    fn new(now: u64) -> Self {
        Awake {
            last: AtomicU64::new(now),
            paused: AtomicBool::new(false),
        }
    }

    fn tick(&self, now: u64) {
        let last = self.last.swap(now, Ordering::SeqCst);
        if now.saturating_sub(last) > PAUSED_AFTER_MS {
            self.paused.store(true, Ordering::SeqCst);
        }
    }

    /// True once after a pause. A request can arrive before the first tick after a freeze, so
    /// it reads the clock itself.
    fn take_pause(&self, now: u64) -> bool {
        self.tick(now);
        self.paused.swap(false, Ordering::SeqCst)
    }
}

/// The WebView or the app closed its socket before the answer was all written.
///
/// That ends a request normally: the app's server check reads only the status line and
/// closes. Only the local TCP socket carries an operating system error code. An error from
/// the iroh side has none, so a lost connection to the studio is still reported.
fn asker_left(error: &anyhow::Error) -> bool {
    error.downcast_ref::<std::io::Error>().is_some_and(|error| {
        error.raw_os_error().is_some()
            && matches!(
                error.kind(),
                std::io::ErrorKind::BrokenPipe | std::io::ErrorKind::ConnectionReset
            )
    })
}

impl Studio {
    /// A new stream to the studio, on the shared connection, or on a new one when that has closed.
    async fn open(&self) -> Result<(iroh::endpoint::SendStream, iroh::endpoint::RecvStream)> {
        let mut slot = self.connection.lock().await;
        if self.awake.take_pause(now_ms()) {
            if let Some(connection) = slot.take() {
                log::line("the app was paused, reconnecting");
                connection.close(0u32.into(), b"paused");
            }
        }
        if let Some(connection) = slot.as_ref() {
            match connection.close_reason() {
                None => match connection.open_bi().await {
                    Ok(pair) => return Ok(pair),
                    Err(error) => log::line(&format!("stream refused, reconnecting: {error}")),
                },
                Some(reason) => log::line(&format!("connection gone, reconnecting: {reason}")),
            }
        }
        let started = std::time::Instant::now();
        log::line("connecting");
        let connection = match self.endpoint.connect(self.addr.clone(), ALPN).await {
            Ok(connection) => connection,
            Err(error) => {
                log::line(&format!(
                    "connect failed after {} ms: {error:#}",
                    started.elapsed().as_millis()
                ));
                return Err(error.into());
            }
        };
        log::line(&format!(
            "connected in {} ms",
            started.elapsed().as_millis()
        ));
        tokio::spawn(log::watch_paths(
            connection.clone(),
            "connection".to_string(),
        ));
        let pair = connection.open_bi().await?;
        *slot = Some(connection);
        Ok(pair)
    }
}

async fn forward(tcp: tokio::net::TcpStream, studio: &Studio) -> Result<()> {
    let (tcp_read, tcp_write) = tcp.into_split();
    let (mut send, recv) = studio.open().await?;
    send.write_all(&HANDSHAKE).await?;
    relay::relay(tcp_read, tcp_write, recv, send).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{asker_left, Awake, PAUSED_AFTER_MS};

    #[test]
    fn a_gap_between_ticks_marks_one_pause() {
        let awake = Awake::new(1_000);
        awake.tick(2_000);
        assert!(!awake.take_pause(3_000));
        awake.tick(3_000 + PAUSED_AFTER_MS + 1);
        assert!(awake.take_pause(3_000 + PAUSED_AFTER_MS + 2));
        assert!(!awake.take_pause(3_000 + PAUSED_AFTER_MS + 3));
    }

    #[test]
    fn a_request_after_a_freeze_sees_the_pause_before_any_tick() {
        let awake = Awake::new(1_000);
        assert!(awake.take_pause(1_000 + 60_000));
    }

    #[test]
    fn a_clock_set_back_is_no_pause() {
        let awake = Awake::new(10_000);
        assert!(!awake.take_pause(5_000));
    }

    #[test]
    fn a_socket_the_asker_closed_is_not_a_failure() {
        // EPIPE is 32 on both, ECONNRESET is 104 on Android and Linux, 54 on macOS.
        let reset = if cfg!(target_os = "macos") { 54 } else { 104 };
        for code in [32, reset] {
            let error = anyhow::Error::from(std::io::Error::from_raw_os_error(code));
            assert!(asker_left(&error), "os error {code}");
        }
    }

    #[test]
    fn a_lost_studio_connection_is_still_a_failure() {
        let lost = std::io::Error::new(std::io::ErrorKind::ConnectionReset, "connection lost");
        assert!(!asker_left(&anyhow::Error::from(lost)));
        let timeout = std::io::Error::new(std::io::ErrorKind::TimedOut, "timed out");
        assert!(!asker_left(&anyhow::Error::from(timeout)));
    }
}
