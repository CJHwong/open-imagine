# LTX-2.5 CUDA gateway

## Why it looks like this

The gateway uses the pinned pipeline's MP4 exporter. It preserves the exporter's codec settings and passes the original audio tensor unchanged.

For normalized video, it converts one frame at a time. This avoids the exporter's complete-clip temporary arrays. It preserves the same multiplication, rounding, and integer conversion.

For other values, it passes the original array to the exporter. This preserves its warnings and error behavior.

The child compiles the transformer's repeated block once it is on the GPU
(`compile_repeated_blocks`, static shapes). Each new size or frame count compiles again on its
first run, and later runs at that shape reuse it.

## Speed experiments, 2026-11-19

All on a DGX Spark through the Studio operations API, seed 7, BF16, 24 fps, without prompt
enhancement unless the row says so.

| Request | Eager | Compiled |
|---|---:|---:|
| 768 × 768, 97 frames, warm | 70.8 s | 53.0 s |
| 768 × 768, 97 frames, first run (load included) | 119.6 s | 111.3 s |
| 1280 × 704, 97 frames, first run at that size | 110.0 s | 89.7 s |
| 384 × 384, 25 frames, first run at that size | 7.6 s | 12.1 s |
| 384 × 384, 25 frames, repeat | 7.55 s | 6.57 s |

The compile wins from the second run at a shape, and on the first run of any clip long
enough to hide the compile. A short first clip pays about 5 s for it. The compiled frames
match the eager ones in scene and quality: the mean absolute pixel difference was 4.8 and 6.3
of 255 at 1 s and 3 s. A compiled child also ran two keyframes (53.4 s), a run with prompt
enhancement, and a cancel, which stopped the run at step 3. A cancel stops the child, so the
compiled block goes with it: the next run, 384 × 384 at 25 frames, took 56.3 s with the reload
and the compile.

These did not win, and are not used. They were measured on the child directly, not through the API:

- fp8 and NVFP4 transformer weights. At 768 × 768 and 97 frames BF16 took 70.8 s, NVFP4
  W4A4 70.9 s, and fp8 W8A8 108.5 s, because quantizing each activation cost more than the
  narrower multiply saved. The transformer is compute-bound here, so narrower weights save
  memory (NVFP4 peaked 25 GiB lower) and no time.
- Attention backends. The transformer's 60.4 s became 61.2 s on cuDNN and 69.5 s on the
  memory-efficient kernel.

## Stage experiment, 2026-11-15

The experiment uses the Studio operations API on a DGX Spark. It uses `diffusers==0.43.0`, BF16 weights, seed 7, 97 frames, and 24 frames per second. Prompt enhancement and audio remain enabled.

The public prompt is: "A red toy train moves across a wooden table. Fixed camera, warm daylight."

Each size runs twice in one resident child. The first request loads the model in 36.00 seconds, excluding Python and dependency imports.

| Measured stage | 768 × 768, second request | 1280 × 704, second request |
|---|---:|---:|
| Prompt enhancement | 5.168 s | 4.942 s |
| Text encoding | 0.639 s | 0.625 s |
| Conditioning | 1.122 s | 1.109 s |
| Denoising | 60.148 s | 94.476 s |
| Video decoding | 3.031 s | 4.579 s |
| Video postprocessing | 2.721 s | 5.065 s |
| Audio decoding | 0.013 s | 0.010 s |
| Vocoder | 0.177 s | 0.233 s |
| Original MP4 encoding | 2.131 s | 8.500 s |
| Child JSON output | 0.006 s | 0.007 s |
| Peak Torch allocation | 80.86 GiB | 83.82 GiB |
| Encoded MP4 size | 832,908 bytes | 1,080,914 bytes |

Stage boundaries synchronize the GPU. Nested stages can overlap in the measurements. Do not add these rows or treat them as normal request latency.

The experiment also writes public frame fixtures after encoding. Those writes take 2.73 and 4.23 seconds in the second requests. They are separate from the encoding stage and do not occur in the product.

The child output timing includes JSON serialization and its stdout write. It excludes parent decoding, HTTP delivery, and download.

Both requests at each size produce identical MP4 bytes. Source digests match before and after all four requests. This small diagnostic sample identifies costs; it does not establish a general speed improvement.

## Encoding experiment, 2026-11-15

The CPU comparison uses public frame fixtures from the first request at each size. Each fixture contains 97 normalized `float32` frames. The value range is [0, 1]. Both paths produce the same rounded `uint8` values in [0, 255].

Each encoding starts a separate Python process. Each size has three repetitions per path, with the order alternating between repetitions. The GPU remains idle during the comparison.

The timer starts after imports and fixture loading. It includes the iterator's complete-array range check, MP4 encoding, and reading the encoded bytes. Peak resident memory covers the complete process, including imports and loaded fixtures.

| Fixture | Original median | Iterator median | Original peak memory | Iterator peak memory |
|---|---:|---:|---:|---:|
| 768 × 768 | 1.332 s | 1.116 s | 2.810 GiB | 1.503 GiB |
| 1280 × 704 | 3.952 s | 1.347 s | 3.876 GiB | 1.902 GiB |

The table reports median encoding time and maximum peak resident memory across three repetitions. It does not measure complete Studio request latency.

For each fixture, all six MP4 outputs match byte for byte. Decoded video frames and audio samples also match exactly. Fixture and source hashes match before and after all 12 encodings. The iterator retains the pinned exporter's codec settings.

The saved audio fixtures use `float32`, with 192,480 stereo samples at 48,000 Hz. The profiler converts the original audio tensor to `float32` before saving it. This can change the exporter's integer conversion, which uses the input tensor's dtype.

Both CPU paths use the same saved audio. Their decoded video matches the original Studio clips, but their decoded audio differs. This comparison proves parity between the two CPU paths. The production change passes the original audio tensor unchanged.

## Product validation

Two uninstrumented Studio operations repeat the public fixture at both sizes. Each MP4 matches the original Studio output byte for byte, including audio. These checks establish output parity, without a complete-request speed claim.

The final helper also passes empty arrays unchanged to the exporter. The existing CUDA live test passes with the final source. It generates a 384 × 384 clip with 25 frames. Source digests match before and after that test.

An independent review checks the implementation and measurements. In an isolated copy, restoring complete-clip conversion makes both allocation tests fail. The restored implementation passes all 27 focused tests.
