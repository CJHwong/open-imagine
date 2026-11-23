//! One timestamped line per connection event, on both ends of the pipe.
//!
//! Each line names a connection, a path, a close reason or a failed forward. None carries a
//! ticket, a key, a request or a reply, so a private run leaves nothing of itself here.
//!
//! On Android the line goes to the system log under the tag `openimagine_pipe`, which `adb
//! logcat -s openimagine_pipe` reads. Elsewhere it goes to the file `OPENIMAGINE_PIPE_LOG`
//! names, or to stderr when the variable is unset.

use std::time::{SystemTime, UNIX_EPOCH};

use iroh::endpoint::Connection;

pub fn line(message: &str) {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    write(&format!(
        "{}.{:03} {message}",
        now.as_secs(),
        now.subsec_millis()
    ));
}

/// Log the connection's selected path each time it changes, until the connection closes.
///
/// iroh moves a connection between the direct path and the relay without telling anyone, and
/// the stalls this pipe has had were all a question of which path a request was waiting on.
pub async fn watch_paths(connection: Connection, name: String) {
    let mut ticker = tokio::time::interval(std::time::Duration::from_millis(500));
    let mut last = String::new();
    loop {
        tokio::select! {
            reason = connection.closed() => {
                line(&format!("{name} closed: {reason}"));
                return;
            }
            _ = ticker.tick() => {}
        }
        let paths = connection.paths();
        let selected = paths
            .iter()
            .find(|path| path.is_selected())
            .map(|path| {
                let kind = if path.is_relay() { "relay" } else { "direct" };
                format!("{kind} {:?}", path.remote_addr())
            })
            .unwrap_or_else(|| "none".to_string());
        if selected != last {
            line(&format!(
                "{name} path: {selected} (open paths {})",
                paths.len()
            ));
            last = selected;
        }
    }
}

#[cfg(target_os = "android")]
fn write(text: &str) {
    use std::ffi::{c_char, c_int, CString};

    #[link(name = "log")]
    extern "C" {
        fn __android_log_write(priority: c_int, tag: *const c_char, text: *const c_char) -> c_int;
    }
    const INFO: c_int = 4;
    let Ok(text) = CString::new(text) else {
        return;
    };
    unsafe {
        __android_log_write(INFO, c"openimagine_pipe".as_ptr(), text.as_ptr());
    }
}

#[cfg(not(target_os = "android"))]
fn write(text: &str) {
    use std::io::Write;

    let Some(path) = std::env::var_os("OPENIMAGINE_PIPE_LOG") else {
        eprintln!("{text}");
        return;
    };
    let opened = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path);
    if let Ok(mut file) = opened {
        let _ = writeln!(file, "{text}");
    }
}
