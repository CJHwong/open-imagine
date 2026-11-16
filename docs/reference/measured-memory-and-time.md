# Measured memory and time

**Measurement update: 2026-11-16.** Source1 denotes the frozen 2026-11-16 code with digest `cf52268b6a1c4694102b44606c2c0f749b2f01d6c8e44742b087b3ff24515871`.
Source2 denotes the later frozen code with digest `b441a062014a6a4f52e769215f1faf1fe5404dd709b97a0cfb303b9b97e6575b`.
Source3 denotes the final H3 image-marker fix with digest `aac6350dd097528822befd61c7fec45bfbe0118ac806bcabcb5c5e8e3e795a53`.
Rows marked historical keep their original campaign scope. Current rows do not establish complete semantic coverage.

The main campaigns measure memory and elapsed time on an Apple M5 Pro Mac and an NVIDIA DGX Spark.
The Mac has 64 gibibytes (GiB) of memory. The Spark has 121.7 GiB of unified memory.
Each machine has its own section: the models it ran, how to read its numbers, and one table per modality.

**Latest campaign: 2026-11-16.** The current campaign reruns supported documented requests through the studio API.
Current numeric rows identify their frozen source revision. Historical rows retain their original dates, fixtures, and timing scopes.
Current operation counts come from the final evidence ledger. Expected outcomes and unexpected failures remain separate.
The campaign accounts for 183 distinct case IDs. Warmups, retries, and extra contract checks remain separate.
Successful requests and decoded outputs do not establish prompt fidelity.
The [latest results and coverage](#gateway-performance-checks-2026-11-15-to-2026-11-16) identify the checks that ran and the remaining gaps.
The H3 video encoding and synthetic transport checks also use an M1 Pro with 32 GiB; those are component measurements.

## Apple M5 Pro

The original Mac campaign ran on 2026-11-12 and 2026-11-13. Its historical rows remain explicitly marked.
The current 2026-11-16 campaign uses the studio API and public fixtures with explicit seeds.
The completed image phase records 44 measured requests and four warmups. It decodes 43 images and confirms one expected memory limit.
The current image outputs report seed seven. Image steps come from retained output metadata.
The H3-Image rows use the pre-quantized MLX int8 pack. Their image engines load per call.
The documented Mac modalities are complete. The optional phase completes 21 requests and closes 19 historical setup-case IDs.

| Item | Value |
|---|---|
| Machine | Apple M5 Pro, 64 GiB |
| Date | Current campaign: 2026-11-16. Historical rows: 2026-11-12 and 2026-11-13. |
| Path | The studio API on a local port, one operation at a time |
| Seed | Current image payloads explicitly set 7. Other current cases use their manifest seed, including named exceptions. Historical image seeds remain unspecified. |
| Sample | Free memory from `memory_pressure -Q`, and `footprint` of the server process tree, once a second |
| Baseline | The three samples before the submit |
| Time | Submit to terminal status. The time excludes queue wait and weight download. |

### Models

| Model | Backend | Source | Quantization | Checkpoint (GiB) |
|---|---|---|---|---|
| FLUX.3 Klein | `flux3` | `black-forest-labs/flux-3-image-klein` | q8 (mflux) | 19 |
| MiniMax H3-Image | `minimax_h3_image` | `MiniMaxAI/MiniMax-H3-Image`, fetched by h3-image-mlx | int8 | 46 |
| Qwen-Image-2.1 | `qwen21` | `Qwen/Qwen-Image-2.1` | bf16 | 31 |
| Qwen-Image-2.1 Turbo | `qwen21_turbo` | `Qwen/Qwen-Image-2.1-Turbo` | bf16 | 30 |
| LTX-2.5 | `ltx25_mlx` | `dgrauet/ltx-2.5-mlx-q8` | q8 | 70 |
| MiniMax H3 | `minimax_h3` | `pipenetwork/MiniMax-H3-MLX-8bit` at revision `e55f97c8` | q8 | 65 |
| Drama-3 | `drama3` | `mlx-community/fish-audio-drama-3-8bit` at revision `fedc7cc9` | 8-bit | 39 |
| YuE2 | `yue2` | `m-a-p/YuE2-3B`, converted to MLX at revision `5f7620e5` | Q8 generator, BF16 acoustic, FP32 decoder | 9.7 |
| Krea 2 Turbo | `krea2` | `mflux-community/krea-2-turbo-mflux-q8` | Native packed 8-bit storage; resident runtime dtypes not recorded. | 20.66 installed |
| FLUX.2 Klein base 9B | `flux2` | `darknight9121/FLUX.2-klein-base-9B-bucket-uncensored` | quantize=None; stored transformer BF16 and text encoder F16. | 32.34 installed |
| Viggle Turbo | `viggle_turbo` | `Viggle/Qwen-Image-2.1-viggle-turbo` | quantize=None; stored BF16 LoRA; reused base has BF16/F32 weights. | 1.27 LoRA; 30.86 base cache |
| LTX-2.3 | `ltx23_mlx` | `dgrauet/ltx-2.3-mlx-q8` | Pack declares 8-bit groups of 64, transformer blocks only. | 53.98 installed |

`Checkpoint` counts the files the backend reads from disk, measured with `du` on this Mac.
The four added optional rows instead report installed file lengths. Their labels distinguish installed packs, LoRA files, and reused base-cache files.
A pre-quantized pack is smaller than its source because the pack already holds the narrowed weights.
The original model rows exclude separate prompt rewriters, adapters, and LoRA downloads. The new Viggle row names its LoRA and reused base separately.

### How to read the numbers

**Free-memory drop (GiB)** is the fall from the baseline to the lowest free-memory sample, as a share of 64 GiB.
A free-memory drop is a signed baseline-to-minimum change. A negative change means sampled available memory increased against baseline.
Background activity limits interpretation.
A negative change does not represent negative allocation or measured memory savings.
**Process footprint (GiB)** is the sampled peak sum of physical footprints across the server process tree.
A retained model can contribute memory before a request. Process-per-call models can reuse cached filesystem data without retaining model weights.
The image phase has two incomplete footprint samples. The peak uses complete samples and preserves both gaps in the raw evidence.
The macOS `footprint` command rounds large `CURRENT` headers. The sampler sums those rounded current values across the process tree.
It reports the maximum complete one-second sample. It does not use the lifetime field `phys_footprint_peak`.
Two decimal places format approximate sums. They do not imply byte-level or 0.01 GiB accuracy.
Resident set size and physical footprint measure different quantities. Do not treat them as interchangeable process memory.
**Time (s)** is the operation's wall time. The queue wait is excluded, because the runner waits for an idle server before it submits.
Each case has one row. `Runs` gives the recorded runs for that case name, and the row shows the last run.
A row with one run is one measurement, not an average. Machine load moves a time, so compare rows with that limit in mind.
These numbers apply to a 64 GiB Mac. Another host has no calibrated estimate.

### Image

The current image phase checks operation completion and output decoding. The Result cells also name observed quality limits.
Turbo with ten references loses the distinct pear. Base Qwen with four, eight, or ten references changes the composition.
These observations do not establish regression or cause. Other decoded images receive no blanket semantic pass.
FLUX.3 and H3-Image load image engines per call. Driver warmup can warm filesystem data, but does not establish resident weights.
Base Qwen rebuilds its generator for a new uncached prompt. Turbo restores only its text encoder.
Both Qwen variants retain same-mode edit models. A mode switch releases the other variant.

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `flux3/generate/text/512` (Source1) | flux3, generate, size 512x512, reported steps 16 | 7.68 | 48.01 | 28.7 | Succeeded (decoded) | 1 |
| `flux3/generate/text/768` (Source1) | flux3, generate, size 768x768, reported steps 16 | 16.64 | 46.03 | 25.2 | Succeeded (decoded) | 1 |
| `flux3/generate/text/1024` (Source1) | flux3, generate, size 1024x1024, reported steps 16 | 26.88 | 58.03 | 45.4 | Succeeded (decoded) | 1 |
| `minimax_h3_image/generate/1024` (historical) | minimax_h3_image, generate, size 1024x1024, 6 steps | 14.72 | 19.06 | 23.2 | Succeeded | 1 |
| `minimax_h3_image/generate/2048` (historical) | minimax_h3_image, generate, size 2048x2048, 6 steps | 8.32 | 20.07 | 51.4 | Succeeded | 1 |
| `minimax_h3_image/edit/one-ref-2048` (historical) | minimax_h3_image, edit, size match, 6 steps, 1 ref, input 2048x2048 | 3.20 | 4.39 | 153.2 | Succeeded | 1 |
| `qwen21/edit/10-refs/out1024` (Source1) | qwen21, edit, size 1024, 10 refs, reported steps 40 | 32.64 | 72.01 | 651.4 | Succeeded (decoded; composition changed) | 1 |
| `qwen21/edit/2-refs/out1024` (Source1) | qwen21, edit, size 1024, 2 refs, reported steps 40 | 2.35 | 61.01 | 258.2 | Succeeded (decoded) | 1 |
| `qwen21/edit/4-refs/out1024` (Source1) | qwen21, edit, size 1024, 4 refs, reported steps 40 | 8.32 | 59.01 | 339.7 | Succeeded (decoded; composition changed) | 1 |
| `qwen21/edit/8-refs/out1024` (Source1) | qwen21, edit, size 1024, 8 refs, reported steps 40 | 36.48 | 68.01 | 550.2 | Succeeded (decoded; composition changed) | 1 |
| `qwen21/edit/each/out1024` (Source1) | qwen21, edit, size 1024, 4 refs, reported steps 40, total=1, first reference only | 10.88 | 55.01 | 216.7 | Succeeded (decoded) | 1 |
| `qwen21/edit/mask/out1024` (Source1) | qwen21, edit, size 1024, 1 ref, mask, reported steps 40 | 10.88 | 55.01 | 249.1 | Succeeded (decoded) | 1 |
| `qwen21/edit/one-ref/in1600x900` (Source1) | qwen21, edit, size 1024, 1 ref, input 1600x900, reported steps 40 | 12.16 | 53.01 | 224.9 | Succeeded (decoded) | 1 |
| `qwen21/edit/one-ref/in2048x2048` (Source1) | qwen21, edit, size 1024, 1 ref, input 2048x2048, reported steps 40 | 13.44 | 60.01 | 216.9 | Succeeded (decoded) | 1 |
| `qwen21/edit/one-ref/in4032x3024` (Source1) | qwen21, edit, size 1024, 1 ref, input 4032x3024, reported steps 40 | 17.92 | 59.01 | 226.0 | Succeeded (decoded) | 1 |
| `qwen21/edit/one-ref/in512x512` (Source1) | qwen21, edit, size 1024, 1 ref, input 512x512, reported steps 40 | 4.48 | 60.01 | 223.9 | Succeeded (decoded) | 1 |
| `qwen21/edit/one-ref/out1024` (Source1) | qwen21, edit, size 1024, 1 ref, reported steps 40 | 10.88 | 58.01 | 219.0 | Succeeded (decoded) | 1 |
| `qwen21/edit/one-ref/out1344` (Source1) | qwen21, edit, size 1344, 1 ref, reported steps 40 | 16.64 | 69.01 | 460.7 | Succeeded (decoded) | 1 |
| `qwen21/edit/one-ref/out512` (Source1) | qwen21, edit, size 512, 1 ref, reported steps 40 | 34.56 | 51.01 | 48.5 | Succeeded (decoded) | 1 |
| `qwen21/edit/one-ref/out768` (Source1) | qwen21, edit, size 768, 1 ref, reported steps 40 | 30.08 | 56.01 | 104.4 | Succeeded (decoded) | 1 |
| `qwen21/generate/text/1024` (Source1) | qwen21, generate, size 1024x1024, reported steps 40 | 21.76 | 50.01 | 158.4 | Succeeded (decoded) | 1 |
| `qwen21/generate/text/1328` (Source1) | qwen21, generate, size 1328x1328, reported steps 40 | 23.04 | 48.01 | 295.5 | Succeeded (decoded) | 1 |
| `qwen21/generate/text/512` (Source1) | qwen21, generate, size 512x512, reported steps 40 | 26.24 | 44.01 | 33.5 | Succeeded (decoded) | 1 |
| `qwen21/generate/text/768` (Source1) | qwen21, generate, size 768x768, reported steps 40 | 24.96 | 47.01 | 79.8 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/10-refs/out1024` (Source1) | qwen21_turbo, edit, size 1024, 10 refs, reported steps 8 | 42.45 | 68.01 | 460.8 | Succeeded (decoded; pear missing) | 1 |
| `qwen21_turbo/edit/2-refs/out1024` (Source1) | qwen21_turbo, edit, size 1024, 2 refs, reported steps 8 | 42.03 | 50.01 | 55.5 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/4-refs/out1024` (Source1) | qwen21_turbo, edit, size 1024, 4 refs, reported steps 8 | 39.68 | 54.01 | 75.8 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/8-refs/out1024` (Source1) | qwen21_turbo, edit, size 1024, 8 refs, reported steps 8 | 41.17 | 62.01 | 337.2 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/each/out1024` (Source1) | qwen21_turbo, edit, size 1024, 4 refs, reported steps 8, total=1, first reference only | 36.05 | 50.01 | 47.4 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/mask/out1024` (Source1) | qwen21_turbo, edit, size 1024, 1 ref, mask, reported steps 8 | 37.33 | 50.01 | 62.6 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/one-ref/in1600x900` (Source1) | qwen21_turbo, edit, size 1024, 1 ref, input 1600x900, reported steps 8 | 35.84 | 50.01 | 56.5 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/one-ref/in2048x2048` (Source1) | qwen21_turbo, edit, size 1024, 1 ref, input 2048x2048, reported steps 8 | 36.05 | 50.01 | 49.4 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/one-ref/in4032x3024` (Source1) | qwen21_turbo, edit, size 1024, 1 ref, input 4032x3024, reported steps 8 | 36.69 | 50.01 | 55.6 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/one-ref/in512x512` (Source1) | qwen21_turbo, edit, size 1024, 1 ref, input 512x512, reported steps 8 | 36.05 | 50.01 | 44.4 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/one-ref/out1024` (Source1) | qwen21_turbo, edit, size 1024, 1 ref, reported steps 8 | 36.05 | 50.01 | 35.3 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/one-ref/out1344` (Source1) | qwen21_turbo, edit, size 1344, 1 ref | 39.89 | 53.01 | 78.6 | Failed (expected limit) | 1 |
| `qwen21_turbo/edit/one-ref/out512` (Source1) | qwen21_turbo, edit, size 512, 1 ref, reported steps 8 | 45.23 | 50.01 | 12.1 | Succeeded (decoded) | 1 |
| `qwen21_turbo/edit/one-ref/out768` (Source1) | qwen21_turbo, edit, size 768, 1 ref, reported steps 8 | 36.05 | 50.01 | 18.1 | Succeeded (decoded) | 1 |
| `qwen21_turbo/generate/text/1024` (Source1) | qwen21_turbo, generate, size 1024x1024, reported steps 8 | 46.51 | 50.01 | 23.3 | Succeeded (decoded) | 1 |
| `qwen21_turbo/generate/text/1328` (Source1) | qwen21_turbo, generate, size 1328x1328, reported steps 8 | 45.87 | 50.01 | 45.5 | Succeeded (decoded) | 1 |
| `qwen21_turbo/generate/text/512` (Source1) | qwen21_turbo, generate, size 512x512, reported steps 8 | 26.03 | 31.01 | 5.2 | Succeeded (decoded) | 1 |
| `qwen21_turbo/generate/text/768` (Source1) | qwen21_turbo, generate, size 768x768, reported steps 8 | 33.49 | 40.01 | 12.2 | Succeeded (decoded) | 1 |

### Video

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `ltx25/generate/1-keyframes/768x768x97` (Source3) | ltx25_mlx, generate, 768x768, 97 frames, 1 keyframe, no enhance | 15.36 | 28.08 | 155.3 | Succeeded (decoded) | 1 |
| `ltx25/generate/2-keyframes/768x768x97` (Source3) | ltx25_mlx, generate, 768x768, 97 frames, 2 keyframes, no enhance | 16.64 | 29.07 | 168.4 | Succeeded (decoded) | 1 |
| `ltx25/generate/4-keyframes/768x768x97` (Source3) | ltx25_mlx, generate, 768x768, 97 frames, 4 keyframes, no enhance | 15.36 | 29.07 | 192.6 | Succeeded (decoded) | 1 |
| `ltx25/generate/8-keyframes/768x768x97` (Source3) | ltx25_mlx, generate, 768x768, 97 frames, 8 keyframes, no enhance | 16.00 | 32.07 | 247.1 | Succeeded (decoded) | 1 |
| `ltx25/generate/audio/768x768x97` (Source3) | ltx25_mlx, generate, 768x768, 97 frames, no enhance, audio track | 16.00 | 37.07 | 866.6 | Succeeded (decoded) | 1 |
| `ltx25/generate/fast/768x768x121` (Source3) | ltx25_mlx, generate, 768x768, 121 frames, fast mode | 19.20 | 24.06 | 142.2 | Succeeded (decoded) | 1 |
| `ltx25/generate/frames/121` (Source3) | ltx25_mlx, generate, 768x768, 121 frames | 15.36 | 24.07 | 192.6 | Succeeded (decoded) | 1 |
| `ltx25/generate/frames/25` (Source3) | ltx25_mlx, generate, 768x768, 25 frames | 16.00 | 23.07 | 53.4 | Succeeded (decoded) | 1 |
| `ltx25/generate/frames/49` (Source3) | ltx25_mlx, generate, 768x768, 49 frames | 15.36 | 24.07 | 82.7 | Succeeded (decoded) | 1 |
| `ltx25/generate/no-enhance/768x768x97` (Source3) | ltx25_mlx, generate, 768x768, 97 frames, no enhance | 14.08 | 24.07 | 153.2 | Succeeded (decoded) | 1 |
| `ltx25/generate/text/1280x704x97` (Source3) | ltx25_mlx, generate, 1280x704, 97 frames | 17.07 | 26.06 | 200.7 | Succeeded (decoded) | 1 |
| `ltx25/generate/text/1920x1088x97` (Source3) | ltx25_mlx, generate, 1920x1088, 97 frames | 12.37 | 32.06 | 723.4 | Succeeded (decoded) | 1 |
| `ltx25/generate/text/384x384x25` (Source3) | ltx25_mlx, generate, 384x384, 25 frames | 21.97 | 23.09 | 28.2 | Succeeded (decoded) | 1 |
| `ltx25/generate/text/768x768x97` (Source3) | ltx25_mlx, generate, 768x768, 97 frames | 17.28 | 24.06 | 115.0 | Succeeded (decoded) | 1 |
| `minimax_h3/generate/text/512x288x73` (Source3) | minimax_h3, generate, 512x288, 73 frames, 24 fps | 33.28 | 33.11 | 106.9 | Succeeded (decoded) | 1 |
| `minimax_h3/generate/text/1024x576x175` (Source3) | minimax_h3, generate, 1024x576, 175 frames, 24 fps | 32.00 | 33.05 | 1653.8 | Succeeded (decoded) | 1 |

### Voice

The Source3 Mac Drama rows replace seven earlier requests with unproved external child provenance.
Six expected outcomes pass. The seed 11 request fails at max_tokens after 95.93 seconds; its expected-success check remains false.
One direct isolated child control reproduces the limit with the same protocol job. Its 69.89 seconds is not an operation timing.
Its package hashes name another environment. Later matching hashes do not prove earlier worker package bytes.

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `drama3/clone/ref15s` (Source3) | drama3, clone, 7 words, ref 15s | 28.80 | 41.09 | 4.1 | Succeeded (decoded) | 1 |
| `drama3/clone/ref5s` (Source3) | drama3, clone, 7 words, ref 5s | 28.16 | 41.06 | 4.1 | Succeeded (decoded) | 1 |
| `drama3/generate/paragraph700` (Source3) | drama3, generate, 83 words | 28.80 | 41.08 | 39.3 | Succeeded (decoded) | 1 |
| `drama3/generate/sentence50` (Source3) | drama3, generate, 7 words | 28.16 | 41.09 | 4.0 | Succeeded (decoded) | 1 |
| `drama3/generate/text1000` (Source3) | drama3, generate, 200 words | 28.16 | 41.05 | 67.5 | Failed (expected limit) | 1 |
| `drama3/generate/text4000` (Source3) | drama3, generate, 800 words | 28.16 | 41.05 | 67.5 | Failed (expected limit) | 1 |
| `drama3/generate/text50-seed11` (Source3) | drama3, generate, 10 words, seed 11 | 28.16 | 42.07 | 95.93 | Failed (max_tokens, unexpected) | 1 |

### Music

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `yue2/cover/speech10s` (historical) | yue2, cover, style, lyrics, 10 s speech reference | 6.40 | 8.93 | 18.2 | Succeeded | 1 |
| `yue2/generate/instrumental` (Source3) | yue2, generate, style, instrumental | 3.84 | 11.15 | 264.0 | Succeeded (decoded) | 1 |
| `yue2/generate/long` (Source3) | yue2, generate, style, lyrics | 3.84 | 10.12 | 213.6 | Succeeded (decoded) | 1 |
| `yue2/generate/short` (Source3) | yue2, generate, style, lyrics | 5.12 | 11.08 | 123.9 | Succeeded (decoded) | 1 |
| `yue2/plan/short` (Source3) | yue2, plan, style, lyrics | 3.20 | 4.63 | 9.1 | Succeeded (structured result) | 1 |
| `yue2/transcribe/speech10s` (historical) | yue2, transcribe, 10 s speech reference | 1.92 | 4.23 | 7.1 | Succeeded | 1 |
| `yue2/transcribe/speech15s` (historical) | yue2, transcribe, 15 s speech reference | 1.92 | 4.24 | 5.1 | Succeeded | 1 |

### Mandarin, 2026-11-14

The heading retains the original campaign date. The Source3 rows below were measured on 2026-11-16.
| Case | Settings | Time (s) | Audio | Result |
|---|---|---|---|---|
| `mandarin/voice/traditional` (Source3) | drama3, generate, Traditional Chinese | 4.0 | 5.1 s at 44100 Hz | Succeeded (decoded) |
| `mandarin/voice/simplified` (Source3) | drama3, generate, Simplified Chinese | 4.0 | 4.4 s at 44100 Hz | Succeeded (decoded) |
| `mandarin/voice/paragraph` (Source3) | drama3, generate, Traditional Chinese | 67.5 | none | Failed (expected limit) |
| `mandarin/music/verse` (Source3) | yue2, generate, Mandarin lyric | 42.4 | 42.2 s at 48000 Hz | Succeeded (decoded) |

The current requests use the public Mandarin fixtures through the studio API. Their raw records include memory samples.
The compact table reports latency and decoded audio duration. It omits memory columns.
The paragraph reaches its declared token limit. Two speech results and one song fully decode.
The measured song follows an explicit warmup. These checks do not establish pronunciation quality.

### Optional image results, 2026-11-16

All 21 requests pass completion, full-image decoding, and native geometry checks. The phase includes three separate warmups.
These results close all 19 earlier setup-case IDs. Two additional FLUX.2 requests repair invalid historical size values.
Together with two earlier FLUX.3 edits and two LTX2.3 clips, all six rejected historical payloads now have repaired runs.
The current table uses explicit seed seven. Steps come from retained output metadata.
Generate with a reference is a supported FLUX.2 mode. Its gradient result lacks the requested distinct pear.
The requested 25-step schedule and strength 0.4 select 15 denoise iterations in the pinned native consumer.
No introduced mode or argument mapping change is identified. These checks do not establish the cause of the missing pear.
Krea reference previews retain a visible pear with haze or gradient influence. Completion and decoding do not establish prompt fidelity.
Frozen code retains in-process models and replaces them on mode changes. No per-request native object trace proves residency for every row.
Stored tensor headers, runtime quantization requests, and later dependency metadata remain separate evidence fields.

| Case | Decoded output | Reported steps | Time (s) | Signed free-memory drop (GiB) | Approximate process footprint (GiB) | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| office/krea2/generate/text/512 | 512x512 | 8 | 19.195 | 18.56 | 33.01 | Succeeded (decoded) |
| office/krea2/generate/text/768 | 768x768 | 8 | 41.384 | 24.96 | 50.01 | Succeeded (decoded) |
| office/krea2/generate/text/1024 | 1024x1024 | 8 | 89.722 | 12.80 | 50.01 | Succeeded (decoded) |
| office/krea2/generate/one-ref/in512x512 | 1024x1024 | 8 | 64.549 | 31.36 | 50.01 | Succeeded (decoded; haze) |
| office/krea2/generate/one-ref/in1024x1024 | 1024x1024 | 8 | 60.550 | 30.72 | 50.01 | Succeeded (decoded; haze) |
| office/krea2/generate/one-ref/in2048x2048 | 1024x1024 | 8 | 56.513 | 30.72 | 50.01 | Succeeded (decoded; haze) |
| office/krea2/generate/one-ref/in1600x900 | 1360x768 | 8 | 56.482 | 31.36 | 50.01 | Succeeded (decoded; haze) |
| office/krea2/generate/one-ref/in4032x3024 | 1184x880 | 8 | 56.587 | 30.72 | 50.01 | Succeeded (decoded; haze) |
| office/flux2/generate/text/512 | 512x512 | 25 | 68.502 | 19.20 | 32.01 | Succeeded (decoded) |
| office/flux2/generate/text/768 | 768x768 | 25 | 136.441 | 26.88 | 41.01 | Succeeded (decoded) |
| office/flux2/generate/text/1024 | 1024x1024 | 25 | 243.688 | 42.24 | 49.01 | Succeeded (decoded) |
| office/flux2/generate/match/in1600x900 | 1360x768 | 25 | 243.306 | 29.44 | 50.01 | Succeeded (decoded; no distinct pear) |
| office/flux2/edit/1-refs/out1024 | 1024x1024 | 25 | 545.355 | 34.56 | 50.01 | Succeeded (decoded) |
| office/flux2/edit/4-refs/out1024 | 1024x1024 | 25 | 1955.587 | 35.84 | 50.01 | Succeeded (decoded) |
| office/flux2/edit/one-ref/in512x512 | 1024x1024 | 25 | 321.420 | 39.04 | 50.01 | Succeeded (decoded) |
| office/flux2/edit/one-ref/in2048x2048 | 1024x1024 | 25 | 547.812 | 32.64 | 49.01 | Succeeded (decoded) |
| office/flux2/edit/one-ref/in4032x3024 | 1184x880 | 25 | 547.747 | 32.00 | 50.01 | Succeeded (decoded) |
| office/viggle_turbo/generate/text/512 | 512x512 | 6 | 6.214 | 27.09 | 34.01 | Succeeded (decoded) |
| office/viggle_turbo/generate/text/1024 | 1024x1024 | 6 | 27.445 | 30.08 | 50.01 | Succeeded (decoded) |
| office/viggle_turbo/edit/one-ref/match | 1024x1024 | 6 | 50.608 | 37.12 | 50.01 | Succeeded (decoded) |
| office/viggle_turbo/edit/one-ref/out1024 | 1024x1024 | 6 | 44.374 | 5.76 | 50.01 | Succeeded (decoded) |

#### Installed optional packs and provenance

Installed bytes sum selected file lengths. They do not measure runtime memory, allocated disk blocks, or the entire upstream repository.
Pack headers and profile values were checked after the phase. Earlier full-file hashes come from the verified installation proof.
The native dependency inventory is a later metadata sample, not a contemporaneous package-byte bracket.
License names below identify the pinned published metadata or license file.

| Pack | Repository and pinned revision | Installed bytes | Declared license | Storage and runtime request |
| --- | --- | ---: | --- | --- |
| Krea 2 Turbo | [mflux-community/krea-2-turbo-mflux-q8](https://huggingface.co/mflux-community/krea-2-turbo-mflux-q8/tree/5f94d7734c8873daddf803721f6423148619f63c) at `5f94d7734c8873daddf803721f6423148619f63c` | 22186472315 | Krea 2 Community License | Native packed 8-bit storage; resident runtime dtypes not recorded. |
| FLUX.2 Klein base 9B | [darknight9121/FLUX.2-klein-base-9B-bucket-uncensored](https://huggingface.co/darknight9121/FLUX.2-klein-base-9B-bucket-uncensored/tree/3bfbda10423059381f3cdfdc9ffb6f037083d64a) at `3bfbda10423059381f3cdfdc9ffb6f037083d64a` | 34722768239 | FLUX Non-Commercial License | quantize=None; stored transformer BF16 and text encoder F16. |
| Viggle Turbo | [Viggle/Qwen-Image-2.1-viggle-turbo](https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo/tree/009a44a895ef85f7e643c80fdca9543795248867) at `009a44a895ef85f7e643c80fdca9543795248867` | 1359147904 | Qwen RESEARCH LICENSE AGREEMENT | quantize=None; stored BF16 LoRA; reused base has BF16/F32 weights. |
| LTX-2.3 | [dgrauet/ltx-2.3-mlx-q8](https://huggingface.co/dgrauet/ltx-2.3-mlx-q8/tree/69f8f11996b7b2ee54e82d0db7a5acad14b8685d) at `69f8f11996b7b2ee54e82d0db7a5acad14b8685d` | 57957214326 | LTX-2 Community License Agreement | Pack declares 8-bit groups of 64, transformer blocks only. |

The Viggle total counts only its 1,359,147,904-byte LoRA. Its reused Qwen base cache contains 33,131,600,661 bytes.
The base cache revision is `d26bb61231c349cf6b7896fa83353113880e1ba3`. Its files were not rehashed during this phase.
FLUX.2 reads its staged local text encoder. Its F16 bytes have a prior verified identity from the separate encoder pack.
That identity uses `ponpoke/flux2-klein-9b-uncensored-text-encoder` at `fba36e796aac081246708dd30392a401ba44922e`. Runtime does not resolve that gated repository.
The LTX2.3 installed total excludes its separate Gemma text encoder. The retained install proof records that dependency.
The Krea card names its community license. The FLUX.2 license file names its non-commercial license.
The separately fetched pinned Viggle license names the Qwen research agreement. The LTX2.3 license file names its community agreement.



### Current repaired fixtures, 2026-11-16

| Completed replacement or repaired case | Steps from output | Time (s) | Incremental memory drop (GiB) | Peak process footprint (GiB) | Status | Source |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| office/flux3/edit/1-refs/out1024 | 16 | 104.9 | 23.04 | 62.03 | succeeded | cf52268b6a1c4694102b44606c2c0f749b2f01d6c8e44742b087b3ff24515871 |
| office/flux3/edit/2-refs/out1024 | 16 | 204.7 | 40.32 | 67.03 | succeeded | cf52268b6a1c4694102b44606c2c0f749b2f01d6c8e44742b087b3ff24515871 |
| office/minimax_h3_image/generate/1024 | 6 | 18.1 | 16.00 | 37.02 | succeeded | cf52268b6a1c4694102b44606c2c0f749b2f01d6c8e44742b087b3ff24515871 |
| office/minimax_h3_image/generate/2048 | 6 | 64.5 | 4.48 | 38.02 | succeeded | cf52268b6a1c4694102b44606c2c0f749b2f01d6c8e44742b087b3ff24515871 |
| office/minimax_h3_image/edit/one-ref-2048 | 6 | 176.7 | 3.20 | 22.20 | succeeded | cf52268b6a1c4694102b44606c2c0f749b2f01d6c8e44742b087b3ff24515871 |
| office/ltx23_mlx/generate/text/768x768x97 | not returned | 159.4 | 15.36 | 24.06 | succeeded (dark last-frame preview) | aac6350dd097528822befd61c7fec45bfbe0118ac806bcabcb5c5e8e3e795a53 |
| office/ltx23_mlx/generate/one-keyframe/768x768x97 | not returned | 922.6 | 14.72 | 34.06 | succeeded (dark last-frame preview) | aac6350dd097528822befd61c7fec45bfbe0118ac806bcabcb5c5e8e3e795a53 |
| office/flux2/edit/1-refs/out1024 | not returned | 545.4 | 34.56 | 50.01 | succeeded | aac6350dd097528822befd61c7fec45bfbe0118ac806bcabcb5c5e8e3e795a53 |
| office/flux2/edit/4-refs/out1024 | not returned | 1955.6 | 35.84 | 50.01 | succeeded | aac6350dd097528822befd61c7fec45bfbe0118ac806bcabcb5c5e8e3e795a53 |


### Not tested

The table records setup gaps from the 2026-11-12 to 2026-11-13 campaign.
The optional campaign completes all 19 historical setup-case IDs. The gap descriptions below remain historical. Current results appear above.
The setup links describe the required assets; the named case files belong to the original campaign.

| Model | Historical cases | Historical setup gap | Current 2026-11-16 result |
|---|---|---|---|
| flux2 | 7 cases: `flux2/generate/text/512`, `flux2/generate/text/768`, `flux2/generate/text/1024`, `flux2/generate/match/in1600x900`, `flux2/edit/one-ref/in512x512`, `flux2/edit/one-ref/in2048x2048`, `flux2/edit/one-ref/in4032x3024` | The weights are missing at the local model path named in the error. | All 7 setup-case IDs pass completion, decoding, and native geometry. |
| krea2 | 8 cases: `krea2/generate/text/512`, `krea2/generate/text/768`, `krea2/generate/text/1024`, `krea2/generate/one-ref/in512x512`, `krea2/generate/one-ref/in1024x1024`, `krea2/generate/one-ref/in2048x2048`, `krea2/generate/one-ref/in1600x900`, `krea2/generate/one-ref/in4032x3024` | The int8 weights are incomplete. | All 8 setup-case IDs pass completion, decoding, and native geometry. |
| viggle_turbo | 4 cases: `viggle_turbo/generate/text/512`, `viggle_turbo/generate/text/1024`, `viggle_turbo/edit/one-ref/match`, `viggle_turbo/edit/one-ref/out1024` | The LoRA file is missing. | All 4 setup-case IDs pass completion, decoding, and native geometry. |

Three groups stopped on the payload, not on a model gap.
`flux2/edit/1-refs/out1024` and `flux2/edit/4-refs/out1024` used a `size` value the API rejects.
`flux3/edit/1-refs/out1024` and `flux3/edit/2-refs/out1024` did the same.
`ltx23_mlx/generate/text/768x768x97` and `ltx23_mlx/generate/one-keyframe/768x768x97` omitted `frame_rate`.
Those historical payloads produced no model measurement. The current LTX2.3 requests use explicit frame rates and appear in the repaired-fixture table.

## DGX Spark

The original Spark campaigns ran on 2026-11-13, 2026-11-14, and 2026-11-15.
Rows marked Source1, Source2, or Source3 contain current measurements from 2026-11-16.
Historical experiments retain their original fixtures, dates, and timing scopes.
Every backend runs in a PEP 723 child on Python 3.12, one operation at a time, with `HF_HUB_DISABLE_XET=1` because Xet delivery stalls on this network.

| Item | Value |
|---|---|
| Machine | Historical host record: NVIDIA DGX Spark, GB10, 121.7 GiB unified memory, CUDA 13.0, driver 580.178.04, Ubuntu 24.04 aarch64 |
| Date | Current source-tagged rows: 2026-11-16. Historical campaigns: 2026-11-13 to 2026-11-15. |
| Path | Current campaign: studio API on port 8898. Historical campaign: port 8899. One operation at a time. |
| Seed | 7 unless the case name names one |
| Sample | `MemAvailable` from `/proc/meminfo`, once a second |
| Baseline | The three samples before the submit |
| Time | Submit to terminal status. The time excludes queue wait and weight download. |

The machine row retains the historical driver and operating-system descriptor. Current retained preflight records do not independently establish those versions.
Current image-child measurements record PyTorch 2.15.0+cu132. That package suffix describes the CUDA build, not the installed driver version.

### Models

| Model | Backend | Source | Quantization | Checkpoint (GiB) |
|---|---|---|---|---|
| Qwen-Image-2.1 Turbo | `qwen21_turbo_cuda` | `Qwen/Qwen-Image-2.1-Turbo` | BF16 by default. Current NVFP4 checks use the quantize configuration on qwen21_turbo_cuda. The older backend alias remains removed. | 32 |
| MiniMax H3-Image | `minimax_h3_image_cuda` | `MiniMaxAI/MiniMax-H3-Image` | bf16 on disk, text encoder NVFP4 weight-only; transformer fp8 weight-only in the default entry and NVFP4 W4A4 in the second | 127 |
| LTX-2.5 | `ltx25_cuda` | `Lightricks/LTX-2.5-Diffusers` | bf16, the only build | 107 |
| Drama-3 | `drama3_cuda` | `fishaudio/drama-3` | FP8 W8A8, the build the release ships | 39 |
| YuE2 | `yue2_cuda` | `m-a-p/YuE2-3B` with `m-a-p/YuE2-Vae` | bf16 on disk and by default; the NVFP4 entry runs the lyrics stages with NVFP4 weights and activations from a pack built on first use, and the acoustic decoder and vocoder stay bf16 | 7.3 |

`Checkpoint` counts the files the backend reads, measured with `du` on this machine.
Two repositories ship more than that. H3-Image carries a second copy of its transformer, so the download is 190 GiB.
LTX-2.5 carries a second transformer, a distilled LoRA and the 9.6 GiB prompt enhancer, so the download is 163 GiB.

### How to read the numbers

**Free-memory drop (GiB)** is the fall from the baseline to the lowest `MemAvailable` sample, as a share of 121.7 GiB.
Current model states come from the recorded lifecycle and worker identities. A fresh child can load cached weights without a fresh pack build.
A resident request excludes a new model load. Historical first and warm labels alone do not prove residency or cache state.
**Process footprint (GiB)** is the peak sum of the resident memory of the child process tree.
On unified memory a resident figure under-reports the GPU allocation, so read it beside the free-memory drop. `not sampled` means no sample exists.
The campaign of 2026-11-15 sampled free memory only, because its harness reads `MemAvailable` once a second and does not walk the child process tree.
Those historical rows say `not sampled` for the footprint. Current source-tagged rows include sampled memory from their retained records.
The repository [`scripts/measure`](../../scripts/measure/README.md) recipes describe the earlier campaign.
The current campaign uses retained V3/V5 drivers and documented overlays in the companion evidence bundle.
The bundle records current manifests, asset provenance, source hashes, and process identities.
Historical rows can require their original revision, build, fixtures, or corrected payloads. The current matrix does not reproduce every historical experiment unchanged.
**Time (s)** is the operation's wall time. The queue wait is excluded.
Each current row reports one measured request. Some historical row occurrences map to the same current request.
The ledger records that reuse. A repeated table occurrence is not an extra measured repetition.
A cold run also pays a submit wait before the child starts, and that wait is inside its time.
These numbers apply to this machine. Another host has no calibrated estimate.

### Image

These are the builds the picker offers: Qwen-Image-2.1 Turbo in bf16, and H3-Image in fp8 or
NVFP4. Current Qwen NVFP4 checks use a configuration override on qwen21_turbo_cuda. The removed backend alias remains unsupported.

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `qwen21_turbo_cuda/generate/text/512`, bf16, first run (Source1) | generate, 512x512, 8 steps, bf16 | 34.72 | 18.75 | 26.0 | Succeeded (decoded) | 1 |
| `qwen21_turbo_cuda/generate/text/512`, bf16 (Source1) | generate, 512x512, 8 steps, bf16 | 0.01 | 2.16 | 3.0 | Succeeded (decoded) | 1 |
| `qwen21_turbo_cuda/generate/text/768`, bf16 (Source1) | generate, 768x768, 8 steps, bf16 | 2.90 | 2.18 | 7.0 | Succeeded (decoded) | 1 |
| `qwen21_turbo_cuda/generate/text/1024`, bf16 (Source1) | generate, 1024x1024, 8 steps, bf16 | 3.81 | 2.18 | 12.0 | Succeeded (decoded) | 1 |
| `qwen21_turbo_cuda/generate/text/1328`, bf16 (Source1) | generate, 1328x1328, 8 steps, bf16, decoded 1312x1312 | 5.76 | 2.20 | 20.0 | Succeeded (decoded) | 1 |
| `minimax_h3_image_cuda/generate/text/1024` (Source1) | generate, 1024x1024, 6 steps, NVFP4 W4A4, reported steps 6 | 0.01 | 2.39 | 33.1 | Succeeded (decoded) | 1 |
| `minimax_h3_image_cuda/generate/text/1024-fp8` (Source1) | generate, 1024x1024, 6 steps, fp8 weights | 0.01 | 2.41 | 55.2 | Succeeded (decoded) | 1 |

The Source1 BF16 rows contain the current 2026-11-16 request measurements. First and resident requests have separate explicit states.
The Turbo checkpoint ships its own eight-step schedule, so a 20-step request samples the same eight steps.
The following quality comparison is historical, from 2026-11-15. It compares FP8 with NVFP4 at one prompt and seed: at one prompt and seed, speckle fell from 3.94 to 2.04 and the smoothest 32x32 patch went from 5.99 to 2.17 standard deviation.
The H3 cold rows predate the load work of 2026-11-14 and 2026-11-15. The fp8 load alone measured 722.0 s, then 203.1 s once each weight travelled through host memory, then 33.4 s from the pack.
That campaign measured a 100.3 s cold Studio run and a 55.2 s warm run.
The later FP8 fixture checks below measure 54.393–54.766 s for resident-model HTTP requests. They use different prompts and seed 731.

#### The NVFP4 builds, 2026-11-15

The current Qwen rows use qwen21_turbo_cuda with quantize=nvfp4. The retired backend alias stays unsupported.
Each source tag identifies its measured build. Historical H3 pack attempts keep their original scope.

| Case | Settings | Free-memory drop (GiB) | Time (s) | Result |
|---|---|---|---|---|
| `qwen21_turbo_cuda/generate/512`, first run (NVFP4 configuration) (Source2) | NVFP4, 512x512, 8 steps, reported steps 8 | 34.86 | 31.1 | Succeeded (decoded) |
| `qwen21_turbo_cuda/generate/512` (NVFP4 configuration) (Source2) | NVFP4, 512x512, 8 steps, reported steps 8 | 0.01 | 3.0 | Succeeded (decoded) |
| `qwen21_turbo_cuda/generate/768` (NVFP4 configuration) (Source2) | NVFP4, 768x768, 8 steps, reported steps 8 | 2.94 | 6.0 | Succeeded (decoded) |
| `qwen21_turbo_cuda/generate/1024` (NVFP4 configuration) (Source2) | NVFP4, 1024x1024, 8 steps, reported steps 8 | 3.32 | 11.0 | Succeeded (decoded) |
| `qwen21_turbo_cuda/generate/1328` (NVFP4 configuration) (Source2) | NVFP4, 1328x1328, 8 steps, reported steps 8, decoded 1312x1312 | 5.69 | 18.0 | Succeeded (decoded) |
| `qwen21_turbo_cuda/edit/one-ref/match` (NVFP4 configuration) (Source2) | NVFP4, 512 out, 1 reference, reported steps 8 | 0.21 | 3.1 | Succeeded (decoded) |
| `qwen21_turbo_cuda/edit/big-ref/match` (NVFP4 configuration) (Source2) | NVFP4, 1344 out, 1 reference at 2048, reported steps 8 | 6.50 | 25.2 | Succeeded (decoded) |
| `minimax_h3_image_cuda_nvfp4/generate/1024`, first attempt (historical) | NVFP4, 1024x1024, 6 steps | -1.98 | 200.4 | Failed: the child died while the pack was written |
| `minimax_h3_image_cuda_nvfp4/generate/1024`, first run (Source1) | NVFP4, 1024x1024, 6 steps, reported steps 6 | 45.77 | 57.2 | Succeeded (decoded) |
| `minimax_h3_image_cuda_nvfp4/generate/1024` (Source1) | NVFP4, 1024x1024, 6 steps, reported steps 6 | 0.01 | 33.1 | Succeeded (decoded) |
| `minimax_h3_image_cuda_nvfp4/edit/one-ref/match` (Source1) | NVFP4, 1 reference at 4 MP, reported steps 6 | 0.86 | 45.3 | Succeeded (decoded) |

**Historical decision, 2026-11-15.** The Qwen pack quantizes the weights at load, so it adds nothing to the disk and its first
run is 20.1 s against the bf16 build's 25.1 s. Against the bf16 rows it is 5 to 14% faster
and holds 36.0 GiB against 40.7. That did not pay for the grain.

**Historical pack builds, 2026-11-15.** The H3-Image pack is written to disk first: 38 GB at `~/.cache/open-imagine/h3-pack-nvfp4`.
The first run is that build and load, not a sample, and it took two attempts: the first child
died while the pack was written and the parent reported "the engine stopped answering" after
200.4 s. A warm run is 34.3 s against fp8's 57.4.

#### The precision sweep on H3-Image

This historical experiment retains its original child-module path and precision builds. It is not a current studio API request.
Three builds ran one prompt and seed through a script that loads the child module and calls its
run, in the pattern the child uses. These times compare with each other, not with a studio row.

| Build | Warm (s) | Grain, portrait |
|---|---|---|
| nvfp4 W4A4 | 32.1 | 1.58 |
| fp8 weight only | 55.5 | 0.69 |
| int8 W8A8 | 67.3 | 0.63 |

int8 gives the cleanest picture and the slowest run. The store is not the cost: per-token
activation quantization costs more than the int8 matmul saves. On this stack only the fused fp4
kernel is fast, and that is why the nvfp4 build leads.
Grain is the standard deviation of the flattest 32x32 block on a 0 to 255 luminance scale,
measured on the portrait at the default canvas. It ranks the three builds at one prompt; the
speckle figures above come from a different case.

#### The canvas is larger than the request

`get_image_canvas_size` at `before_denoise.py:94` scales the generation up when the request is
below `min_generation_area`, whose default is 4194304 at `before_denoise.py:187`. A 1024x1024
request becomes a 2048x2048 canvas, and every request from 576x1024 to 1536x864 lands on the same
4.2 MP canvas. That is why the time was flat across sizes.

The 2026-11-15 to 2026-11-16 check uses FP8, six steps, seed 731, and 1024×1024 output.
Each prompt runs at both canvas areas through the Studio operation path. CUDA synchronization brackets the pipeline call.

| Public fixture | Default 2048×2048 pipeline (s) | Native 1024×1024 pipeline (s) | Default HTTP operation (s) | Native HTTP operation (s) |
| --- | ---: | ---: | ---: | ---: |
| Mountain lake and smooth sky | 56.036 | 39.607 | 99.345, includes pack loading | 39.912 |
| Window portrait | 54.416 | 39.503 | 54.766 | 39.852 |
| Matte ceramic vase | 54.039 | 39.685 | 54.393 | 40.101 |

Pipeline timings exclude pack loading, PNG encoding, and transport. The first default HTTP operation includes loading; the later default requests reuse the resident model.
The native sky shows broad purple and blue blotches. Independent inspection confirms this defect.
Portrait content also changes, so its detail comparison remains qualitative. This sample supports keeping the existing canvas floor.
It does not establish a quality-preserving fix or explain the difference from MLX.

An earlier child-module probe measured 32.4 s at the default canvas and 20.6 s at the native canvas.
Its build is not identified in that record, so those figures are not the latest FP8 baseline.
The earlier MLX quality comparison was not rerun in the latest pass.

#### `num_inference_steps` does nothing

`before_denoise.py:679` builds the timesteps from `components.config.sample_sigmas`, so a run
asked for one step still takes the checkpoint's six. That is why one step and six steps measured
the same. The 32.1 s is six denoise steps at about 5 s each, plus 2.5 s of VAE decode.

#### Edits run the same checkpoint on both image backends

Neither engine needs a second model for an edit. The diffusers Qwen-Image-2.1 pipeline
conditions on reference images through its Qwen3-VL text encoder and its vae. The H3 pipeline
switches to its image-conditioned blocks when `image` is set, which resize the references for the
vae and for the text encoder. The Source1 table below contains current 2026-11-16 measurements through the studio API.
The following load and free-memory figures describe historical 2026-11-15 experiments.

| Case | Time (s) |
|---|---|
| Qwen generate, 512x512, 8 steps, warm (Source1) | 3.0 |
| Qwen edit, one reference, match (Source1) | 4.1 |
| Qwen edit, two references, match (Source1) | 4.2 |
| H3 generate, 1024x1024, 6 steps, cold (Source1) | 89.4 |
| H3 edit, one reference, match at 4 MP (Source1) | 68.4 |

The first Qwen run of that studio took 18.0 s and carries the load. The H3 run carries its 33.4 s
pack load and generated on the engine's 4.2 MP canvas, so its 4 MP edit is the comparable row.
A warm edit moved free memory by 0.00 GiB on Qwen and 0.27 GiB on H3, because the model was
already resident in both cases: the peak is the model's own.

H3's edit offers only sizes of about 4 MP, because an edit at 1024 came out posterized on the MLX
engine and this backend inherits the model's behaviour. Its Match follows the first reference's
aspect at that size, on the 32-pixel grid. Qwen's Match follows the last reference at its own
area, also on the 32-pixel grid and under the 1344 cap the MLX edit path uses.

#### The Qwen prompt rewriters run on this machine too

The same two 9B cards the Mac loads, through transformers instead of mlx-vlm, with the
instructions, the language nudge and the sampling taken from `qwen_runtime/rewriter_text` so
both machines ask the same question. The Source2 rewrite rows below were measured on 2026-11-16 after explicit backend selection.

| Case | Time (s) | Output |
|---|---|---|
| Rewrite for generate, first press (Source2) | 109.3 | Structured result retained |
| Rewrite for edit, with a picture (Source2) | 246.7 | Structured result retained |

Each current rewrite timer includes a fresh enhancer load. The retained selection proof identifies the requested backend.
The older 19.61 GiB memory observation remains historical and does not describe these current requests.

The H3-Image 27B enhancer uses the published quantized checkpoint. ModelOpt NVFP4 storage decodes to BF16 runtime weights.
Its approximately 17 GB disk size is not its runtime memory footprint. The Source3 timings below include a fresh enhancer load:

| Case | Time (s) | Output |
|---|---|---|
| Enhance for generate, first press (Source3) | 315.8 | Structured result retained |
| Enhance for edit, with a picture (Source3) | 415.2 | Structured result retained |

One enhancer supports both modes. These current Source3 requests start from a released model state.
The older 21 GiB memory observation does not establish current residency or memory cost.
The corrected image markers pass real one-reference and two-reference requests. These checks do not prove complete caption fidelity.

### Video

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `ltx25_cuda/generate/text/768x448x97` (Source1) | generate, 768x448, 97 frames, distilled eight-step schedule | 0.32 | 12.43 | 46.4 | Succeeded (decoded) | 1 |
| `ltx25_cuda/generate/text/1280x704x97` (Source1) | generate, 1280x704, 97 frames, distilled eight-step schedule | 8.38 | 13.13 | 117.4 | Succeeded (decoded) | 1 |
| `ltx25_cuda/generate/text/768x768x97-fast` (historical) | generate, 768x768, 97 frames, Fast mode | 0.36 | 11.6 | 76.3 | Succeeded | 1 |
| `ltx25_cuda/generate/text/768x768x97` (Source1) | generate, 768x768, 97 frames, distilled eight-step schedule | 5.66 | 12.81 | 76.4 | Succeeded (decoded) | 1 |
| `ltx25_cuda/generate/keyframe/768x512x97` (Source1) | generate, 768x512, 97 frames, one keyframe at frame 0, strength 1.0 | 0.04 | 11.84 | 56.5 | Succeeded (decoded) | 1 |

The Source1 rows contain current request timings. The historical Fast row retains its original payload and result.
The current backend rejects Fast mode. Current keyframe requests and the explicit rejection check pass.
The following load experiments remain historical.

The first run of the 768x448 case took 96.4 s, which includes a 32.3 s load. The load was 189.2 s before each weight travelled through host memory.
The keyframe row is one press on a fresh server: it carries the same 32-second load, and its
first frame is the reference picture. The pipeline takes the reference as an
`LTX2VideoCondition` and re-compresses it at the model's own CRF before the vae sees it, which
needs PyAV in the child environment.
The clip is a 1.4 MB MP4. `LTX2DFRPipeline` runs the checkpoint's distilled eight-value sigma list, which is what the MLX backend runs when it takes its distilled path; `LTX2Pipeline` would run a linear thirty-step schedule at 3.75 times the cost.

#### Updated LTX CUDA checks, 2026-11-15 to 2026-11-16

The new public fixture is "A red toy train moves across a wooden table. Fixed camera, warm daylight."
Both operations use BF16, seed 7, 97 frames, 24 frames per second, prompt enhancement, and audio.
These are uninstrumented Studio operations after the frame-conversion change.

| Size | Model state | Submit to terminal status (s) | Process footprint |
| --- | --- | ---: | --- |
| 768×768 | Fresh child; includes model loading | 114.041 | Not sampled |
| 1280×704 | Model resident; first request at this size | 121.371 | Not sampled |

Both MP4 files match their original outputs byte for byte, including audio.
The original fixture runs contain stage synchronization and scratch writes, so their total times cannot establish a complete-request speed ratio.
The new prompt and load states also prevent replacing the historical 74.4 s and 115.5 s rows with these figures.

The separate encoding comparison uses the saved frames, three alternating repetitions per path, and a fresh Python process for each encoding.
Its timer excludes imports and fixture loading. It includes the range check, encoding, and reading the MP4 bytes.

| Encoding fixture | Original median (s) | Current median (s) | Original peak process memory (GiB) | Current peak process memory (GiB) |
| --- | ---: | ---: | ---: | ---: |
| 768×768, 97 frames | 1.332 | 1.116 | 2.810 | 1.503 |
| 1280×704, 97 frames | 3.952 | 1.347 | 3.876 | 1.902 |

Each fixture's six encoded MP4 files match exactly. Saved float32 audio differs from the original tensor's conversion; both encoding paths use that same fixture.
The uninstrumented Studio checks above separately establish exact original audio parity. These memory figures are process peaks, not GPU allocations or historical free-memory drops.

### Voice

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `drama3_cuda/generate/sentence50` (Source1) | generate, 7 words, 5.4 s of decoded audio at 44100 Hz | 0.41 | 4.06 | 8.0 | Succeeded (decoded) | 1 |
| `drama3_cuda/generate/short` (Source1) | generate, 13 words, one delivery cue | 0.36 | 4.06 | 7.0 | Succeeded (decoded) | 1 |
| `drama3_cuda/generate/paragraph700` (Source3) | generate, 83 words, 32.6 s of decoded audio at 44100 Hz | 1.38 | 4.06 | 45.1 | Succeeded (decoded) | 1 |
| `drama3_cuda/generate/paragraph700`, second pass (Source3) | generate, 83 words, 32.6 s of decoded audio at 44100 Hz | 1.30 | 4.07 | 45.1 | Succeeded (decoded) | 1 |
| `drama3_cuda/clone/ref7s` (Source1) | clone, 7 s reference, 4.5 s of decoded audio at 44100 Hz | 0.31 | 4.19 | 7.1 | Succeeded (decoded) | 1 |
| `mandarin/voice/traditional` (Source1) | generate, Traditional Chinese, 3.7 s of decoded audio at 44100 Hz | 0.02 | 3.97 | 6.0 | Succeeded (decoded) | 1 |
| `mandarin/voice/simplified` (Source1) | generate, Simplified Chinese, 3.9 s of decoded audio at 44100 Hz | 0.32 | 3.97 | 6.0 | Succeeded (decoded) | 1 |
| `mandarin/voice/paragraph` (Source1) | generate, Traditional Chinese, 19.6 s of decoded audio at 44100 Hz | 2.07 | 4.03 | 27.1 | Succeeded (decoded) | 1 |
| `mandarin/voice/generate-same-text` (Source1) | generate, no reference, 4.2 s of decoded audio at 44100 Hz | 0.35 | 4.03 | 6.0 | Succeeded (decoded) | 1 |
| `mandarin/voice/clone-tw-reference` (Source1) | clone, synthetic zh_TW reference, 3.6 s of decoded audio at 44100 Hz | 0.30 | 4.07 | 6.1 | Succeeded (decoded) | 1 |
| `mandarin/voice/clone-4s6` (Source1) | clone, 4.6 s human reference, 2.7 s of decoded audio at 44100 Hz | 0.25 | 4.07 | 5.0 | Succeeded (decoded) | 1 |
| `mandarin/voice/clone-10s` (Source1) | clone, 10 s human reference, 2.7 s of decoded audio at 44100 Hz | 0.29 | 4.07 | 5.1 | Succeeded (decoded) | 1 |

**Historical loader experiment, 2026-11-15.** The first Drama-3 run of a server took 350.7 s against 9.0 s warm, and the cost was the load, not a kernel compile: the engine copies each weight straight from the safetensors mapping into a device tensor, which measured 0.19 GB/s. Cloning each one into ordinary memory first took the load to 27.0 s and a first run to 38.1 s, with the audio byte-identical.
The historical outputs ran at 0.66x realtime on the 7-word English case and 0.72x on the 83-word one, and at 0.56x on the Mandarin sentence.
The three clone rows are one target sentence with three references; each first run paid the load.
Unconditioned Chinese completes but mispronounces: transcribing the output, 帶傘 came back as 呆散 and 可能 as 河冷. The clone rows read the same sentence correctly. The MLX backend mispronounces the same way, so this is the model, not the engine.
A synthetic reference clones a synthetic voice. The human reference rows are the ones to judge accent by.

The current paragraph rows use two distinct requests after the sentence warmup. Both requests retain the same worker identity.
Their HTTP times are 45.094 and 45.080 seconds. Their WAV bytes and full decoded samples match exactly.
The current YuE short first/repeat rows also use distinct requests with one worker. Their full decoded samples match; containers differ.

#### No compile path, and fp16 does not lift the decode

`ModelManager(compile=True)` stops with `ValueError: --compile is not supported for Drama 3
checkpoints`, raised at `fish_speech/models/text2semantic/inference.py:447`. The child already
passes `compile=False` for that reason.

`--half` does not lift the rate either. Through one probe, the bf16 run decoded 234 frames in
12.37 s, 18.91 frames per second, and the fp16 run decoded 158 frames in 8.40 s, 18.81 frames per
second. The fp16 run took 9.0 s instead of 14.7 s only because it stopped at the end of speech
after 7.34 s of audio instead of 10.87 s. The decode rate is the same, so the datatype is not a
lever. Time follows the audio length at about 19 frames per second.

### Music

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `yue2_cuda/generate/short` (Source1) | nvfp4, generate, style and one lyric line, 104.4 s of decoded audio at 48000 Hz | 10.29 | 5.35 | 120.3 | Succeeded (decoded) | 1 |
| `mandarin/music/verse` (Source1) | nvfp4, generate, Mandarin style and lyric, 34.6 s of decoded audio at 48000 Hz | 3.30 | 5.47 | 33.1 | Succeeded (decoded) | 1 |
| `yue2_cuda/generate/short` (Source3) | bf16, generate, style and one lyric line, 67.6 s of decoded audio at 48000 Hz | 6.90 | 9.66 | 117.2 | Succeeded (decoded) | 1 |
| `mandarin/music/verse` (Source1) | bf16, generate, Mandarin style and lyric, 41.7 s of decoded audio at 48000 Hz | 6.19 | 9.78 | 98.2 | Succeeded (decoded) | 1 |
| `yue2_cuda/generate/short` (Source2) | fp8, generate, style and one lyric line, 65.0 s of decoded audio at 48000 Hz | 18.59 | 14.29 | 203.4 | Succeeded (decoded) | 1 |
| `mandarin/music/verse` (Source2) | fp8, generate, Mandarin style and lyric, 56.9 s of decoded audio at 48000 Hz | 6.64 | 11.26 | 131.3 | Succeeded (decoded) | 1 |

**Historical precision comparison, 2026-11-15.** One build per pair used the same payload, seed, and child environment: torch 2.15.0, torchao 0.18.0, mslk 1.4.0. The English case is the first run of each
build, so it carries that build's start; the Mandarin case is warm. Per second of audio the Mandarin
rows are the comparison: nvfp4 0.96 s, bf16 2.43 s, fp8 2.64 s. The run on 2026-11-14 measured
1.19, 2.28 and 2.61 for the same three builds, so read the last digit as noise and the ratio as the
result: nvfp4 is about 2.5 times faster per second of audio.
The same seed wrote a different song in each build, so compare seconds per second of audio rather
than total seconds.
`fp8` is the engine's own `FP8Linear`, the arithmetic its authors mark experimental.
The same song came back in each build on both dates, which is the seed holding. The nvfp4 pack is
1.80 GB and takes the cold start from 111.4 s, cold Triton cache included, to 19.1 s; the English row
in that historical comparison carries 19.1 s of pack load instead of the build. The pack is rebuilt when the torch, torchao or
mslk version changes.

The source-tagged lyric-length rows below contain current request timings. The retained metadata records each decoded audio duration.
Historical token-limit and quality experiments retain their own original scope.

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `yue2_cuda/generate/lyrics-4-lines` (Source1) | generate, one repeated line, 159 characters, 39.8 s of decoded audio at 48000 Hz | 6.47 | 9.90 | 91.2 | Succeeded (decoded) | 1 |
| `yue2_cuda/generate/lyrics-8-lines` (Source1) | generate, one repeated line, 311 characters, 77.6 s of decoded audio at 48000 Hz | 7.18 | 9.93 | 137.3 | Succeeded (decoded) | 1 |
| `yue2_cuda/generate/lyrics-12-lines` (Source1) | generate, one repeated line, 463 characters, 84.9 s of decoded audio at 48000 Hz | 6.54 | 9.96 | 144.3 | Succeeded (decoded) | 1 |
| `yue2_cuda/generate/lyrics-16-lines` (historical) | generate, one repeated line, 615 characters, 118.7 s of audio | 8.04 | 9.6 | 179.4 | Succeeded | 1 |
| `yue2_cuda/generate/long` (historical) | generate, style and 20 repeated lyric lines, 760 characters | 8.07 | 10.1 | 454.1 | Failed: the semantic stage reached its token limit | 1 |
| `yue2_cuda/generate/instrumental` (Source1) | generate, style and no lyrics, 187.5 s of decoded audio at 48000 Hz | 6.70 | 10.16 | 231.5 | Succeeded (decoded) | 1 |

The four `lyrics-N-lines` rows are the sweep behind the gateway's lyric limit: 615 characters finished and 760 did not, so the CUDA gateway refuses more than 600 characters before it starts, instead of failing after seven minutes.
The original Mac recipe uses 3,048 lyric characters for its 237.9 s long case, not the Spark recipe's 760 characters.
Those two rows do not establish a matched lyric-limit comparison.
The successful historical lyric cases did not truncate. The recorded NVFP4 compute figure is 0.79 s per second of audio.
An earlier build produced 40.0 s of Chinese audio in 176.4 s, against 114.5 s in 174.4 s for English.
Those figures do not describe the latest Torch 2.15 rows above.

#### Current request rejections, 2026-11-16

| Historical row | Current case | Result | Source |
| --- | --- | --- | --- |
| document-line-380 | spark/negative/ltx-fast | rejected | cf52268b6a1c4694102b44606c2c0f749b2f01d6c8e44742b087b3ff24515871 |
| document-line-489 | spark/yue2_cuda/generate/lyrics-16-lines | rejected | cf52268b6a1c4694102b44606c2c0f749b2f01d6c8e44742b087b3ff24515871 |
| document-line-490 | spark/yue2_cuda/generate/long | rejected | cf52268b6a1c4694102b44606c2c0f749b2f01d6c8e44742b087b3ff24515871 |


#### The bf16 sweep on this machine

The shipped music build is bf16, because the song is the product. The same style and seed at
four lyric lengths. The source-tagged rows below use current requests measured through the studio API on 2026-11-16:

| Case | Settings | Free-memory drop (GiB) | Time (s) | Result |
|---|---|---|---|---|
| `yue2_cuda/generate/short`, first run (Source3) | bf16, 33 characters, 67.6 s of decoded audio at 48000 Hz | 17.87 | 207.4 | Succeeded (decoded) |
| `yue2_cuda/generate/short`, warm (Source3) | bf16, 33 characters, 67.6 s of decoded audio at 48000 Hz | 6.90 | 117.2 | Succeeded (decoded) |
| `yue2_cuda/generate/mid272` (Source1) | bf16, 272 characters, 79.5 s of decoded audio at 48000 Hz | 5.64 | 147.3 | Succeeded (decoded) |
| `yue2_cuda/generate/mid413` (Source1) | bf16, 413 characters, 222.1 s of decoded audio at 48000 Hz | 7.82 | 333.9 | Succeeded (decoded) |
| `yue2_cuda/generate/long535` (Source1) | bf16, 535 characters, 136.0 s of decoded audio at 48000 Hz | 6.13 | 198.4 | Succeeded (decoded) |
| `yue2_cuda/generate/instrumental` (Source1) | bf16, style and no lyric, 187.5 s of decoded audio at 48000 Hz | 6.70 | 231.5 | Succeeded (decoded) |
| `yue2_cuda/plan/short` (Source1) | bf16, style and one lyric line | 1.72 | 17.0 | Succeeded (structured result) |
| `yue2_cuda/cover/ref20s` (historical) | bf16, cover from a 20 s reference, 93.9 s of audio | -0.05 | 126.3 | Succeeded |
| `yue2_cuda/transcribe/ref20s`, first run (historical) | bf16, transcribe a 20 s reference, `melody-full` | 1.02 | 39.1 | Succeeded |
| `yue2_cuda/transcribe/ref20s`, warm (historical) | bf16, transcribe a 20 s reference, `melody-full` | 0.52 | 21.1 | Succeeded |

The 20-second transcription and Cover rows retain their historical fixture and timings. Its public provenance remains unresolved.
Three Source3 requests use a verified new reference. They separately measure first transcription, repeated transcription, and cache-primed Cover.

A negative drop means the sampled free memory increased relative to baseline. These samples do not identify the cause of that increase.
The historical 413-character and 535-character requests produced different audio lengths. Current rows report their newly decoded durations.
Load state, cache state, and output duration limit these comparisons. These runs do not isolate the effect of lyric length.

#### Current verified-reference requests, 2026-11-16

Five historical transcription and Cover rows use one unresolved audio fixture. Their original numbers remain historical.
Three Source3 requests replace them with the first 20 seconds of a verified public instrumental.
The two transcription requests set seed seven. Cover retains the historical style, lyric, and seed.
The same worker performs generation before the first transcription. The consecutive repeat reuses its process-local transcription cache.
The two seeded structured responses match exactly. Cover follows that repeat and uses its cached transcription.
HTTP means Hypertext Transfer Protocol. Its time includes polling. Native operation time measures the server operation.
Do not compare these fields across columns.
The one-second polling interval sets the cached HTTP floor. Signed memory changes include background activity.
The negative change does not represent negative allocation or memory savings.

| Request | HTTP time (s) | Native operation time (s) | Signed free-memory drop (GiB) | Sampled peak RSS (GiB) |
| --- | ---: | ---: | ---: | ---: |
| state-repeat/yue/transcribe-new-reference-first | 27.144 | 26.81980 | 5.809 | 13.10 |
| state-repeat/yue/transcribe-new-reference-repeat | 1.068 | 0.07597 | -0.036 | 9.76 |
| state-repeat/yue/cover-new-reference | 72.229 | 71.25909 | 6.615 | 9.86 |

The original reference remains ineligible for current public measurements. Its metadata remains in the retained evidence.

#### The q8 path on this machine

This section preserves the historical 2026-11-15 CUDA q8 probe. The 33.1-second NVFP4 comparison is also historical.
This unsupported CUDA q8 configuration was not rerun in the current campaign.
`Int8WeightOnlyConfig` on the Mandarin payload produced 32.7 s of audio in 84.6 s, then 91.7 s.
Each run reloaded the audio decoder, 30.0 s and 39.6 s, so the lyric stages took 54.6 s and
52.1 s. The warm nvfp4 run of that payload takes 33.1 s and pays no decoder load, so q8 is at
least 1.6x slower on the lyric stages. The int8 store quarters the weight bytes, but every matmul
still runs in bf16 and pays a dequantization step, where the fp4 kernel takes both operands
natively.

#### Transcribe and cover on this machine

A later matched check uses a synthetic ten-second stereo melody, task `melody-full`, and the unchanged Studio request path.

| CUDA BF16 request | Before result cache (s) | With result cache (s) |
| --- | ---: | ---: |
| First request, cache miss | 46.1 | 31.1 |
| Identical repeated reference and task | 22.1 | 1.0 |

The runner polls once per second, so 1.0 second is its resolution floor.
All four response bodies match exactly. The cache changes no sampling or generation settings.
Both first requests miss the cache; their different totals do not measure a cache benefit.

The same synthetic reference checks the existing MLX cache on the M5 Pro: 20.2848 seconds first, then 0.0731 seconds repeated.
That runner polls every 50 milliseconds. Its cached latency is not directly comparable to the CUDA runner's one-second floor.

The CUDA engine has no transcriber, so the child runs the pinned upstream SheetSage2 script as
its own process, with the release's requirements added to the child's environment. Measured on
2026-11-15 on a 20-second reference with unresolved public provenance, task `melody-full`. The table below remains historical:

| Case | Time (s) | Result |
|---|---|---|
| Transcribe (historical) | 42.1 | native ABC with Vocal and Ins voices |
| Cover (historical) | 66.1 | 12.6 MB of 48 kHz stereo audio |

These historical rows retain their original reference and timings. Three verified-reference requests provide five current row replacements in the Source3 state checks.
On a cache miss, the song weights stay resident while the transcription script runs; its model is freed when it exits.
A cache hit reuses the saved result without starting that script. The Source3 replacement sequence uses a verified new20-second reference. Its Cover follows two transcriptions and can reuse their result.

### Kernels

Kernel measurements on this machine, one 4096-square linear layer:

Current probes use the recorded image-child interpreter with PyTorch 2.15.0+cu132, CUDA 13.2, and MSLK 1.4.0+cu130.
The linear script uses five warmups and 20 timed iterations with synchronized boundaries. These figures describe one iteration batch per case.
Warmed GEMM throughput spans 91.4 to 94.7 TFLOPS for BF16 at 2048, 4096, and 8192 square dimensions.
The weight row reports distinct physical storages, including quantization scales. It does not multiply logical tensor dimensions by logical element size.
The older weight-only 128 MiB entry has no matching retained measurement recipe. Its original value remains in the evidence ledger.
The archived W4A4 allocation probe independently confirms 128 to 36 MiB. The physical-storage probe adds the weight-only result.
These layer probes do not establish end-to-end pipeline speed or statistical significance.

| Measure | bf16 | NVFP4 weight-only | NVFP4 W4A4 |
|---|---|---|---|
| 512 tokens (Source3) | 0.23 ms | 0.44 ms | 0.08 ms |
| 4096 tokens (Source3) | 1.44 ms | 1.71 ms | 1.13 ms |
| 8192-square physical weights (Source3) | 128 MiB | 36 MiB | 36 MiB |

The kernel table measures isolated linear layers. It does not establish end-to-end pipeline latency.
Current model tables report supported FP8 and NVFP4 H3 requests separately. Successful execution does not establish equal output quality.
The latest kernel evidence records the current interpreter and package versions. Historical pipeline load experiments retain their original dates.

**The first load cost 236 s until the weights were materialized.** Moving safetensors' mmap-backed tensors straight to the device ran at 128 MB/s on this machine; the same tensors moved from ordinary memory at 14 GiB/s. A 16 GiB shard went from 135 s to 1.3 s, and a cold studio run from 242 s to 20 s.
H3-Image cannot hold a host copy of its 62 GiB transformer beside the device copy: that order died with `CUDA_ERROR_OUT_OF_MEMORY` at 110 GiB resident, because the host copy and the device copy come out of one pool. It now clones one group of aliased weights at a time and drops the clone as the group lands, so the temporary is one tensor rather than the model. Measured on 2026-11-14, the transformer move fell from 511.7 s to 48.5 s and the whole load from 722.0 s to 203.1 s. What remained was quantization: 95.9 s for the encoder and 58.7 s for the transformer.
A pack of the quantized weights removes repeated quantization and roughly halves the weight bytes.
Before the pack-copy change, the 2026-11-15 FP8 measurement took 647.6 s: 208.5 s to build and 439.1 s to write.
Its device-to-host copies ran at about 116 MB/s. The cached load took 33.4 s, with a byte-identical picture.
The verified pack payload contains 54,582,157,268 bytes, about 50.83 GiB, excluding container headers.

The 2026-11-16 writer check uses the existing packed weights and the current nonblocking copy helper.
It synchronizes the source CUDA device, frees unused CUDA reservation before copying, and releases pinned host memory after each component.

| Current pack measurement | Result |
| --- | ---: |
| Full cached-weight rewrite | 48.407 s |
| Stored tensors checked against the original | 3,722, all matching bytes, dtype, shape, and metadata |
| Observed peak process memory, sampled every 100 ms | 45.96 GiB |
| Lowest observed system memory available | 19.68 GiB |
| Peak allocated pinned host pool, including allocator rounding | 45.14 GiB |
| Allocated and active pinned bytes after each component | 0 |

The check first creates 24 GiB of unused CUDA reservation to represent retained allocations after quantization.
The writer releases it without changing active model allocation or weight pointers. The original pack remains unchanged.
This is a cached-weight rewrite, excluding cold quantization and `fsync`.
The separate Source3 campaign measures full fresh-pack builds and cached reloads. Those results appear beside the historical pack measurements.
The 48.407-second experiment remains a cached-weight rewrite. Subtracting it from the historical 439.1-second write does not establish cold-start improvement.

#### Fresh pack build and cached reload (Source3)

RSS means resident set size. The table reports sampled process memory.
Each case uses the same public harbour prompt, seed seven, six steps, and a 1024x1024 output.
Build requests begin with an absent owned pack directory. Reload requests start a fresh child with that newly written pack.
The request time includes child startup, model work, and output preparation. A cached reload is not a warm resident inference.
All fresh, reloaded, and matching original-pack outputs have identical PNG bytes, decoded pixels, and PNG metadata.
The comparison checks 3,722 FP8 and 4,095 NVFP4 tensor headers plus their pack manifests.
Tensor payload equality is not checked in this fresh-pack campaign.
The failed historical NVFP4 write remains unchanged. The new successful build closes its current execution coverage.

| Case | Time (s) | Sampled peak RSS (GiB) | Minimum sampled available memory (GiB) | Complete samples | Source |
| --- | ---: | ---: | ---: | ---: | --- |
| spark/fresh-pack/fp8/build-and-generate | 333.015 | 100.55 | 20.33 | 333 | Source3 |
| spark/fresh-pack/fp8/cached-reload-and-generate | 94.587 | 26.03 | 57.33 | 95 | Source3 |
| spark/fresh-pack/nvfp4/build-and-generate | 332.200 | 106.60 | 17.94 | 333 | Source3 |
| spark/fresh-pack/nvfp4/cached-reload-and-generate | 64.350 | 17.25 | 73.45 | 65 | Source3 |


**Historical residency experiment, 2026-11-15.** A retained model avoids its next load. The original check used
`[memory] policy = "boundary"`: a cold Qwen Turbo run took 31.1 s, an H3 run took 107.5 s
beside it, and Qwen again took 12.2 s without a reload. Under `immediate`, which is the
default, the third run pays Qwen's load again.

The same per-tensor order applies to LTX-2.5. Its load fell from 189.2 s to 32.3 s, and its clip is byte-identical. Qwen-Image-2.1 uses it too: 87.7 s for its whole components against 14.4 s one group at a time, with the picture byte-identical.

### Against the M5 Pro

The 2026-11-16 table compares current requests with matched public inputs and exposed settings.
Each ratio divides Mac request seconds by Spark request seconds. Engine, precision, output geometry, and lifecycle limit its meaning.

| Case | M5 Pro (s) | DGX Spark (s) | Ratio |
|---|---|---|---|
| Qwen Turbo generate, 512x512, 8 steps | 5.160 | 3.009 | 1.71x |
| Qwen Turbo generate, 768x768, 8 steps | 12.221 | 7.020 | 1.74x |
| Qwen Turbo generate, 1024x1024, 8 steps | 23.305 | 12.033 | 1.94x |
| Qwen Turbo generate, 1328x1328, 8 steps | 46.486 | 20.048 | 2.32x |
| LTX-2.5 generate, 768x768, 97 frames | 115.829 | 137.379 | 0.84x |
| Drama-3 generate, 7 words | 4.047 | 6.031 | 0.67x |
| YuE2 generate, instrumental (Spark BF16, Mac Q8) | 262.982 | 270.690 | 0.97x |
| Drama-3 clone, one reference | 4.047 | 6.060 | 0.67x |
| YuE2 generate, short (Spark NVFP4, Mac Q8) | 144.177 | 71.175 | 2.03x |
| YuE2 generate, Mandarin lyric (Spark NVFP4, Mac Q8) | 39.288 | 30.063 | 1.31x |
| Drama-3 generate, 83 words | 26.216 | 56.122 | 0.47x |
| MiniMax H3-Image generate, 1024x1024, 6 steps, Spark FP8, Mac int8 | 17.128 | 94.587 | 0.18x |
| MiniMax H3-Image generate, 1024x1024, 6 steps, Spark NVFP4, Mac int8 | 17.128 | 64.350 | 0.27x |

#### Current cross-host comparison details, 2026-11-16

All 12 Mac requests pass completion and full decoding. Four use the original server; eight use a fresh server with unchanged payloads.
The pre-request resource-tracker error remains a harness diagnostic. It submits no LTX request and supplies no timing.
One partial footprint sample is excluded from the process peak. The other samples remain in the raw records.
The table reuses compatible Spark requests. A repeated table occurrence is not another measurement.
User prompts, references, seeds, and exposed settings match after backend selection. Qwen cfg maps to CUDA guidance at the same explicit value.
The ratio divides Mac request time by Spark request time. It does not isolate hardware throughput.
Qwen uses eight steps, seed seven, and guidance one. Requested 1328-square output decodes to 1328 on MLX and 1312 on CUDA.
LTX uses 768x768, 97 frames, 24 frames per second, prompt enhancement, and audio on both hosts.
Both LTX requests include a fresh model load. The MLX engine uses a native q8 pack; CUDA uses BF16.
Drama compares an MLX 8-bit pack with CUDA FP8 W8A8. Its requests follow a same-backend warmup.
YuE requests also follow a same-backend warmup. MLX uses a Q8 generator, BF16 acoustic weights, and FP32 decoder weights.
CUDA uses BF16 for the instrumental and NVFP4 lyric stages for the short and Mandarin requests. Its acoustic decoder remains BF16.
H3 MLX uses per-call stages with a native int8 pack and a 1,048,576-pixel working canvas.
H3 CUDA starts fresh children with cached FP8 or NVFP4 packs and a 4,194,304-pixel working canvas.
Their requested 1024-square outputs and six-step setting match. Precision, working canvas, and lifecycle do not match.
These mixed execution paths do not establish a per-megapixel hardware ranking.
Audio duration differs across engines and precisions. The normalized rates below divide request time by actual decoded audio duration.
These rates include the recorded request lifecycle. They do not establish equal audio quality or equal acoustic work.

| Comparison | Mac audio (s) | Spark audio (s) | Mac request seconds per audio second | Spark request seconds per audio second |
| --- | ---: | ---: | ---: | ---: |
| Drama-3 generate, 7 words | 3.483 | 3.576 | 1.162 | 1.687 |
| YuE2 generate, instrumental (bf16) | 163.119 | 203.879 | 1.612 | 1.328 |
| Drama-3 clone, one reference | 3.390 | 3.204 | 1.194 | 1.891 |
| YuE2 generate, short (nvfp4) | 109.919 | 104.359 | 1.312 | 0.682 |
| YuE2 generate, Mandarin lyric (nvfp4), Spark warm | 42.239 | 34.599 | 0.930 | 0.869 |
| Drama-3 generate, 83 words | 34.830 | 40.449 | 0.753 | 1.387 |

[Platform comparison](platform-comparison.md) records the historical 2026-11-15 campaign and its estimate settings.
That historical page does not override the current Source1, Source2, or Source3 rows here.
Current cross-host comparisons require matching public requests and explicit model states, precisions, output contracts, and working canvases.

## Gateway performance checks, 2026-11-15 to 2026-11-16

The paired performance checks keep their recorded settings and fixtures. Encoding comparisons use the same public frames on both paths.
The correctness fixes intentionally change errors, privacy handling, cleanup, and previously broken prompt enhancement.
These measured controls do not claim unchanged behavior across all 33 modified runtime paths.

| Change or experiment | Host and measurement scope | Measured result | Decision |
| --- | --- | --- | --- |
| YuE2 CUDA transcription cache | DGX Spark, Studio operation | Repeated reference: 22.1 s to the runner's 1.0 s polling floor | Keep one result in memory |
| H3 video buffer view | M1 Pro, CPU encoding only | Traced Python peak: 251.09 MiB to 2.96 MiB; MP4 bytes match | Keep the buffer view |
| [LTX CUDA frame conversion](../../studio/l3_interface_adapters/gateways/video/ltx25_cuda/README.md) | DGX Spark, saved-frame CPU encoding | 1280×704 encoding: 3.952 s to 1.347 s; peak process memory: 3.876 GiB to 1.902 GiB | Convert one frame at a time |
| [H3-Image CUDA pack copies](../../studio/l3_interface_adapters/gateways/image/minimax_h3_image_cuda/README.md) | DGX Spark, cached-weight rewrite | Full rewrite: 48.407 s; all 3,722 tensors match | Use synchronized nonblocking copies and release unused caches |
| [FLUX.3 residency](../../studio/l3_interface_adapters/gateways/image/flux3/README.md) | M5 Pro, Studio generation | Three-request median saves 0.967 s, but retains 8.50 GiB | Keep one process per image |
| [Drama-3 cache policy](../../studio/l3_interface_adapters/gateways/voice/drama3/README.md) | M5 Pro, Studio speech operations | Final-only clearing saves under 2%, but adds about 0.70 GiB peak MLX allocation | Keep per-chunk clearing |
| H3-Image native canvas | DGX Spark, synchronized pipeline | Warm pipeline time falls about 27%, but the sky develops blotches | Keep the current canvas floor |

The pack rewrite excludes cold quantization and `fsync`. It is not a matched comparison with the historical 439-second write.
The encoding figures describe isolated encoding, not complete request latency. The backend notes contain settings, methods, memory costs, and limits.
On the M1 Pro, synthetic binary transport is faster than base64 JSON, but omits the product's cancellation, progress, and error behavior.
The measured LTX files contain about 0.8–1.1 MB, so this change keeps the current transport.

### Updated M5 Pro checks

The FLUX.3 comparison uses q8 weights, 512×512, 16 steps, seed 7, and a public ceramic-cup prompt.
Both paths use `HF_HUB_OFFLINE=1` and warm filesystem caches. All six PNG outputs match exactly.

| FLUX.3 request | Current process-per-image path (s) | Resident prototype (s) |
| --- | ---: | ---: |
| First | 9.342 | 9.412 |
| Second | 9.372 | 8.224 |
| Third | 9.397 | 8.405 |
| Median | 9.372 | 8.405 |

Only the prototype's second and third requests reuse a loaded model. Its 8.50 GiB idle MLX allocation outweighs this small saving.
These fixtures do not replace the earlier FLUX.3 size sweep or establish a new cold-machine time.

The Drama-3 comparison uses two fixed public scripts, seed 7, one warmup per policy, and three warm repetitions per script.
All paired audio bytes match. The measured audio lengths are 3.019 and 19.180 seconds.

| Drama-3 warm median | Current per-chunk clear (s) | Final-only clear prototype (s) |
| --- | ---: | ---: |
| Short script | 2.168 | 2.143 |
| Long script | 13.755 | 13.553 |

Final-only clearing adds about 0.70 GiB peak MLX allocation and 1.19 GiB sampled process memory. The current policy remains unchanged.
These scripts differ from the historical sentence, paragraph, clone, and Mandarin cases.

**Historical targeted check, 2026-11-15 to 2026-11-16.** The M5 Pro H3 smoke check generates 73 frames at 512×288.
Complete video and audio decoding pass, but the runner does not retain an exact request timer.
The current dated H3 matrix rows provide request timings. This older smoke check remains an untimed result.

### CPU component measurements on the M1 Pro

The H3 video comparison uses 97 frames at 1280×704, 24 frames per second, and stereo audio.
Python 3.12.9 and FFmpeg 9.0.2 encode three alternating repetitions per path.

| H3 video encoding | Median (s) | Peak traced Python allocation (MiB) |
| --- | ---: | ---: |
| Complete raw-video bytes copy | 5.99 | 251.09 |
| Current buffer view | 5.96 | 2.96 |

All six MP4 files match exactly. The timing establishes no meaningful encoding speed gain.
Traced Python memory excludes the original frame array, FFmpeg memory, and GPU allocations. It is not the M5 Pro process-footprint metric.

The transport comparison uses seven timing repetitions and a separate memory pass with a synthetic 64 MiB payload.

| Synthetic child transport | Median (s) | Peak parent Python allocation (MiB) |
| --- | ---: | ---: |
| Current base64 JSON | 0.5296 | 256.01 |
| Raw binary prototype | 0.0275 | 64.00 |

These are component measurements on the M1 Pro, not complete Studio requests or predictions of Spark throughput.

### What the latest pass covers

The measured production snapshot passes 3,555 CPU tests. All 13,212 statements and 3,400 branches have coverage.
The capability gate passes 70 checks. All 835 runtime, test, and gate file hashes match before and after that capability gate.
The current evidence checks 143 expected outcomes across 144 historical operation rows.
One measured request fails its expected success. No historical operation rows remain pending.
All 13 current comparison rows have matched request evidence. The MLX backend-switch check passes 19 checks.
The retained ledger records every historical row disposition.
The planned matrix has 183 distinct case IDs: 178 expected outcomes, four reference-replacement dispositions, and one unexpected failure.
Warmups, retries, fresh-pack checks, kernels, and other controls remain separate.
Current numeric rows identify their frozen source. Historical replacement fixtures and unsupported requests retain explicit dates and scope.
Eleven historical row occurrences require replacement fixtures. Three old requests have current rejection checks. These do not reproduce the older successful recipes.
The request matrix checks completion and output contracts. Successful decoding does not establish prompt fidelity. Each observed quality limit stays beside its result.
The retained evidence lists named browser and live gates separately. A live-test duration includes setup and teardown, so it does not replace request latency.
Component and prototype experiments retain their own hardware, fixtures, repetition counts, and limits. They do not predict complete product speed.


The historical operation ledger covers 144 row occurrences: 143 expected outcomes and one unexpected stopping-limit failure.
These outcomes include declared token limits and request rejections. They do not mean 143 successful media outputs.
Eleven row occurrences use explicit replacement fixtures. Three historical requests have current rejection checks.
Matched cross-host comparisons and the MLX backend-switch check are complete.
The retained evidence contains the complete row ledger, request manifests, source hashes, and fixture revisions.

Browser checks exposed two test defects: Look radio selection and a cancellation notice over the drawing canvas.
CPU controls reproduce both defects. The real batch check passes 12 checks, and both H3 MLX video live tests pass.
On Spark, Qwen CUDA passes a real generation test and browser checks for generation, edit, and cancellation.
A browser switch from Qwen CUDA to H3 CUDA also passes, including generation after the switch.
The corrected MLX page check passes all 181 checks.
The MLX backend-switch check passes all 19 checks, including FLUX.2 generation, edit, and Qwen generation.
Production code remains identical to the measured snapshots.
