# Measured memory and time

Measured peak memory and elapsed time for each case, on one Mac with an Apple M5 Pro and 64 gibibytes (GiB) of memory.
The measurements ran on 2026-11-12 and 2026-11-13 through the studio API.
The measured tables hold 70 cases: 67 succeeded and 3 stopped at an engine limit.

| Item | Value |
|---|---|
| Machine | Apple M5 Pro, 64 GiB |
| Date | 2026-11-12 and 2026-11-13 |
| Path | The studio API on a local port, one operation at a time |
| Seed | Video set 7. Voice and Music set 7 unless the case name names one. Image cases used the studio default. |
| Sample | Free memory from `memory_pressure -Q`, and `footprint` of the server process tree, once a second |
| Baseline | The three samples before the submit |
| Time | Submit to terminal status. The time excludes queue wait and weight download. |

## How to read the numbers

**Free-memory drop (GiB)** is the fall from the baseline to the lowest free-memory sample, as a share of 64 GiB.
**Process footprint (GiB)** is the peak sum of the memory footprint of every process in the server tree. It includes a model that an earlier case left warm.
**Time (s)** is the operation's wall time. The queue wait is excluded, because the runner waits for an idle server before it submits.
Each case has one row. `Runs` gives the recorded runs for that case name, and the row shows the last run.
A row with one run is one measurement, not an average. Machine load moves a time, so compare rows with that limit in mind.
These numbers apply to a 64 GiB Mac. Another host has no calibrated estimate.

## Image

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

## Video

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

## Voice

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `drama3/clone/ref15s` | drama3, clone, 7 words, ref 15s | 42.24 | 68.03 | 5.1 | Succeeded | 1 |
| `drama3/clone/ref5s` | drama3, clone, 7 words, ref 5s | 40.96 | 67.03 | 4.1 | Succeeded | 1 |
| `drama3/generate/paragraph700` | drama3, generate, 83 words | 41.60 | 67.03 | 29.2 | Succeeded | 1 |
| `drama3/generate/sentence50` | drama3, generate, 7 words | 41.60 | 67.03 | 25.2 | Succeeded | 1 |
| `drama3/generate/text1000` | drama3, generate, 200 words | 40.96 | 67.03 | 83.7 | Failed: the audio reached max_tokens | 2 |
| `drama3/generate/text4000` | drama3, generate, 800 words | 41.60 | 67.03 | 83.7 | Failed: the audio reached max_tokens | 2 |
| `drama3/generate/text50-seed11` | drama3, generate, 10 words, seed 11 | 43.52 | 40.06 | 30.2 | Succeeded | 1 |

## Music

| Case | Settings | Free-memory drop (GiB) | Process footprint (GiB) | Time (s) | Result | Runs |
|---|---|---|---|---|---|---|
| `yue2/cover/speech10s` | yue2, cover, style, lyrics, 10 s speech reference | 6.40 | 8.93 | 18.2 | Succeeded | 1 |
| `yue2/generate/instrumental` | yue2, generate, style, instrumental | 4.48 | 36.02 | 283.2 | Succeeded | 1 |
| `yue2/generate/long` | yue2, generate, style, lyrics | 3.84 | 36.02 | 237.9 | Succeeded | 1 |
| `yue2/generate/short` | yue2, generate, style, lyrics | 3.84 | 36.02 | 160.2 | Succeeded | 1 |
| `yue2/plan/short` | yue2, plan, style, lyrics | 3.20 | 35.40 | 10.1 | Succeeded | 1 |
| `yue2/transcribe/speech10s` | yue2, transcribe, 10 s speech reference | 1.92 | 4.23 | 7.1 | Succeeded | 1 |
| `yue2/transcribe/speech15s` | yue2, transcribe, 15 s speech reference | 1.92 | 4.24 | 5.1 | Succeeded | 1 |

## Not tested

The table lists the models that produced no measurement because a weight or runtime was missing.
Complete the setup, then rerun the named case file.

| Model | Cases | What is missing | To complete |
|---|---|---|---|
| flux2 | 7 cases: `flux2/generate/text/512`, `flux2/generate/text/768`, `flux2/generate/text/1024`, `flux2/generate/match/in1600x900`, `flux2/edit/one-ref/in512x512`, `flux2/edit/one-ref/in2048x2048`, `flux2/edit/one-ref/in4032x3024` | The weights are missing at the local model path named in the error. | Install them from [Optional Image: FLUX.2](../how-to/set-up-models.md#optional-image-flux2), then rerun `cases.batch1.json`. |
| krea2 | 8 cases: `krea2/generate/text/512`, `krea2/generate/text/768`, `krea2/generate/text/1024`, `krea2/generate/one-ref/in512x512`, `krea2/generate/one-ref/in1024x1024`, `krea2/generate/one-ref/in2048x2048`, `krea2/generate/one-ref/in1600x900`, `krea2/generate/one-ref/in4032x3024` | The int8 weights are incomplete. | Install them from [Image: Krea 2 Turbo](../how-to/set-up-models.md#image-krea-2-turbo), then rerun `cases.batch1.json`. |
| viggle_turbo | 4 cases: `viggle_turbo/generate/text/512`, `viggle_turbo/generate/text/1024`, `viggle_turbo/edit/one-ref/match`, `viggle_turbo/edit/one-ref/out1024` | The LoRA file is missing. | Install it from [Optional Image: Qwen and Viggle Turbo](../how-to/set-up-models.md#optional-image-qwen-and-viggle-turbo), then rerun `cases.batch1.json`. |
| minimax_h3 | 3 cases: `minimax_h3/generate/text/512x288x73`, `minimax_h3/generate/text/1024x576x175`, `minimax_h3/generate/text/1280x704x175` | The pinned H3 engine and weights are missing. | Install them from [Optional Video: MiniMax H3](../how-to/set-up-models.md#optional-video-minimax-h3), and set `[minimax_h3]` `engine_dir` and `model_dir` in `studio.toml`. Then rerun `cases.batch2.json`. |

Three groups stopped on the payload, not on a model gap.
`flux2/edit/1-refs/out1024` and `flux2/edit/4-refs/out1024` used a `size` value the API rejects.
`flux3/edit/1-refs/out1024` and `flux3/edit/2-refs/out1024` did the same.
`ltx23_mlx/generate/text/768x768x97` and `ltx23_mlx/generate/one-keyframe/768x768x97` omitted `frame_rate`.
Each case needs a corrected payload and a rerun.
