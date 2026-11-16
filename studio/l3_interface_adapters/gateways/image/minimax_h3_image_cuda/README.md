# MiniMax H3-Image CUDA performance

The gateway generates at the selected size. The CUDA pipeline rounds non-grid Match dimensions to its 32-pixel canvas and resizes the final image to the requested dimensions. Earlier small-canvas tests found some quality defects.
Pack creation uses nonblocking CPU copies and waits for the source CUDA device before serialization.
It releases unused CUDA memory before copying and releases pinned host memory after each component.
The host release also runs when serialization fails.

The measurements below use DGX Spark (NVIDIA GB10), Torch 2.15.0+cu132, TorchAO 0.18.0, mslk 1.4.0, and Diffusers 0.43.0.
The model revision is `5f90473023975e6271b0ed1dd84c4e88e4bbc6d3`.
The FP8 pack contains an FP8 transformer and an NVFP4 text encoder.

## Canvas experiment

Six requests use the Studio HTTP operation path, a resident child, 1024×1024 output, six distilled steps, and seed 731.
An isolated experiment changes only `min_generation_area` between 4,194,304 and 1,048,576 pixels.
Each request records source digests before and after execution.
CUDA synchronization brackets the pipeline call; these times exclude pack loading, PNG encoding, and transport.

| Public fixture | Default canvas (s) | Native canvas (s) |
| --- | ---: | ---: |
| Mountain lake with smooth dawn sky | 56.036 | 39.607 |
| Window portrait with natural skin | 54.416 | 39.503 |
| Matte ceramic vase on a pale blue table | 54.039 | 39.685 |

The first default request also pays for loading: its HTTP time is 99.345 seconds.
The later default HTTP times are 54.766 and 54.393 seconds.
The native sky has broad purple and blue patches; the default has a more uniform gradient.
The native portrait loses fine detail, and the native vase has broad tonal stripes.
The portrait's content also changes, so its detail comparison remains qualitative.
Independent inspection confirms the sky defect.
Three prompts and one seed support retaining the default; they do not establish a universal quality result.
This earlier experiment found quality defects at 1 MP. The user subsequently chose native selected-size generation.

## Initial-noise experiment

The MLX path uses NumPy noise. The CUDA path uses PyTorch noise. The same seed gives different initial tensors.
A scratch CUDA child tested both noise sources at 1 MP. Each pair used the same prompt, seed, and weights.
Three prompts and two seeds produced six pairs. Three further requests used the 4 MP canvas at seed 731.
The requests ran through the Studio API with one warmup and a resident FP8 child.

| Canvas and noise | Requests | Median request time |
| --- | ---: | ---: |
| 1 MP, PyTorch noise | 6 | 41.20 s |
| 1 MP, NumPy noise | 6 | 41.19 s |
| 4 MP, PyTorch noise | 3 | 55.29 s |

The 4 MP seed 731 controls reproduced the earlier images. Noise changes the image composition.
The new images do not establish that NumPy noise fixes 1 MP quality. The sample does not prove equal quality.
The gateway now uses the selected size, by user choice. All images and request records remain in the local experiment evidence.

## Pack writing

A bounded sample contains 447,473,668 bytes from real FP8, NVFP4, and plain weights while the full model remains resident.
Three original-writer trials compare direct copies, byte views, device clones, nonblocking copies, and bounded pinned staging.
Every trial rebuilds the saved weights and checks their raw bytes and metadata.
Synthetic byte tensors do not reproduce the slow real-weight copies.

The final helper also releases the host cache, which the initial nonblocking prototype retained.
Three final bounded writes take 0.433, 0.351, and 0.359 seconds, including that release.
Each component starts with zero cached pinned bytes; each write ends with zero allocated and active pinned bytes.
The release uses the public [PyTorch host-cache API](https://docs.pytorch.org/docs/stable/generated/torch.accelerator.memory.empty_host_cache.html).

A full cached-pack rewrite takes 48.407 seconds, excluding `fsync`.
All 3,722 stored tensors match the original bytes, dtype, shape, and manifest metadata.
The comparison streams 54,582,157,268 payload bytes without loading a complete shard into memory.
The experiment first creates 24 GiB of unused CUDA reservation to model retained quantization allocations.
The writer releases this reservation before its first host copy.
Memory samples use a nominal 100 ms interval.
Sampled peak resident host memory is 45.96 GiB; minimum available system memory is 19.68 GiB.
Pinned allocation rounding raises the transformer's temporary host pool to 45.14 GiB.
The pinned host pool returns to zero after each component.
The experiment deletes its scratch pack and leaves the existing pack unchanged.
This is a cached-weight rewrite, not a cold quantization run or a matched comparison with the historical 439-second write.
An earlier HTTP live test passes with all 1,016 file digests unchanged before and after.

## Fresh pack creation

The next experiment builds each pack in an empty directory, generates an image, releases the child, and reloads the new pack.
All four historical requests use the Studio HTTP path and the former 4 MP canvas floor.
Each uses 1024×1024 output, six distilled steps, seed 7, and the same public fisherman prompt.
Source digests bracket every request.
One-second samples measure the summed resident set size (RSS) of the server and its descendants.
Available memory uses Linux `MemAvailable`.

| Build | Fresh request (s) | Pack write (s) | Reload request (s) | Peak RSS (GiB) | Minimum available (GiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| FP8 | 333.015 | 64.3 | 94.587 | 100.55 | 20.33 |
| NVFP4 | 332.200 | 46.3 | 64.350 | 106.60 | 17.94 |

Fresh includes model construction, quantization, pack writing, and generation.
Reload uses a new child. Pack writing excludes `fsync`.
Each fresh/reloaded pair matches PNG bytes, decoded pixels, and PNG metadata.
Each also matches the earlier output from its corresponding original pack for the same request.
The headers and manifests match the originals: 3,722 stored tensors for FP8 and 4,095 for NVFP4.
This header check does not compare fresh tensor payloads.
These single runs prove complete cold creation and reload without establishing a matched speedup against the historical write.
The original packs stay unchanged.
The existing HTTP live test also passes in 107.89 seconds against a later 1,018-file copy.
That copy records its CUDA configuration override and keeps all source digests unchanged throughout the run.

## Prompt-enhancer checkpoint

The public prompt-enhancer release uses ModelOpt NVFP4 weights in storage.
Transformers 5.23.0 skips this quantizer and attempts to load packed matrices at half their required width.
The loader now decodes one indexed matrix at a time and places its BF16 values on CUDA.
It reads each scale through the shard index, because one layer stores its scales in another shard.
It checks every model weight before transfer and retains the checkpoint's generation settings.
Raw weights keep their stored dtype. Constructor rotary buffers keep their FP32 dtype.
The decoded model stays in memory during its request.
CUDA chat templates need one image marker per reference.
The adapter adds these markers and keeps the text that the shared formatter supplies.
