//! The phone side of a dumbpipe connection, in this process.
//!
//! A standalone dumbpipe process aborts on Android because iroh needs the Java
//! VM and application context for DNS. This library receives both from
//! MainActivity, then runs the same connect-tcp loop as dumbpipe: bind a local
//! TCP port and forward every accepted connection to the ticket's endpoint.

use std::ffi::{c_char, c_int, c_void, CStr};
use std::str::FromStr;
use std::sync::{Mutex, Once};

use anyhow::Result;
use iroh::{endpoint::presets, Endpoint, EndpointAddr, SecretKey};
use iroh_tickets::endpoint::EndpointTicket;
use jni::objects::JObject;
use jni::JNIEnv;
use tokio::net::TcpListener;
use tokio_util::sync::CancellationToken;

mod protocol;
mod relay;

use protocol::{ALPN, HANDSHAKE};

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
            eprintln!("listener stopped: {error}");
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
    let addr = ticket.endpoint_addr();
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
        let endpoint = endpoint.clone();
        let addr = addr.clone();
        tokio::spawn(async move {
            // A forward ends when either side closes. The next connection opens its
            // own; the cause is kept as one line, with no ticket or prompt in it.
            if let Err(error) = forward(tcp, endpoint, addr).await {
                eprintln!("forward failed: {error}");
            }
        });
    }
    endpoint.close().await;
    Ok(())
}

async fn forward(tcp: tokio::net::TcpStream, endpoint: Endpoint, addr: EndpointAddr) -> Result<()> {
    let (tcp_read, tcp_write) = tcp.into_split();
    let connection = endpoint.connect(addr, ALPN).await?;
    let (mut send, recv) = connection.open_bi().await?;
    send.write_all(&HANDSHAKE).await?;
    relay::relay(tcp_read, tcp_write, recv, send).await?;
    Ok(())
}
