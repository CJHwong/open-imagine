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
- 50 steps, the default of diffusers and SGLang, or 20 in Fast mode. 50 is not a limit of the
  weights: the MLX backend runs the same base checkpoint at eight transformer calls. No shorter
  schedule was tried here.

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

## HyperFlow H3 Flash

`minimax_h3_flash_cuda` runs [HyperFlow H3 Flash](https://huggingface.co/VideoRebirthAI/hyperflow-h3-flash),
Video Rebirth's pruned H3, on this child with `--flash`. It takes the same inputs as base H3 here:
text, a first or last frame, up to nine pictures, and pictures with a track. It runs six steps and
has no Fast mode.

Flash keeps base H3's encoder, VAEs and workflows. It replaces the two transformers with its own,
13.7 and 13.9 billion parameters against about 31 billion, where most large layers are low-rank
pairs. Its sampler hands each step the time it steps to as well as the time it is at, so the
child swaps Flash's two sampler blocks into the three workflows before it builds the pipeline. A
swap on a built pipeline does not reach the blocks it runs. The block swap is Flash's private
code, so the child checks that it replaced three of each and refuses to start otherwise.

The transformers land in NVFP4 from the bf16 files, as base H3's do. The low-rank pairs, the
per-block AdaLN projections and the output norm stay in bf16, as Flash's own code keeps them. The
last two take a 16-wide input, which the NVFP4 kernel refused.

### Weights

The child fetches `fl2va_bf16/` and `ref2va_bf16/` of `VideoRebirthAI/hyperflow-h3-flash` at revision
`6834923e1a9ca4d15a2349a622b6677bea1404cb`, 52 GiB, and the encoder and VAEs of the base release.
It never fetches the base transformers. The sampler comes from the
[`hyperflow-h3-flash`](https://github.com/Video-Rebirth/hyperflow-h3-flash) package at commit
`dc67ea7`, pinned in the child's script header. Deleting Flash's storage removes only its
transformers; the encoder and the VAEs belong to base H3. Deleting base H3's storage removes them
too, and Flash still reads as ready: its next load downloads them again, the 63 GiB encoder and the VAEs.

The weights are a Model Derivative of MiniMax-H3 under the MiniMax H3 Community License Agreement.
It is not an open-source license. It does not cover use in the European Union, the United Kingdom,
the Republic of Korea or the United States without MiniMax's authorization, and it includes an
Acceptable Use Policy.

### Measured

On the DGX Spark, 2026-11-24, through the Studio operations API, seed 7, warm:

| Clip | Base H3, Fast mode (20 steps) | Flash (6 steps) |
|---|---:|---:|
| Text, 512 × 288, 124 frames | 79.5 s | 32.1 s |
| Text, 1024 × 576, 124 frames | 380.8 s | 138.5 s |
| Text, 1280 × 704, 124 frames | 716.7 s | 261.7 s |
| Two pictures, 512 × 288 | 397.1 s, through the child directly | 142.5 s |
| One picture and a 5 s track, 512 × 288 | 222.9 to 360.6 s | 82.2 s |

A Flash step costs about nine tenths of a base step: attention costs the same, and attention
dominates at these sizes. The gain is the step count. The first clip of a child takes about 95 s
more, against about 135 s for base H3, and the loaded model holds 43.1 GiB against 62.

The clips at 1280 × 704 and at 345 frames kept one coherent subject, as did text and two pictures at
seeds 7, 8 and 9. The MLX notes warn that a short schedule fails first on long clips; these runs
did not show it, but none ran past 345 frames, the cap of this backend.
