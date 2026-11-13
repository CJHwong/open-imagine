#!/bin/sh
# Build the in-process iroh pipe library and place it in the app.
#
# Requirements: Rust, the aarch64-linux-android target, cargo-ndk, and the Android
# NDK (set ANDROID_NDK_HOME if the toolchain cannot find it).
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT/rust/openimagine_pipe"

rustup target add aarch64-linux-android
cargo ndk -t arm64-v8a build --locked --release --lib

mkdir -p "$ROOT/android/app/src/main/jniLibs/arm64-v8a"
cp target/aarch64-linux-android/release/libopenimagine_pipe.so \
   "$ROOT/android/app/src/main/jniLibs/arm64-v8a/"
echo "Wrote android/app/src/main/jniLibs/arm64-v8a/libopenimagine_pipe.so"
