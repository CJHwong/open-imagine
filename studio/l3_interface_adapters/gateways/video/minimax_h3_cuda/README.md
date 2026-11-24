# MiniMax H3 CUDA gateway

The child drives diffusers' modular `MiniMaxH3Blocks` at the pinned release
`1cc7549f2cf0af8ff2f09b24f3c57303c8aa6317`. The pipeline picks its workflow from the inputs:
text alone is `t2va`, a first or last frame is `fl2va`, and pictures, with or without an audio
track, are `ref2va`, which runs on its own transformer. The child holds the encoder and both transformers.

## What it takes

- Text, with a still on the first frame, the last frame, or both. A still on any other frame
  is refused: the pipeline takes keyframes only at the ends. The still that sets the canvas is
  cover-cropped to it, because the pipeline would stretch it.
- Up to nine pictures of who or what to show, on no frame. The prompt names them as
  `<Picture 1>` on, in the order sent. The pipeline takes no keyframe beside them.
- An audio track with at least one picture, named `<Audio 1>`. The track steers the sound the
  model generates, as a voice or a sound to follow, but the pipeline places it before the clip
  on its own clock, so the picture is not timed to it and the clip carries the generated sound.
  The pipeline refuses a track with no picture. A track sent with keyframes and no pictures
  still runs, the older form of this run: each keyframe becomes a picture.
- No clip as a reference. `ref2va` takes three, and the studio does not offer them: on
  2026-11-24 one clip took 22 times a text run at 512 × 288 and copied its own scene over the
  picture beside it, and three clips ran the Spark out of memory even at 288p.
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
| Two pictures, no track, full 50 steps, through a scratch copy of the child | 992 s |
| Cancel during a 50-step run | stopped at step 19 within 2 s |

A studio idle with the model loaded had 62 GiB less free memory than before its first clip.
The time estimate is fitted on five Fast text runs from 512 × 288 to 1280 × 704, and reads each within 8%.
A picture adds about 3.78 thousand tokens to each step. Two pictures solved to 3.77 at 512 × 288
and 3.79 at 1024 × 576, so the cost does not move with the clip: the picture is encoded at its own
size. A clip with a track keeps the measured 4.4 factor instead.
It counts a full 50-step run, so a Fast clip takes about 40% of the figure.
