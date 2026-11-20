# MiniMax H3 CUDA gateway

The child drives diffusers' modular `MiniMaxH3Blocks` at the pinned release
`1cc7549f2cf0af8ff2f09b24f3c57303c8aa6317`. The pipeline picks its workflow from the inputs:
text alone is `t2va`, a first or last frame is `fl2va`, and pictures with an audio track are
`ref2va`, which runs on its own transformer. The child holds the encoder and both transformers.

## What it takes

- Text, with a still on the first frame, the last frame, or both. A still on any other frame
  is refused: the pipeline takes keyframes only at the ends. The still that sets the canvas is
  cover-cropped to it, because the pipeline would stretch it.
- An audio track with one or two stills. The stills become pictures of what to show. The
  track steers the sound the model generates, as a voice or a sound to follow, but the
  pipeline places it before the clip on its own clock, so the picture is not timed to it and
  the clip carries the generated sound. The pipeline refuses a track with no picture.
- 124 to 345 frames at 24 fps, which is 5 to 14.4 s. The pipeline refuses under 5 s.
- 50 steps, the release's own count, or 20 in Fast mode.

Edit, LoRAs, the 2K regenerate and the release's prompt system (Context-IR) are not offered.

## Why it looks like this

All on the DGX Spark, 2026-11-20, seed 42 unless the row says otherwise. The precision and
load rows drove diffusers directly; the clip rows ran through the Studio operations API.

| What | FP8 | NVFP4 W4A4 |
|---|---:|---:|
| One step, text, 512 × 288, 124 frames | 7.7 s | 3.4 s |
| One step, text, 1024 × 576, 124 frames | 34.6 s | 17.9 s |
| Encoder and one transformer held | 62.7 GiB | 39.1 GiB |
| Encoder and both transformers held | 93.6 GiB | 56.3 GiB |

The NVFP4 frames showed no grain at either size, unlike H3-Image's NVFP4 build. The same seed
draws a different scene under each precision, so the comparison was by eye.

There is no pack of quantized weights. Each linear lands on the device one at a time and is
quantized as it lands, so a load from the bf16 files took 133 s and free memory never fell
under 48.7 GiB. A pack would save part of that load and nothing else.

A reference run costs about five times a text run of the same size: 17.5 to 19.2 s per step
at 512 × 288 against 3.4 s. Scaling the picture to a 768-pixel short side saved 9%, so the
cost is the reference rows, not memory pressure.

| Clip, through the studio, 512 × 288, 124 frames, Fast mode | Time |
|---|---:|
| Text, first clip of the child, load included | 226.7 s |
| Text, warm | 82.3 s |
| First and last frame, warm | 88.5 s |
| One picture and a 5 s track, warm | 360.6 s |
| Cancel during a 50-step run | stopped at step 19 within 2 s |

A studio idle with the model loaded had 62 GiB less free memory than before its first clip.
No time estimate is declared yet: the cost is measured at two sizes, not three.
