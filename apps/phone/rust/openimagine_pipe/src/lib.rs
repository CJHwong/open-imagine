//! The phone side of a dumbpipe connection, in this process.
//!
//! A standalone dumbpipe process aborts on Android because iroh needs the Java
//! VM and application context for DNS. This library receives both from
//! MainActivity, then runs the same connect-tcp loop as dumbpipe: bind a local
//! TCP port and forward every accepted connection to the ticket's endpoint.

use std::ffi::{c_char, c_int, c_void, CStr};
use std::str::FromStr;
use std::sync::{Mutex, Once};

use anyhow::{Context, Result};
use iroh::{endpoint::presets, Endpoint, EndpointAddr, SecretKey};
use iroh_tickets::endpoint::EndpointTicket;
use jni::objects::JObject;
use jni::JNIEnv;
use tokio::net::TcpListener;
use tokio_util::sync::CancellationToken;

mod protocol;

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
    let token = CancellationToken::new();
    let cancel = token.clone();
    runtime.spawn(async move {
        let _ = run(ticket, port, secret, cancel).await;
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
    port: u16,
    secret: SecretKey,
    token: CancellationToken,
) -> Result<()> {
    let endpoint = Endpoint::builder(presets::N0)
        .secret_key(secret)
        .alpns(vec![ALPN.to_vec()])
        .bind()
        .await?;
    let listener = TcpListener::bind(("127.0.0.1", port))
        .await
        .with_context(|| format!("cannot bind 127.0.0.1:{port}"))?;
    let addr = ticket.endpoint_addr();
    loop {
        let accepted = tokio::select! {
            _ = token.cancelled() => break,
            result = listener.accept() => result,
        };
        let Ok((tcp, _)) = accepted else {
            continue;
        };
        let endpoint = endpoint.clone();
        let addr = addr.clone();
        tokio::spawn(async move {
            // A forward ends when either side closes. The next connection opens
            // its own, so the error carries no action here.
            let _ = forward(tcp, endpoint, addr).await;
        });
    }
    endpoint.close().await;
    Ok(())
}

async fn forward(tcp: tokio::net::TcpStream, endpoint: Endpoint, addr: EndpointAddr) -> Result<()> {
    let (mut tcp_read, mut tcp_write) = tcp.into_split();
    let connection = endpoint.connect(addr, ALPN).await?;
    let (mut send, mut recv) = connection.open_bi().await?;
    send.write_all(&HANDSHAKE).await?;
    let up = async {
        tokio::io::copy(&mut tcp_read, &mut send).await?;
        send.finish()?;
        Ok::<_, std::io::Error>(())
    };
    let down = async {
        tokio::io::copy(&mut recv, &mut tcp_write).await?;
        Ok::<_, std::io::Error>(())
    };
    let _ = tokio::join!(up, down);
    Ok(())
}
