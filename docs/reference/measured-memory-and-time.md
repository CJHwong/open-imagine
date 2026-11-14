# Measured memory and time

Measured peak memory and elapsed time for each case, on two machines: a Mac with an Apple M5 Pro and 64 gibibytes (GiB) of memory, and an NVIDIA DGX Spark with 121.7 GiB of unified memory.
Each machine has its own section: the models it ran, how to read its numbers, and one table per modality.

## Apple M5 Pro

The measurements ran on 2026-11-12 and 2026-11-13 through the studio API.
The measured tables hold 72 cases: 69 succeeded and 3 stopped at an engine limit.
The H3 rows used a pre-quantized MLX q8 pack, not a local build.

| Item | Value |
|---|---|
| Machine | Apple M5 Pro, 64 GiB |
| Date | 2026-11-12 and 2026-11-13 |
| Path | The studio API on a local port, one operation at a time |
| Seed | Video set 7. Voice and Music set 7 unless the case name names one. Image cases used the studio default. |
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

`Checkpoint` counts the files the backend reads from disk, measured with `du` on this Mac.
A pre-quantized pack is smaller than its source because the pack already holds the narrowed weights.
The Qwen prompt rewriters, the LTX adapters and the Viggle LoRA are separate downloads and are not in these figures.

### How to read the numbers

**Free-memory drop (GiB)** is the fall from the baseline to the lowest free-memory sample, as a share of 64 GiB.
**Process footprint (GiB)** is the peak sum of the memory footprint of every process in the server tree. It includes a model that an earlier case left warm.
**Time (s)** is the operation's wall time. The queue wait is excluded, because the runner waits for an idle server before it submits.
Each case has one row. `Runs` gives the recorded runs for that case name, and the row shows the last run.
A row with one run is one measurement, not an average. Machine load moves a time, so compare rows with that limit in mind.
These numbers apply to a 64 GiB Mac. Another host has no calibrated estimate.

### Image

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `flux3/generate/text/512` | flux3, generate, size 512x512 | 10.24 | 16.13 | 25.2 | Succeeded | 1 |
| `flux3/generate/text/768` | flux3, generate, size 768x768 | 9.60 | 21.09 | 20.1 | Succeeded | 1 |
| `flux3/generate/text/1024` | flux3, generate, size 1024x1024 | 38.40 | 35.09 | 38.3 | Succeeded | 1 |
| `minimax_h3_image/generate/1024` | minimax_h3_image, generate, size 1024x1024, 6 steps | 14.72 | 19.06 | 23.2 | Succeeded | 1 |
| `minimax_h3_image/generate/2048` | minimax_h3_image, generate, size 2048x2048, 6 steps | 8.32 | 20.07 | 51.4 | Succeeded | 1 |
| `minimax_h3_image/edit/one-ref-2048` | minimax_h3_image, edit, size match, 6 steps, 1 ref, input 2048x2048 | 3.20 | 4.39 | 153.2 | Succeeded | 1 |
| `qwen21/edit/10-refs/out1024` | qwen21, edit, size 1024, 10 refs | 37.12 | 81.02 | 818.3 | Succeeded | 1 |
| `qwen21/edit/2-refs/out1024` | qwen21, edit, size 1024, 2 refs | 31.36 | 67.02 | 272.2 | Succeeded | 1 |
| `qwen21/edit/4-refs/out1024` | qwen21, edit, size 1024, 4 refs | 35.84 | 67.02 | 461.8 | Succeeded | 1 |
| `qwen21/edit/8-refs/out1024` | qwen21, edit, size 1024, 8 refs | 35.20 | 77.02 | 739.1 | Succeeded | 1 |
| `qwen21/edit/each/out1024` | qwen21, edit, size 1024, 4 refs, each ref | 16.64 | 61.02 | 224.9 | Succeeded | 1 |
| `qwen21/edit/mask/out1024` | qwen21, edit, size 1024, 1 ref, mask | 30.72 | 65.02 | 275.3 | Succeeded | 1 |
| `qwen21/edit/one-ref/in1600x900` | qwen21, edit, size 1024, 1 ref, input 1600x900 | 17.92 | 61.02 | 240.1 | Succeeded | 1 |
| `qwen21/edit/one-ref/in2048x2048` | qwen21, edit, size 1024, 1 ref, input 2048x2048 | 18.56 | 61.02 | 230.9 | Succeeded | 1 |
| `qwen21/edit/one-ref/in4032x3024` | qwen21, edit, size 1024, 1 ref, input 4032x3024 | 28.16 | 63.02 | 244.1 | Succeeded | 1 |
| `qwen21/edit/one-ref/in512x512` | qwen21, edit, size 1024, 1 ref, input 512x512 | 33.92 | 67.02 | 240.3 | Succeeded | 1 |
| `qwen21/edit/one-ref/out1024` | qwen21, edit, size 1024, 1 ref | 33.28 | 61.02 | 215.5 | Succeeded | 1 |
| `qwen21/edit/one-ref/out1344` | qwen21, edit, size 1344, 1 ref | 40.96 | 71.02 | 454.3 | Succeeded | 1 |
| `qwen21/edit/one-ref/out512` | qwen21, edit, size 512, 1 ref | 21.76 | 60.02 | 42.3 | Succeeded | 1 |
| `qwen21/edit/one-ref/out768` | qwen21, edit, size 768, 1 ref | 26.88 | 65.02 | 108.0 | Succeeded | 1 |
| `qwen21/generate/text/1024` | qwen21, generate, size 1024x1024 | 32.64 | 54.02 | 179.5 | Succeeded | 1 |
| `qwen21/generate/text/1328` | qwen21, generate, size 1328x1328 | 18.56 | 55.02 | 273.2 | Succeeded | 1 |
| `qwen21/generate/text/512` | qwen21, generate, size 512x512 | 34.13 | 43.02 | 486.3 | Succeeded | 1 |
| `qwen21/generate/text/768` | qwen21, generate, size 768x768 | 24.32 | 50.02 | 66.7 | Succeeded | 1 |
| `qwen21_turbo/edit/10-refs/out1024` | qwen21_turbo, edit, size 1024, 10 refs | 55.68 | 69.02 | 629.9 | Succeeded | 1 |
| `qwen21_turbo/edit/2-refs/out1024` | qwen21_turbo, edit, size 1024, 2 refs | 51.20 | 52.02 | 60.5 | Succeeded | 1 |
| `qwen21_turbo/edit/4-refs/out1024` | qwen21_turbo, edit, size 1024, 4 refs | 52.48 | 55.02 | 87.8 | Succeeded | 1 |
| `qwen21_turbo/edit/8-refs/out1024` | qwen21_turbo, edit, size 1024, 8 refs | 56.32 | 64.02 | 506.2 | Succeeded | 1 |
| `qwen21_turbo/edit/each/out1024` | qwen21_turbo, edit, size 1024, 4 refs, each ref | 51.20 | 52.02 | 49.4 | Succeeded | 1 |
| `qwen21_turbo/edit/mask/out1024` | qwen21_turbo, edit, size 1024, 1 ref, mask | 51.41 | 52.02 | 61.5 | Succeeded | 1 |
| `qwen21_turbo/edit/one-ref/in1600x900` | qwen21_turbo, edit, size 1024, 1 ref, input 1600x900 | 51.20 | 50.02 | 53.7 | Succeeded | 1 |
| `qwen21_turbo/edit/one-ref/in2048x2048` | qwen21_turbo, edit, size 1024, 1 ref, input 2048x2048 | 50.56 | 51.02 | 50.9 | Succeeded | 1 |
| `qwen21_turbo/edit/one-ref/in4032x3024` | qwen21_turbo, edit, size 1024, 1 ref, input 4032x3024 | 51.41 | 52.02 | 51.5 | Succeeded | 1 |
| `qwen21_turbo/edit/one-ref/in512x512` | qwen21_turbo, edit, size 1024, 1 ref, input 512x512 | 50.56 | 51.02 | 53.9 | Succeeded | 1 |
| `qwen21_turbo/edit/one-ref/out1024` | qwen21_turbo, edit, size 1024, 1 ref | 51.84 | 51.02 | 49.5 | Succeeded | 2 |
| `qwen21_turbo/edit/one-ref/out1344` | qwen21_turbo, edit, size 1344, 1 ref | 52.48 | 52.02 | 94.8 | Failed: the engine ran out of memory | 2 |
| `qwen21_turbo/edit/one-ref/out512` | qwen21_turbo, edit, size 512, 1 ref | 50.56 | 50.02 | 15.1 | Succeeded | 1 |
| `qwen21_turbo/edit/one-ref/out768` | qwen21_turbo, edit, size 768, 1 ref | 51.20 | 51.02 | 28.2 | Succeeded | 1 |
| `qwen21_turbo/generate/text/1024` | qwen21_turbo, generate, size 1024x1024 | 51.20 | 49.02 | 32.3 | Succeeded | 1 |
| `qwen21_turbo/generate/text/1328` | qwen21_turbo, generate, size 1328x1328 | 50.56 | 51.02 | 69.6 | Succeeded | 1 |
| `qwen21_turbo/generate/text/512` | qwen21_turbo, generate, size 512x512 | 28.80 | 29.02 | 9.1 | Succeeded | 1 |
| `qwen21_turbo/generate/text/768` | qwen21_turbo, generate, size 768x768 | 33.92 | 30.02 | 17.2 | Succeeded | 1 |

### Video

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `ltx25/generate/1-keyframes/768x768x97` | ltx25_mlx, generate, 768x768, 97 frames, 1 keyframe, no enhance | 16.64 | 55.04 | 162.3 | Succeeded | 1 |
| `ltx25/generate/2-keyframes/768x768x97` | ltx25_mlx, generate, 768x768, 97 frames, 2 keyframes, no enhance | 16.64 | 56.04 | 171.4 | Succeeded | 1 |
| `ltx25/generate/4-keyframes/768x768x97` | ltx25_mlx, generate, 768x768, 97 frames, 4 keyframes, no enhance | 18.35 | 56.04 | 199.7 | Succeeded | 1 |
| `ltx25/generate/8-keyframes/768x768x97` | ltx25_mlx, generate, 768x768, 97 frames, 8 keyframes, no enhance | 18.56 | 59.04 | 245.9 | Succeeded | 1 |
| `ltx25/generate/audio/768x768x97` | ltx25_mlx, generate, 768x768, 97 frames, no enhance, audio track | 24.96 | 58.04 | 849.1 | Succeeded | 2 |
| `ltx25/generate/fast/768x768x121` | ltx25_mlx, generate, 768x768, 121 frames, fast mode | 20.48 | 51.04 | 149.1 | Succeeded | 1 |
| `ltx25/generate/frames/121` | ltx25_mlx, generate, 768x768, 121 frames | 15.36 | 51.04 | 200.6 | Succeeded | 1 |
| `ltx25/generate/frames/25` | ltx25_mlx, generate, 768x768, 25 frames | 15.36 | 50.04 | 59.4 | Succeeded | 1 |
| `ltx25/generate/frames/49` | ltx25_mlx, generate, 768x768, 49 frames | 13.44 | 51.04 | 88.7 | Succeeded | 1 |
| `ltx25/generate/no-enhance/768x768x97` | ltx25_mlx, generate, 768x768, 97 frames, no enhance | 21.76 | 51.04 | 160.3 | Succeeded | 1 |
| `ltx25/generate/text/1280x704x97` | ltx25_mlx, generate, 1280x704, 97 frames | 14.08 | 53.04 | 269.2 | Succeeded | 1 |
| `ltx25/generate/text/1920x1088x97` | ltx25_mlx, generate, 1920x1088, 97 frames | 14.08 | 59.04 | 750.9 | Succeeded | 1 |
| `ltx25/generate/text/384x384x25` | ltx25_mlx, generate, 384x384, 25 frames | 21.33 | 49.04 | 26.2 | Succeeded | 1 |
| `ltx25/generate/text/768x768x97` | ltx25_mlx, generate, 768x768, 97 frames | 16.00 | 24.07 | 117.9 | Succeeded | 3 |
| `minimax_h3/generate/text/512x288x73` | minimax_h3, generate, 512x288, 73 frames, 24 fps | 26.24 | 33.07 | 120.0 | Succeeded | 2 |
| `minimax_h3/generate/text/1024x576x175` | minimax_h3, generate, 1024x576, 175 frames, 24 fps | 36.48 | 33.07 | 1608.8 | Succeeded | 1 |

### Voice

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `drama3/clone/ref15s` | drama3, clone, 7 words, ref 15s | 42.24 | 68.03 | 5.1 | Succeeded | 1 |
| `drama3/clone/ref5s` | drama3, clone, 7 words, ref 5s | 40.96 | 67.03 | 4.1 | Succeeded | 1 |
| `drama3/generate/paragraph700` | drama3, generate, 83 words | 41.60 | 67.03 | 29.2 | Succeeded | 1 |
| `drama3/generate/sentence50` | drama3, generate, 7 words | 41.60 | 67.03 | 25.2 | Succeeded | 1 |
| `drama3/generate/text1000` | drama3, generate, 200 words | 40.96 | 67.03 | 83.7 | Failed: the audio reached max_tokens | 2 |
| `drama3/generate/text4000` | drama3, generate, 800 words | 41.60 | 67.03 | 83.7 | Failed: the audio reached max_tokens | 2 |
| `drama3/generate/text50-seed11` | drama3, generate, 10 words, seed 11 | 43.52 | 40.06 | 30.2 | Succeeded | 1 |

### Music

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `yue2/cover/speech10s` | yue2, cover, style, lyrics, 10 s speech reference | 6.40 | 8.93 | 18.2 | Succeeded | 1 |
| `yue2/generate/instrumental` | yue2, generate, style, instrumental | 4.48 | 36.02 | 283.2 | Succeeded | 1 |
| `yue2/generate/long` | yue2, generate, style, lyrics | 3.84 | 36.02 | 237.9 | Succeeded | 1 |
| `yue2/generate/short` | yue2, generate, style, lyrics | 3.84 | 36.02 | 160.2 | Succeeded | 1 |
| `yue2/plan/short` | yue2, plan, style, lyrics | 3.20 | 35.40 | 10.1 | Succeeded | 1 |
| `yue2/transcribe/speech10s` | yue2, transcribe, 10 s speech reference | 1.92 | 4.23 | 7.1 | Succeeded | 1 |
| `yue2/transcribe/speech15s` | yue2, transcribe, 15 s speech reference | 1.92 | 4.24 | 5.1 | Succeeded | 1 |

### Mandarin, 2026-11-14

| Case | Settings | Time (s) | Audio | Result |
|---|---|---|---|---|
| `mandarin/voice/traditional` | drama3, generate, Traditional Chinese | 34.3 | 5.1 s of 44.1 kHz mono | Succeeded |
| `mandarin/voice/simplified` | drama3, generate, Simplified Chinese | 4.3 | 4.4 s of 44.1 kHz mono | Succeeded |
| `mandarin/voice/paragraph` | drama3, generate, Traditional Chinese | 75.7 | none | Failed: the audio reached max_tokens |
| `mandarin/music/verse` | yue2, generate, Mandarin lyric | 57.4 | 42.2 s of 48 kHz stereo | Succeeded |

These ran on this Mac through the same studio on the case file `cases.mandarin.json`, outside the campaign above, so they carry no free-memory or footprint sample.
The paragraph fails here at the MLX backend's token cap, where the CUDA backend completed the same paragraph in 27.1 s.
The music row pays its own first load.

### Not tested

The table lists the models that produced no measurement because a weight or runtime was missing.
Complete the setup, then rerun the named case file.

| Model | Cases | What is missing | To complete |
|---|---|---|---|
| flux2 | 7 cases: `flux2/generate/text/512`, `flux2/generate/text/768`, `flux2/generate/text/1024`, `flux2/generate/match/in1600x900`, `flux2/edit/one-ref/in512x512`, `flux2/edit/one-ref/in2048x2048`, `flux2/edit/one-ref/in4032x3024` | The weights are missing at the local model path named in the error. | Install them from [Optional Image: FLUX.2](../how-to/set-up-models.md#optional-image-flux2), then rerun `cases.batch1.json`. |
| krea2 | 8 cases: `krea2/generate/text/512`, `krea2/generate/text/768`, `krea2/generate/text/1024`, `krea2/generate/one-ref/in512x512`, `krea2/generate/one-ref/in1024x1024`, `krea2/generate/one-ref/in2048x2048`, `krea2/generate/one-ref/in1600x900`, `krea2/generate/one-ref/in4032x3024` | The int8 weights are incomplete. | Install them from [Image: Krea 2 Turbo](../how-to/set-up-models.md#image-krea-2-turbo), then rerun `cases.batch1.json`. |
| viggle_turbo | 4 cases: `viggle_turbo/generate/text/512`, `viggle_turbo/generate/text/1024`, `viggle_turbo/edit/one-ref/match`, `viggle_turbo/edit/one-ref/out1024` | The LoRA file is missing. | Install it from [Optional Image: Qwen and Viggle Turbo](../how-to/set-up-models.md#optional-image-qwen-and-viggle-turbo), then rerun `cases.batch1.json`. |

Three groups stopped on the payload, not on a model gap.
`flux2/edit/1-refs/out1024` and `flux2/edit/4-refs/out1024` used a `size` value the API rejects.
`flux3/edit/1-refs/out1024` and `flux3/edit/2-refs/out1024` did the same.
`ltx23_mlx/generate/text/768x768x97` and `ltx23_mlx/generate/one-keyframe/768x768x97` omitted `frame_rate`.
Each case needs a corrected payload and a rerun.

## DGX Spark

Measured on 2026-11-13 and 2026-11-14 on an NVIDIA DGX Spark, through the studio API.
Every backend runs in a PEP 723 child on Python 3.12, one operation at a time, with `HF_HUB_DISABLE_XET=1` because Xet delivery stalls on this network.

| Item | Value |
|---|---|
| Machine | NVIDIA DGX Spark: GB10, 121.7 GiB unified memory, CUDA 13.0, driver 580.178.04, Ubuntu 24.04 aarch64 |
| Date | 2026-11-13 and 2026-11-14 |
| Path | The studio API on port 8899, one operation at a time |
| Seed | 7 unless the case name names one |
| Sample | `MemAvailable` from `/proc/meminfo`, once a second |
| Baseline | The three samples before the submit |
| Time | Submit to terminal status. The time excludes queue wait and weight download. |

### Models

| Model | Backend | Source | Quantization | Checkpoint (GiB) |
|---|---|---|---|---|
| Qwen-Image-2.1 Turbo | `qwen21_turbo_cuda` | `Qwen/Qwen-Image-2.1-Turbo` | bf16 on disk, NVFP4 W4A4 at load | 32 |
| MiniMax H3-Image | `minimax_h3_image_cuda` | `MiniMaxAI/MiniMax-H3-Image` | bf16 on disk, text encoder FP8, transformer fp8 weight-only | 127 |
| LTX-2.5 | `ltx25_cuda` | `Lightricks/LTX-2.5-Diffusers` | bf16 | 107 |
| Drama-3 | `drama3_cuda` | `fishaudio/drama-3` | FP8 | 39 |
| YuE2 | `yue2_cuda` | `m-a-p/YuE2-3B` with `m-a-p/YuE2-Vae` | BF16 | 7.3 |

`Checkpoint` counts the files the backend reads, measured with `du` on this machine.
Two repositories ship more than that. H3-Image carries a second copy of its transformer, so the download is 190 GiB.
LTX-2.5 carries a second transformer, a distilled LoRA and the 9.6 GiB prompt enhancer, so the download is 163 GiB.

### How to read the numbers

**Free-memory drop (GiB)** is the fall from the baseline to the lowest `MemAvailable` sample, as a share of 121.7 GiB.
A warm row counts only the run, because the weights were resident before submit. A cold row includes the model load.
**Process footprint (GiB)** is the peak sum of the resident memory of the child process tree.
On unified memory a resident figure under-reports the GPU allocation, so read it beside the free-memory drop. `not sampled` means no sample exists.
**Time (s)** is the operation's wall time. The queue wait is excluded.
Each case has one row and `Runs` gives the recorded runs, and the row shows the last run, so a case with two runs shows the warm one.
A cold run also pays a submit wait before the child starts, and that wait is inside its time.
These numbers apply to this machine. Another host has no calibrated estimate.

### Image

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `qwen21_turbo_cuda/generate/text/512` | generate, 512x512, 8 steps, NVFP4 W4A4 | not sampled | not sampled | 4.0 | Succeeded | 2 |
| `qwen21_turbo_cuda/generate/text/768` | generate, 768x768, 8 steps, NVFP4 W4A4 | 2.90 | not sampled | 5.6 | Succeeded | 1 |
| `qwen21_turbo_cuda/generate/text/1024` | generate, 1024x1024, 8 steps, NVFP4 W4A4 | 2.27 | not sampled | 10.1 | Succeeded | 1 |
| `qwen21_turbo_cuda/generate/text/1328` | generate, 1328x1328, 8 steps, NVFP4 W4A4 | 5.19 | not sampled | 17.6 | Succeeded | 1 |
| `minimax_h3_image_cuda/generate/text/1024` | generate, 1024x1024, 6 steps, NVFP4 W4A4 | 0.00 | 1.4 | 33.3 | Succeeded | 2 |
| `minimax_h3_image_cuda/generate/text/1024-fp8` | generate, 1024x1024, 6 steps, fp8 weights | 0.00 | 1.6 | 54.5 | Succeeded | 2 |

The Qwen cold run, the first of the two 512 runs, took 18.6 s and dropped free memory by 38.68 GiB.
The Turbo checkpoint ships its own eight-step schedule, so a 20-step request samples the same eight steps.
The fp8 row is the shipped default. It costs 64% more sampling time than NVFP4 and removes the grain: at one prompt and seed, speckle fell from 3.94 to 2.04 and the smoothest 32x32 patch went from 5.99 to 2.17 standard deviation.
The H3 cold runs were 710.6 s with NVFP4, dropping 88.73 GiB and peaking at 105.3 GiB, and 707.6 s with fp8, dropping 76.78 GiB and peaking at 108.0 GiB.

### Video

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `ltx25_cuda/generate/text/768x768x97` | generate, 768x768, 97 frames, distilled eight-step schedule | 0.32 | 4.3 | 74.4 | Succeeded | 2 |

The first run took 442.1 s, which includes a 368 s load, and dropped 92.59 GiB at a peak of 83.8 GiB resident.
The clip is a 1.4 MB MP4. `LTX2DFRPipeline` runs the checkpoint's distilled eight-value sigma list, which is what the MLX backend runs when it takes its distilled path; `LTX2Pipeline` would run a linear thirty-step schedule at 3.75 times the cost.

### Voice

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `drama3_cuda/generate/sentence50` | generate, 7 words, 3.3 s of 44.1 kHz mono | 0.19 | 4.0 | 5.0 | Succeeded | 2 |
| `drama3_cuda/generate/paragraph700` | generate, 83 words, 36.9 s of 44.1 kHz mono | 1.53 | 4.1 | 51.1 | Succeeded | 1 |
| `mandarin/voice/traditional` | generate, Traditional Chinese, 3.6 s of audio | 44.47 | 7.3 | 351.6 | Succeeded | 1 |
| `mandarin/voice/simplified` | generate, Simplified Chinese, 3.9 s of audio | 0.10 | 4.0 | 7.0 | Succeeded | 1 |
| `mandarin/voice/paragraph` | generate, Traditional Chinese, 19.6 s of audio | 1.75 | 4.1 | 27.1 | Succeeded | 1 |
| `mandarin/voice/generate-same-text` | generate, no reference, 4.5 s of audio | 0.38 | 4.0 | 7.0 | Succeeded | 1 |
| `mandarin/voice/clone-tw-reference` | clone, synthetic zh_TW reference, 3.5 s of audio | 46.89 | 5.8 | 339.6 | Succeeded | 1 |
| `mandarin/voice/clone-4s6` | clone, 4.6 s human reference, 3.3 s of audio | 45.86 | 7.7 | 287.6 | Succeeded | 1 |
| `mandarin/voice/clone-10s` | clone, 10 s human reference, 2.7 s of audio | 0.32 | 4.1 | 5.0 | Succeeded | 1 |

Warm Drama-3 runs at 0.66x realtime on the 7-word English case and 0.72x on the 83-word one, and at 0.56x on the Mandarin sentence.
The three clone rows are one target sentence with three references; each first run paid the load.
Unconditioned Chinese completes but mispronounces: transcribing the output, 帶傘 came back as 呆散 and 可能 as 河冷. The clone rows read the same sentence correctly. The MLX backend mispronounces the same way, so this is the model, not the engine.
A synthetic reference clones a synthetic voice. The human reference rows are the ones to judge accent by.

### Music

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `yue2_cuda/generate/short` | generate, style and one lyric line, 114.5 s of 48 kHz stereo | 7.44 | 9.6 | 174.4 | Succeeded | 2 |
| `yue2_cuda/generate/lyrics-4-lines` | generate, one repeated line, 159 characters, 42.6 s of audio | 18.35 | 9.5 | 181.4 | Succeeded | 1 |
| `yue2_cuda/generate/lyrics-8-lines` | generate, one repeated line, 311 characters, 61.3 s of audio | 7.68 | 9.6 | 112.2 | Succeeded | 1 |
| `yue2_cuda/generate/lyrics-12-lines` | generate, one repeated line, 463 characters, 84.9 s of audio | 7.95 | 9.5 | 145.3 | Succeeded | 1 |
| `yue2_cuda/generate/lyrics-16-lines` | generate, one repeated line, 615 characters, 118.7 s of audio | 8.04 | 9.6 | 179.4 | Succeeded | 1 |
| `yue2_cuda/generate/long` | generate, style and 20 repeated lyric lines, 760 characters | 8.07 | 10.1 | 454.1 | Failed: the semantic stage reached its token limit | 1 |
| `yue2_cuda/generate/instrumental` | generate, style and no lyrics, 127.6 s of audio | 0.00 | 9.6 | 259.6 | Succeeded | 1 |
| `mandarin/music/verse` | generate, Mandarin style and lyric, 40.0 s of audio | 0.00 | 9.6 | 176.4 | Succeeded | 1 |

The first short run took 221.5 s and includes the load.
Warm YuE2 runs at 0.66x realtime and never truncated.
The four `lyrics-N-lines` rows are the sweep behind the gateway's lyric limit: 615 characters finished and 760 did not, so the CUDA gateway refuses more than 600 characters before it starts, instead of failing after seven minutes.
The MLX pack finishes the 760 characters in 237.9 s, so the budget is this engine's limit, not the model's.
`mandarin/music/verse` is the same backend with Traditional Chinese lyrics.
Chinese is slower per second of audio here: 40.0 s of audio in 176.4 s, against 114.5 s in 174.4 s for English.

### Kernels

Kernel measurements on this machine, one 4096-square linear layer:

| Measure | bf16 | NVFP4 weight-only | NVFP4 W4A4 |
|---|---|---|---|
| 512 tokens | 0.23 ms | 0.44 ms | 0.08 ms |
| 4096 tokens | 1.55 ms | 1.73 ms | 1.12 ms |
| 8192-square weights | 128 MiB | 128 MiB | 36 MiB |

A 4096-square bf16 GEMM ran at 83 to 90 TFLOPS at 2048, 4096 and 8192.
At these image sizes NVFP4 does not make the pipeline faster: attention, the text encoder and the VAE decode do not run in FP4.
It does cut the transformer's weights by 72%. Qwen-Image tolerates the 4-bit path; MiniMax H3-Image does not, which is why its default is fp8.

**The first load cost 236 s until the weights were materialized.** Moving safetensors' mmap-backed tensors straight to the device ran at 128 MB/s on this machine; the same tensors moved from ordinary memory at 14 GiB/s. A 16 GiB shard went from 135 s to 1.3 s, and a cold studio run from 242 s to 20 s.
H3-Image is the exception: materializing its 62 GiB transformer first died with `CUDA_ERROR_OUT_OF_MEMORY` at 110 GiB resident, because the host copy and the device copy come out of one pool, so it takes the slower mmap path.

### Against the M5 Pro

| Case | M5 Pro (s) | DGX Spark (s) | Ratio |
|---|---|---|---|
| Qwen Turbo generate, 512x512, 8 steps | 9.1 | 4.0 | 2.3x faster |
| Qwen Turbo generate, 768x768, 8 steps | 17.2 | 5.6 | 3.1x faster |
| Qwen Turbo generate, 1024x1024, 8 steps | 32.3 | 10.1 | 3.2x faster |
| Qwen Turbo generate, 1328x1328, 8 steps | 69.6 | 17.6 | 4.0x faster |
| LTX-2.5 generate, 768x768, 97 frames | 117.9 | 74.4 | 1.6x faster |
| Drama-3 generate, 7 words | 25.2 | 5.0 | 5.0x faster |
| YuE2 generate, instrumental | 283.2 | 259.6 | 1.1x faster |
| Drama-3 clone, one reference | 4.4 | 7.0 | 1.6x slower |
| YuE2 generate, short | 160.2 | 174.4 | 1.1x slower |
| YuE2 generate, Mandarin lyric | 57.4 | 176.4 | 3.1x slower |
| Drama-3 generate, 83 words | 29.2 | 51.1 | 1.8x slower |
| MiniMax H3-Image generate, 1024x1024, 6 steps, NVFP4 | 23.2 | 33.3 | 1.4x slower |
| MiniMax H3-Image generate, 1024x1024, 6 steps, fp8 | 23.2 | 54.5 | 2.3x slower |

Every row is the same case on both machines and the warm run on each, so the ratio means something.
YuE2's long case is absent because the Spark reaches its token limit; the Mac finishes it in 237.9 s.
A rerun of the short case on the Mac on 2026-11-14 took 179.8 s, against the 160.2 s above and 174.4 s on the Spark, so treat those two as level and the 1.1x as run-to-run noise.
Mandarin is the exception: the Spark sings 40 s of Chinese audio in 176.4 s where the Mac takes 57.4 s, while the two are level on English lyrics.
The clone row used the same reference and text on both, measured on 2026-11-14 outside the two campaigns.
Two machines differ by more than speed: the Spark wins by 3 to 4x on image generation, and loses on long-form speech, cloning and music, where the M5 Pro is faster per audio second.
