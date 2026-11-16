# LTX-2.5 CUDA gateway

## Why it looks like this

The gateway uses the pinned pipeline's MP4 exporter. It preserves the exporter's codec settings and passes the original audio tensor unchanged.

For normalized video, it converts one frame at a time. This avoids the exporter's complete-clip temporary arrays. It preserves the same multiplication, rounding, and integer conversion.

For other values, it passes the original array to the exporter. This preserves its warnings and error behavior.

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
