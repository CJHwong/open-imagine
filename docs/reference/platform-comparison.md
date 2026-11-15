# Platform comparison: Apple M5 Pro and DGX Spark

One studio, two machines. The Mac runs the MLX backends and the Spark runs the CUDA ones.
This page puts the same case on both, names the build each one ran, and says where a figure
is missing or a feature is not built. The memory samples, the harness and the full case
list are in [Measured memory and time](measured-memory-and-time.md).

| Item | Apple M5 Pro | DGX Spark |
|---|---|---|
| Machine | Apple M5 Pro, 64 GiB | NVIDIA GB10, 121.7 GiB unified, CUDA 13.0 |
| Engine | MLX | PyTorch, diffusers 0.43 |
| Measured | 2026-11-12 to 2026-11-14 | 2026-11-13 to 2026-11-15 |
| Path | the studio API, one operation at a time | the studio API on port 8899, one operation at a time |
| Seed | 7 for video, voice and music | 7 for every case |

A time is submit to terminal status. It excludes the queue wait and the weight download. A
warm row excludes the model load, because the child holds the model between runs.

## The builds

| Model | Mac backend and build | Spark backend and build |
|---|---|---|
| Qwen-Image-2.1 Turbo | `qwen21_turbo`, bf16 | `qwen21_turbo_cuda`, bf16 |
| Qwen-Image-2.1 | `qwen21`, bf16 | none |
| MiniMax H3-Image | `minimax_h3_image`, int8 | `minimax_h3_image_cuda`, fp8 weight-only; `minimax_h3_image_cuda_nvfp4`, NVFP4 |
| LTX-2.5 | `ltx25_mlx`, q8 | `ltx25_cuda`, bf16 |
| LTX-2.3 | `ltx23_mlx`, q8 | none |
| MiniMax H3 | `minimax_h3`, q8 | none |
| Drama-3 | `drama3`, 8-bit | `drama3_cuda`, FP8 W8A8 |
| YuE2 | `yue2`, Q8 lyrics stages and BF16 decoder | `yue2_cuda`, bf16; `yue2_cuda_nvfp4`, NVFP4 lyrics stages; both keep the BF16 decoder |
| Auk | `auk`, `auk_base` | none |
| FLUX.2 klein, FLUX.3 klein, Krea 2, Viggle Turbo | MLX backends | none |

Two models have two measured builds and two entries in the picker, one per build:
`minimax_h3_image_cuda` and `minimax_h3_image_cuda_nvfp4`, `yue2_cuda` and
`yue2_cuda_nvfp4`. The shipped default is named in `studio.cuda.toml` and is the build whose
quality the model was chosen for.

Qwen-Image-2.1 Turbo had a third entry for a day. Its NVFP4 pack was measured on 2026-11-15
and dropped: 11.0 s at 1024 against 12.0, and 18.1 at 1328 against 19.1, for visible grain
and 4.7 GiB of memory. The rows stay in
[Measured memory and time](measured-memory-and-time.md#the-nvfp4-builds-2026-11-15) as the
record of the decision. The measurement that picks between the H3 builds is in the same page,
under [the precision sweep on H3-Image](measured-memory-and-time.md#the-precision-sweep-on-h3-image).

## Image

Warm runs, one operation at a time. The Mac figures are the case rows in the reference
page, and the Spark figures are the campaign of 2026-11-15.

| Case | Mac (s) | Spark (s) | Spark build |
|---|---|---|---|
| Qwen Turbo generate, 512x512 | 9.1 | 3.0 | bf16 |
| Qwen Turbo generate, 768x768 | 17.2 | 7.0 | bf16 |
| Qwen Turbo generate, 1024x1024 | 32.3 | 12.0 | bf16 |
| Qwen Turbo generate, 1328x1328 | 69.6 | 19.1 | bf16 |
| Qwen Turbo edit, 512 out, 1 ref | 15.1 | 4.1 | bf16 |
| Qwen Turbo edit, 768 out, 1 ref | 28.2 | not measured | bf16 |
| Qwen Turbo edit, 1024 out, 1 ref | 49.5 | not measured | bf16 |
| Qwen Turbo edit, 1344 out, 1 ref | failed, engine out of memory | 28.2 | bf16 |
| Qwen Turbo edit, 512 out, 2 refs | not measured | 4.2 | bf16 |
| Qwen Turbo edit, 512 out, 4 refs | not measured | 6.4 | bf16 |
| H3-Image generate, 1024x1024 | 23.2 | 57.4 | fp8 |
| H3-Image generate, 1024x1024 | 23.2 | 34.3 | NVFP4 |
| H3-Image generate, 2048x2048 | 51.4 | 57.3 | fp8 |
| H3-Image edit, 1 ref at 4 MP | 153.2 | 70.5 | fp8 |
| H3-Image edit, 1 ref at 4 MP | 153.2 | 63.7 | NVFP4 |

The H3-Image pack earns its place: 40% off a generate and 10% off an edit. Its first run on
a machine without the pack costs 527.8 s and a 104.21 GiB free-memory drop, because the child
writes the pack and then loads it; after that a run is 34.3 s. The fp8 default stays, because
the pack leaves grain that fp8 does not.

The edit runs the same checkpoint on both machines, so there is no second model to download
or load on either.

Three figures need a reason.

1. The Mac ran an edit at 1344 out of memory, and the Spark completed the same shape in
   28.2 s. This page does not say why the Mac run failed; the row is what the campaign
   recorded, and the Spark row was measured the next day.
2. H3-Image is faster on the Mac below 2048 and faster on the Spark at 2048 and on an edit.
   The CUDA engine raises every request below 4,194,304 pixels to that canvas, so a
   1024x1024 request costs a 2048x2048 run. The Mac engine works at the size it is asked
   for. That is why 1024 is 2.5 times slower on the Spark and 2048 is a tie. Per megapixel
   the Spark is ahead: 8.2 s on NVFP4 and 13.7 on fp8, against the Mac's 12.3. On a native
   1024 canvas the same engine took 20.6 s in the sweep, against the Mac's 23.2.
3. The Spark runs an edit of the same 4 MP canvas in 70.5 s against the Mac's 153.2 s, 2.2
   times faster. The edit is the case where the CUDA engine leads most.

## Video

LTX-2.5 at 97 frames and 24 fps, the distilled eight-step schedule, warm.

| Case | Mac (s) | Spark (s) | Spark build |
|---|---|---|---|
| 768x768x97 | 117.9 | 76.3 | bf16 |
| 1280x704x97 | 269.2 | 121.5 | bf16 |
| 768x448x97 | not measured | 48.3 | bf16 |
| 768x512x97, one keyframe at frame 0 | not measured | 55.3 | bf16 |
| 768x768x97, Fast mode | 149.1 at 121 frames, against 200.6 | 77.3, against 76.3 | bf16 |

Fast mode is a no-op on the Spark. The Mac saves 26% of a 121-frame clip, and the Spark
saves nothing, because `clip_payload` does not send the flag to the child. The backend
declares `fast_mode` true and the form offers the control. That is a fault, named under
"What is not built" below.

The Mac has cases this table cannot hold, such as a keyframe count sweep and an audio track.
The Spark has no matching row for any of them, because those inputs are not wired there.

## Voice

| Case | Mac (s) | Spark (s) | Spark build |
|---|---|---|---|
| Drama generate, 28 characters | 25.2 | 5.0 | FP8 |
| Drama generate, 66 characters | 30.2 at 10 words | 9.0 | FP8 |
| Drama generate, 451 characters | 29.2 | 48.1 | FP8 |
| Drama clone, 7 s reference | 4.1 at 5 s, 5.1 at 15 s | 9.1 | FP8 |
| Drama generate, Mandarin paragraph | failed, the audio reached max_tokens | 27.1 | FP8 |

The Mac's times sit between 25 and 30 s whatever the script length, and the Spark's follow
the script: 5.0 s for one line and 48.1 s for a paragraph of 451 characters. The Mac's
child pays a fixed cost per run that the Spark's resident child does not.

The Mandarin paragraph is the larger difference. The MLX engine stops at its token cap and
produces no audio. The CUDA engine finishes the same paragraph in 27.1 s.

Per second of audio, which is the comparison the script lengths hide, the Spark takes 1.39 to
1.46 s and the Mac about 0.98 s on its one warm row (4.3 s of wall time for 4.4 s of audio,
Mandarin simplified). The engine writes one codec frame per forward pass at about 19 frames
per second, so the run is a serial chain, and the GPU has nothing to overlap. It refuses
`compile=True`, so there is no graph capture to cut the per-token launch, and bf16 against
fp16 decodes at 18.91 against 18.81 frames per second, so the datatype is not a lever either.
That 40% is the engine's shape, not a setting.

## Music

A music case carries each side's first load on the Mac, because that backend loads per
run, and none on the Spark, because its child stays resident. The campaign chose the four
lyric lengths on the Spark. The Mac's short, long and Mandarin cases used the text in its
own case file, so a row compares a case, not a string.

Every Spark row below ran the NVFP4 build. The picker offers the bf16 build as a second
entry, `yue2_cuda`, and its times are in the table after this one.

| Case | Mac (s) | Spark (s) | Spark build |
|---|---|---|---|
| YuE2 generate, short lyric | 160.2 | 67.2 | NVFP4 |
| YuE2 generate, Mandarin lyric | 57.4 | 31.1 | NVFP4 |
| YuE2 generate, 272 lyric characters | not measured | 89.2 | NVFP4 |
| YuE2 generate, 413 lyric characters | not measured | 98.2 | NVFP4 |
| YuE2 generate, long lyric | 237.9 | 164.5 | NVFP4 |
| YuE2 generate, instrumental | 283.2 | 126.8 | NVFP4 |
| YuE2 plan | 10.1 | 9.0 | NVFP4 |
| YuE2 transcribe, 20 s reference | 5.1 at 15 s | 25.7 | NVFP4 |
| YuE2 cover, 20 s reference | 18.2 at 10 s speech | 45.5 | NVFP4 |

The two machines disagree about which stage costs the time. YuE2 on the Mac pays per song
and lands between 160 and 283 s whatever the lyric length. On the Spark a 31-character
lyric finishes in 67.2 s and a 483-character one in 164.5 s, so the gap over the Mac
narrows as the song grows. Transcribe and cover go the other way: 25.7 s against 5.1 s,
and 45.5 s against 18.2 s.

A time on this engine does not follow the lyric length closely. The 33-character line sang
209 s of audio in 67.2 s and the 60-character Mandarin line sang 69 s in 31.1 s, so the
figure the studio shows is a rough guide rather than a schedule.

The bf16 entry, which is the default, ran the same sweep. Warm runs on both builds, so this
table compares the build and not a first load:

| Case | bf16 (s) | NVFP4 (s) |
|---|---|---|
| generate, 33-character lyric | 117.2 | 67.2 |
| generate, 272 characters | 137.3 | 89.2 |
| generate, 413 characters | 318.8 | 98.2 |
| generate, long lyric | 202.6 at 535 characters | 164.5 at 483 characters |
| generate, instrumental | 250.8 | 126.8 |
| plan | 17.0 | 9.0 |
| cover, 20 s reference | 126.3 | 45.5 |
| transcribe, 20 s reference | 21.1 | 25.7 |

bf16 costs about 1.7 times the pack on a short song and 3.2 times at 413 characters, and it
is 2 to 2.8 times the pack on plan and cover. Per second of audio it takes 0.67 to 0.86 s
against the pack's 0.32 to 0.48.

The bf16 column scatters more than the pack's. The 413-character run sang 444 s of audio in
318.8 s, and the 535-character run sang 272 s in 202.6 s, so the engine writes songs of
different lengths from similar scripts. A line through the four bf16 runs reads 108.8 s plus
0.272 s per character, and its worst error is 98 s.

Transcribe runs the pinned SheetSage2 script on its own model, and the two builds measured
21.1 s and 25.7 s on the same reference. The script is the same; the difference is inside the
noise of a 20 s run.

## The estimate each backend declares

The page draws a time under the run button from these constants. `step_cost` is seconds per
step at one megapixel, `exponent` is how that grows with the pixel count, and `overhead` is
the fixed cost of a run. The video and music records have their own shapes, named in the
table.

| Backend | Constants | Measured against |
|---|---|---|
| `qwen21_turbo_cuda` generate | 1.466 s per step, 0.91, 0 s fixed | 3.3, 6.9, 11.7, 19.2 s against 3.0, 7.0, 12.0, 19.1 s |
| `qwen21_turbo_cuda` edit | 1.944 s per step, 1.0, 0.21 s fixed, 0.171 per extra reference | 4.1 s at 512 out and 28.3 s at 1344 out, against 4.1 and 28.2 s; 6.2 s at four references, against 6.4 s |
| `minimax_h3_image_cuda` generate | 0 s per step, 57.3 s fixed | one canvas for every size this form offers |
| `minimax_h3_image_cuda` edit | 0 s per step, 70.5 s fixed | one reference at 4 MP |
| `minimax_h3_image_cuda_nvfp4` generate | 0 s per step, 34.3 s fixed | the same canvas on the pack |
| `minimax_h3_image_cuda_nvfp4` edit | 0 s per step, 63.7 s fixed | one reference at 4 MP on the pack |
| `ltx25_cuda` generate | 0.530 of the shared fit, 14.2 s fixed | 50, 80, 120 s against 48.3, 76.3, 121.5 s |
| `drama3_cuda` generate | 1.383 per second of audio, 0.28 s fixed, 0.077 s of audio per character | 5.2, 8.8, 48.1 s against 5.0, 9.0, 48.1 s |
| `drama3_cuda` clone | 1.383 per second of audio, 1.64 s fixed, 0.104 s of audio per character | 9.1 s |
| `yue2_cuda_nvfp4` | 52.4 s plus 0.175 s per lyric character, 73.2 s for an instrumental, and one figure per stage | 58.2, 100.0, 124.6, 136.9 s against 67.2, 89.2, 98.2, 164.5 s |
| `yue2_cuda` | 108.8 s plus 0.272 s per lyric character, 140.1 s for an instrumental, and one figure per stage | 117.8, 182.7, 221.1, 254.2 s against 117.2, 137.3, 318.8, 202.6 s |

Every CUDA row above is new. The image, voice and music backends declared no estimate at
all before this pass, and `ltx25_cuda` inherited the MLX record, which reads 270 s for the
768x768 clip that this machine runs in 76.3 s.

## What each mode offers

The CUDA records are read from a running studio's `/api/v1/studio` and its
`/api/v1/images/backends/<id>` routes on 2026-11-15. A cell is the control the form draws.

| Backend | Mode | References | Region marking | Looks | Templates | Batch | Estimate |
|---|---|---|---|---|---|---|---|
| `qwen21_turbo` | generate | 0 to 1, with strength | no | 8 | 7 | 4 | yes |
| `qwen21_turbo_cuda` | generate | 0 | no | 8 | 7 | 4 | yes |
| `qwen21_turbo` | edit | 1 to 10 | yes | 6 | 8 | 4 | yes |
| `qwen21_turbo_cuda` | edit | 1 to 10 | no | 0 | 0 | 4 | yes |
| `minimax_h3_image` | generate | 0 | no | 8 | 7 | 4 | yes |
| `minimax_h3_image_cuda` | generate | 0 | no | 0 | 0 | 1 | yes |
| `minimax_h3_image_cuda_nvfp4` | generate | 0 | no | 0 | 0 | 1 | yes |
| `minimax_h3_image` | edit | 1 to 4 | no | 6 | 5 | 4 | yes |
| `minimax_h3_image_cuda` | edit | 1 to 4 | no | 0 | 0 | 1 | yes |
| `minimax_h3_image_cuda_nvfp4` | edit | 1 to 4 | no | 0 | 0 | 1 | yes |
| `yue2` | all four | n/a | n/a | n/a | n/a | 16 | yes |
| `yue2_cuda` | all four | n/a | n/a | n/a | n/a | 16 | yes, with a 600-character lyric limit |
| `yue2_cuda_nvfp4` | all four | n/a | n/a | n/a | n/a | 16 | yes, with a 600-character lyric limit |

The video records agree field for field, which is the problem: `ltx25_cuda` inherits the
MLX shape, the frame counts, `fast_mode`, `can_skip_audio` and nine Edit adapters, and its
gateway sends only the prompt, the size, the frames, the frame rate, the seed, the enhance
flag and the keyframes.

## What is not built

These are the gaps between the two machines, in the order they cost a user. Each one is
read from the code that runs, not from the record the form draws.

1. LTX Edit. The Spark form offers Edit with nine adapters. `clip_payload` sends no
   adapter and no clip, and the child has no branch for either, so the run renders a
   Generate from the prompt.
2. LTX audio. The form offers an audio track and `can_skip_audio`. The gateway sends no
   track and no audio flag.
3. LTX Fast mode. The form offers it. The gateway sends nothing, and the measured time
   agrees: 77.3 s with the flag against 76.3 s without it.
4. LTX LoRAs. The backend declares none, so the form offers none, and the MLX backend
   offers none either. No gap.
5. Qwen generate from a reference. The MLX backend takes one reference with a strength and
   offers Match on it. The CUDA backend takes none.
6. Qwen region marking. The MLX edit marks a region. The CUDA edit does not.
7. Looks and templates. The CUDA image backends offer none of the MLX verdicts, because
   AGENTS.md step 5 re-samples them on the engine under test.
8. H3-Image batch. The form allows 4 images on the Mac and 1 on the Spark.

The prompt rewriter and the YuE2 transcribe and cover modes are built on both machines, so
they are not on this list.

## What is not measured

| Case | Why it is missing |
|---|---|
| Qwen Turbo edit at 768 and 1024 out | The campaign used a 512 reference, so Match stayed at 512 |
| Qwen Turbo edit with 2 to 10 references at 1024 out | The Spark edit path was measured at 512 out only |
| Qwen Turbo at NVFP4 across every size | One pair of runs at 1024 |
| H3-Image at NVFP4 and int8 through the studio | The precision sweep ran a script, not the studio |
| LTX at 25, 49 and 121 frames | The campaign ran 97 frames |
| LTX audio, Edit and Fast mode | Not built, so nothing to measure |
| Drama at 200 words and above | The Mac stops at the engine's token cap on those, so there is no time to compare |
| flux2, krea2, viggle_turbo, Qwen-Image-2.1, MiniMax H3, LTX-2.3, Auk | No CUDA backend, and some Mac weights are not installed |

## How to repeat it

The case files and the driver live outside the repository, on the machine that runs them.
The driver reads `REPO`, `CONFIG`, `PORT` and `OUT` from the environment, starts one
studio, runs the cases in order, and writes one JSON line per run. A case that fails stops
the run, so the next invocation starts from the first unmeasured case.

```sh
env REPO=$HOME/Workspace/image-gen CONFIG=studio.spark.toml PORT=8899 \
    OUT=/tmp/spark-matrix python3 drive2.py matrix-rest.json
```
