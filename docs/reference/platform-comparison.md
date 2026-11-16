# Platform comparison: Apple M5 Pro and DGX Spark

**Historical measurements, 2026-11-12 to 2026-11-15.** This page preserves that campaign's builds, labels, and numbers.
It does not establish current hardware rankings or current feature support.
The [2026-11-16 measurements](measured-memory-and-time.md) contain current results, explicit model states, quality limits, and the coverage record.

| Item | Apple M5 Pro | DGX Spark |
|---|---|---|
| Machine | Apple M5 Pro, 64 GiB | NVIDIA GB10, 121.7 GiB unified, CUDA 13.0 |
| Engine | MLX | PyTorch, diffusers 0.43 |
| Measured | 2026-11-12 to 2026-11-14 | 2026-11-13 to 2026-11-15 |
| Path | the studio API, one operation at a time | the studio API on port 8899, one operation at a time |
| Seed | 7 for video, voice and music | 7 for every case |

A time runs from submit to terminal status. It excludes queue wait and weight download.
The historical warm label does not prove resident model reuse. Per-call engines can reuse filesystem data while still loading their models.
FLUX.3, H3-Image MLX, and LTX MLX use per-call processes. Base Qwen can rebuild its generator for a new uncached prompt.

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

## The same run on both machines

One manifest, run on both engines on 2026-11-15: the same prompts, the same seed, and the same
reference bytes. The references are one picture made by Qwen bf16 on the Spark, its resizes,
two Drama speeches with their scripts written down, and slices of one recording. The method and
the case list are in [`scripts/measure`](../../scripts/measure/README.md).

The historical `load` label uses a free-memory-drop heuristic of at least ten gigabytes. That heuristic does not prove a model lifecycle.
All other historical labels remain unchanged, but they do not prove warm resident inference.
The current measurements use explicit process, configuration, and lifecycle evidence.

## Image

| Case | M5 Pro (s) | DGX Spark (s) | Ratio |
|---|---|---|---|
| Qwen Turbo generate, 512x512 | 7.1 | 3.0 | 2.4x |
| Qwen Turbo generate, 768x768 | 12.2 | 7.0 | 1.7x |
| Qwen Turbo generate, 1024x1024 | 24.2 | 12.0 | 2.0x |
| Qwen Turbo generate, 1328x1328 | 45.5 | 24.1 | 1.9x |
| Qwen Turbo edit, 512 out, 1 ref | 13.2 | 5.6 | 2.4x |
| Qwen Turbo edit, 768 out, 1 ref | 18.2 | 9.1 | 2.0x |
| Qwen Turbo edit, 1024 out, 1 ref | 36.3 | 15.1 | 2.4x |
| Qwen Turbo edit, 1344 out, 1 ref | 84.6 | 27.2 | 3.1x |
| Qwen Turbo edit, 1024 out, 2 refs | 48.4 | 18.2 | 2.7x |
| Qwen Turbo edit, 1024 out, 4 refs | 79.7 | 25.4 | 3.1x |
| Qwen Turbo edit, 1024 out, 8 refs | 382.0 | 41.7 | 9.2x |
| Qwen Turbo edit, 1024 out, 10 refs | 515.0 | 49.8 | 10.3x |
| Qwen Turbo edit, 1024 out, input 512x512 | 37.3 | 15.2 | 2.5x |
| Qwen Turbo edit, 1024 out, input 1600x900 | 40.4 | 15.4 | 2.6x |
| Qwen Turbo edit, 1024 out, input 2048x2048 | 43.5 | 16.8 | 2.6x |
| Qwen Turbo edit, 1024 out, input 4032x3024 | 53.0 | 19.2 | 2.8x |
| H3-Image generate, 1024x1024 | 18.2 | 56.2 | 0.3x |
| H3-Image generate, 2048x2048 | 57.4 | 56.6 | 1.0x |
| H3-Image edit, 1 ref at 4 MP | 184.5 | 92.5 | 2.0x |

Qwen is 1.7 to 3.1 times faster on the Spark across every single-reference case, and the
reference count is where the two engines separate. Each extra reference costs the Mac about
100 s once past four: 8 references take 382.0 s and 10 take 515.0 s, while the Spark takes 41.7
and 49.8. The MLX backend encodes every reference in a stage of its own; the CUDA child does it
in the process that already holds the model.

H3-Image is the one model where the Mac wins at a small size, and the reason is the canvas: the
CUDA engine raises every request below 4,194,304 pixels to that canvas, so a 1024 request does a
2048 request's work. At 2048 the two are level, 57.4 against 56.6. The edit is 2 times faster on
the Spark.

## Video

| Case | M5 Pro (s) | DGX Spark (s) | Ratio |
|---|---|---|---|
| LTX 768x768x97 | 156.1 | 77.4 | 2.0x |
| LTX 1280x704x97 | 252.8 | 119.5 | 2.1x |
| LTX 1920x1088x97 | 758.2 | 369.9 load | 2.0x |
| LTX 384x384x25 | 34.3 | 17.2 | 2.0x |
| LTX 768x768x25 | 58.4 | 29.1 | 2.0x |
| LTX 768x768x49 | 88.6 | 48.2 | 1.8x |
| LTX 768x768x121 | 197.3 | 118.2 | 1.7x |
| LTX 768x768x121, Fast mode | 145.2 | 119.1 | 1.2x |
| LTX 768x768x97, 1 keyframe | 158.1 | 149.2 load | 1.1x |
| LTX 768x768x97, 2 keyframes | 167.3 | 72.7 | 2.3x |
| LTX 768x768x97, 4 keyframes | 193.6 | 72.6 | 2.7x |
| LTX 768x768x97, 8 keyframes | 243.9 | 73.1 | 3.3x |
| LTX 768x768x97, no prompt pass | 163.2 | 83.4 | 2.0x |

The Spark holds 1.7 to 2.1 times across every shape and length. Two rows break the pattern.

Keyframes are nearly free on the Spark and almost linear on the Mac. A keyframe costs the
Spark nothing after the first, 72.7, 72.6 and 73.1 s for two, four and eight, where the Mac goes
167.3, 193.6 and 243.9, about 25 s each.

During this campaign, Fast mode saved the Mac a quarter of a 121-frame clip.
It saved the Spark nothing: 119.1 s against 118.2 s without it.
The current CUDA backend hides Fast mode and refuses requests that enable it.
The recorded times describe the earlier implementation.

## Voice

| Case | M5 Pro (s) | DGX Spark (s) | Ratio |
|---|---|---|---|
| Drama generate, 28 characters | 2.0 | 5.1 | 0.4x |
| Drama generate, 451 characters | 23.2 | 46.1 | 0.5x |
| Drama generate, 10 words, seed 11 | 3.0 | 7.1 | 0.4x |
| Drama generate, 200 words | 51.3 | 172.5 | 0.3x |
| Drama generate, 800 words | failed at the token cap | 477.4 | |
| Drama clone, 5.9 s reference | 5.1 | 8.2 | 0.6x |
| Drama clone, 11.7 s reference | 5.1 | 7.1 | 0.7x |

Drama is the Mac's model: two to three times faster on every case it finishes. The decode is a
chain of one forward pass per codec frame at about 19 frames per second, so a GPU has nothing to
overlap, and the engine refuses `compile=True`, which leaves no graph capture to cut the
per-token launch. The Spark finishes the 800-word script the Mac's token cap refuses, in 477.4 s.

The clone is much closer than the older rows suggested, 5.1 against 7.1 s, once both are warm.
The earlier 9.1 s row carried a load.

## Music

| Case | M5 Pro (s) | DGX Spark (s) | Ratio |
|---|---|---|---|
| YuE2 generate, short lyric | 145.0 | 115.3 | 1.3x |
| YuE2 generate, long lyric | 171.2 | 187.6 | 0.9x |
| YuE2 generate, instrumental | 169.2 | 193.6 | 0.9x |
| YuE2 plan | 15.1 | 16.0 | 0.9x |
| YuE2 transcribe, 10 s reference | 7.1 | 42.2 | 0.2x |
| YuE2 transcribe, 15 s reference | 5.1 | 24.1 | 0.2x |
| YuE2 cover, 10 s reference | 77.6 | 277.7 | 0.3x |

Music is close on the song itself: the Spark wins the short lyric and the Mac wins the long one
and the instrumental by about 10%. Transcribe and cover are the Mac's by a wide margin, because
the CUDA child runs the pinned SheetSage2 script as its own process with its own model, and that
model is what costs the time.

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

During the campaign, `ltx25_cuda` inherited unsupported MLX controls.
The current backend advertises Generate only. It refuses Edit, source audio, Fast mode, and LoRAs.
It forwards the generated-audio flag and retains the pipeline's soundtrack in the MP4.
CPU checks confirm encoding with and without audio. Full CUDA inference needs another measurement.

## What is not built

These are the gaps between the two machines, in the order they cost a user. Each one is
read from the code that runs, not from the record the form draws.

1. LTX Edit remains unsupported on CUDA. The form hides it, and direct requests fail.
2. LTX source audio remains unsupported on CUDA. Generated sound is optional and retained in the MP4.
3. LTX Fast mode remains unsupported on CUDA. The form hides it, and direct requests fail.
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

The manifest covers every case both engines can express. What it leaves out, and why:

| Case | Why it is missing |
|---|---|
| Qwen Turbo edit with a mask, and Qwen edit of each reference separately | Both are MLX-only features; the CUDA backend has neither, so there is no second column |
| LTX generated audio after the encoding fix | CPU encoding passes; CUDA inference has not been measured again |
| LTX source audio, Edit and Fast mode | Unsupported on CUDA |
| Qwen Turbo and H3-Image at other builds | The NVFP4 entries are measured in [Measured memory and time](measured-memory-and-time.md#the-nvfp4-builds-2026-11-15); the manifest runs the shipped default |
| Drama at 800 words on the Mac | The engine's token cap refuses it, so there is no time to compare. The Spark finishes in 477.4 s |
| flux2, krea2, viggle_turbo, Qwen-Image-2.1, MiniMax H3, LTX-2.3, Auk | No CUDA backend, and some Mac weights are not installed |

Two rows in the tables above carry a load, marked `load`. Their warm figures exist for the
same case elsewhere on this page only where the older campaigns measured it; the harness can
repeat any row twice to separate the load from the run.

## How to repeat it

The harness is in [`scripts/measure`](../../scripts/measure/README.md). It holds the case list,
generates the references both engines must share, runs one studio per machine, and prints both
columns with every case that is missing.

```sh
uv run python scripts/measure/build_assets.py --base http://127.0.0.1:8899 \
    --image-backend qwen21_turbo_cuda --voice-backend drama3_cuda --work /tmp/parity
uv run python scripts/measure/parity_matrix.py --work /tmp/parity
uv run python scripts/measure/run_matrix.py --machine cuda --base http://127.0.0.1:8899 --work /tmp/parity
uv run python scripts/measure/report.py --work /tmp/parity
```

A case that fails is retried by the next run of the same command, because only a success is
skipped. `report.py` names what is left, which is the check that a campaign otherwise lacks.
