# Open Imagine Phone

An Android app for the Open Imagine studio on a Mac. It scans the pairing code that
the studio prints, opens a dumbpipe connection, and shows the full studio page in an
embedded browser. It uses the studio's web icon as its launcher icon.

## What it needs

- The source lives in `apps/phone` in the Open Imagine repository. Run app commands from that directory.
- Flutter 3.44.8, Java 17, Rust 1.93.0, cargo-ndk 4.1.2, and Android NDK 28.2.13676358 build the app.
- `rust-toolchain.toml` installs the pinned Rust tools and Android target through rustup.
- The studio on the Mac. Phone connections start by default; `--connect=off` disables them.
- The Mac runs `dumbpipe` (`brew install dumbpipe`) and prints a QR code at startup.
- The phone runs this app. It builds its own iroh pipe into the APK.

## Build the pipe library

The transport is a Rust library in `rust/openimagine_pipe`. It runs the dumbpipe
forwarding loop in this process, so iroh gets the Java VM and application context that
Android needs for name resolution. A standalone dumbpipe binary aborts without them.

```sh
flutter pub get --enforce-lockfile
./tool/build_pipe.sh
```

This builds `libopenimagine_pipe.so` for `arm64-v8a` and copies it into
`android/app/src/main/jniLibs/arm64-v8a/`. Gradle extracts the library to the native
library directory, and the app loads it with `dart:ffi`.

The library is not committed. A fresh clone needs the script before `flutter run`.

## Run

```sh
flutter run
```

On the Mac:

```sh
uv run studio --port 8765
```

The terminal prints a QR code once the dumbpipe listener is up. Scan it in the app.
The app stores the ticket and starts the pipe at every launch. Press **Open studio**.

The QR carries `openimagine://pair?v=1&ticket=...&port=8765`. The ticket is a
credential that reaches the whole studio, including model settings and public
operations. Rotate the identity file on the Mac and restart to revoke it.

## How it works

1. `MainActivity` loads `libopenimagine_pipe.so` and passes the Java VM and a global
   reference to the application context to `nativeInit`.
2. The app starts `oi_pipe_start(ticket, port, secret)` at launch when a ticket is stored. The
   Rust side binds `127.0.0.1:<port>` and forwards every accepted TCP connection to the
   ticket's iroh endpoint.
3. `StudioPage` loads `http://127.0.0.1:<port>` in `webview_flutter`. The studio's own
   Origin and Host check accepts that address, so no server setting changes.
4. The ticket stays in `flutter_secure_storage`, not in shared preferences. The Mac
   keeps one ticket from its identity file, so the stored pairing survives restarts.

`PipeTransport` is the transport boundary. A Tailcat adapter can replace the iroh one
without touching the scanner or the browser.

Disconnect stays available while the app connects. It stops the transport and
removes the stored pairing. A cancelled attempt cannot open the studio later.
Scan the code again to reconnect.

## Microphone, files and clipboard

The studio uses the same controls on desktop and phone.
Android asks for microphone access when you select Record.
The manifest also grants audio routing access, which Chromium requires before
it opens a recording device. This permission needs no separate runtime prompt.
If you deny access, the page stops the pending recording. You can try Record again.
If Android stops asking, allow microphone access in Android Settings.

Reference controls open the Android file selector. The selector keeps the page's
file filters and supports multiple files when the selected mode permits them.
Cancel returns to the form without a reference change.

Paste appears beside image and video reference labels when compatible media exists.
The app checks clipboard metadata
while its window has focus. It reads copied media only after you select Paste.
Empty and unsupported clipboards show no Paste button. Voice and music show no Paste button.
Browsers without clipboard metadata keep their standard paste and file selection controls.
The Android WebView uses native composition to avoid delayed page paint after asynchronous updates.
The page keeps Paste active until media import finishes. It requests frames during
that work, so the reference appears without another touch or scroll.
Native clipboard reads accept image, audio and video content URIs, up to 32 MB.
The app keeps these bytes in memory. It creates no clipboard cache file.

## Verified

On an arm64 emulator on 2026-11-12, the app connected to a studio through the relay,
loaded the real page, and showed the image workspace. The standalone dumbpipe CLI was
also tested and aborts on Android; that path is removed.

On 2026-11-14, an Android emulator passed native input checks through `StudioPage`
against the studio stub. The checks cover file selection, cancellation, reference
pixels, clipboard metadata and explicit clipboard paste. Android also
shows the microphone prompt, ends a denied request and grants a retry.
Recording starts on the emulator and the user's physical phone.
The physical phone also shows a pasted reference without another touch or scroll.

## Checks

```sh
flutter pub get --enforce-lockfile
flutter gen-l10n
dart format --output=none --set-exit-if-changed lib test
flutter analyze --no-pub
flutter test --no-pub
cargo fmt --manifest-path rust/openimagine_pipe/Cargo.toml -- --check
cargo clippy --manifest-path rust/openimagine_pipe/Cargo.toml --locked --all-targets -- -D warnings
```

The separate `Phone` GitHub Actions workflow runs these checks and builds an arm64 APK.
It also runs Android Lint on the Kotlin code and manifest.
It runs when the app or its workflow changes. It does not install the Python studio.
Generated translations, native libraries, build caches, local SDK paths and signing keys stay outside Git.
Commit `pubspec.lock` and `Cargo.lock` when dependencies change.

## Release build

```sh
./tool/build_pipe.sh
flutter build apk --release --target-platform android-arm64
```

The APK is at `build/app/outputs/flutter-apk/app-release.apk`. The generated Gradle
config signs release builds with the debug key, so the APK installs on a phone that
allows unknown sources. Replace that signing config before distributing it.

## Limits

- Android only. iOS cannot load a Rust cdylib the same way; it needs an XCTest or a
  static library behind an FFI plugin.
- The pipe stops when Android kills the app. A foreground service shows progress during
  an active run. Android can still stop the process.
- Downloads from a `blob:` URL may not reach the Android download manager. Viewing and
  generating work; saving a generated file may not.
- The app binds the phone's loopback only. The studio's listener binds the Mac's
  loopback. The dumbpipe relay carries the connection between them.
