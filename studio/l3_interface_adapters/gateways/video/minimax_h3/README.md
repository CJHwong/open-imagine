# MiniMax H3

Experimental MiniMax H3 Q8 generation on Apple Silicon, through Open Imagine's Video workspace.
The built-in integration drives Phosphene's staged runner at commit
`63893b3f33a62316a8b2065bcfba69ec0cc49aff`. Each large component leaves memory before the next loads.

## Current scope

- Text to video with native stereo audio, 24 fps, 73-175 frames on the `17n+5` grid, which is
  about 3 to 7.3 seconds. The page has presets for 73, 124 and 175 frames, and its slider takes
  every 17-frame step between them.
- Up to three keyframes, each on its own frame. A still at frame 0 is the first frame. A still on
  the last frame is the last frame, and a still on any other frame is a keyframe there.
  Each still is cover-cropped to the canvas. The page puts stills without a frame on the first
  frame, then the last frame, then the middle, and gives a captured frame the nearest free frame.
- An audio track drives the clip, for example a voice for lip sync. The clip keeps that track as
  its sound. WAV, MP3, FLAC, OGG, M4A and AIFF decode in memory, including an M4A that keeps
  its index after its audio data.
- Landscape, portrait and square canvases. The initial landscape canvas is 512 x 288. The high
  quality class is 1280 x 704 and 704 x 1280, the same sizes as LTX's. On a 64 GiB Mac the
  memory gate takes them up to 158 frames. See "Memory gate" below.
- These canvases are the page's menu, not a limit. Through the API a clip can have any ratio,
  for example 640 x 480 for a 4:3 picture. Each side is from 256 to 1280 pixels, on the 32 pixel
  grid, and the clip has no more pixels than 1280 x 704. The memory gate estimates such a size
  by its packed rows, as it does for the sizes on the menu.
- The base schedule uses nine sigma points and eight transformer evaluations.
- Fast mode runs four on the same weights, for clips up to the size of 1024 x 576 at 124 frames with one keyframe. See
  "Fast mode" below.
- LoRA files that your settings list. See "LoRAs" below.
- Ordered batches use Studio's sequential fallback. One child renders one clip.
- Cancellation stops the owned process group, including its media encoder.

Video edits, prompt rewriting, Looks, templates, clips longer than 175 frames and
distilled Fast adapters are not offered in this version. A keyframe has no strength setting.
No time estimate is published from a single small smoke test.

## Install the engine

Use an Apple Silicon Mac with 64 GiB of unified memory and ffmpeg/ffprobe on PATH.
Reserve about 120 GB for downloads and conversion; this is a planning allowance.
The original BF16 DiT stays on disk after conversion. Delete it explicitly if it is no longer needed.

From the Open Imagine repository:

```sh
git clone --filter=blob:none --no-checkout https://github.com/mrbizarro/minimax-h3-mlx.git \
  ~/Library/Caches/open-imagine/engines/minimax-h3-63893b3
git -C ~/Library/Caches/open-imagine/engines/minimax-h3-63893b3 checkout --detach \
  63893b3f33a62316a8b2065bcfba69ec0cc49aff
uv venv --python 3.11 ~/Library/Caches/open-imagine/engines/minimax-h3-63893b3/.venv
uv pip install --python ~/Library/Caches/open-imagine/engines/minimax-h3-63893b3/.venv/bin/python \
  -r studio/l3_interface_adapters/gateways/video/minimax_h3/engine-requirements.txt
uv run python -m studio.l3_interface_adapters.gateways.video.minimax_h3.download
```

The download utility pins every source revision and fetches the model terms.
It downloads the pruned BF16 DiT, the Q8 text encoder, compact VAEs and tokenizer,
and the upstream text configuration. It never loads a model.
The engine's own download script follows branch tips, so use this utility for reproducibility.

With Studio stopped and the GPU free, build Q8 using the pinned engine:

```sh
~/Library/Caches/open-imagine/engines/minimax-h3-63893b3/.venv/bin/python \
  ~/Library/Caches/open-imagine/engines/minimax-h3-63893b3/scripts/quantize_stream.py \
  --src ~/Library/Caches/models/minimax-h3/deepbeep-pruned-bf16/MiniMax-H3-FL2VA-pruned_bf16.safetensors \
  --out ~/Library/Caches/models/minimax-h3/h3-dit-q8
```

The builder's closing validation holds the BF16 source and Q8 model in one process.
That phase can approach the memory ceiling on a 64 GiB Mac. Close other model workers first.
Do not run conversion beside a render.

## Run in Studio

```sh
uv run studio \
  --config studio/l3_interface_adapters/gateways/video/minimax_h3/studio.toml --port 8873 \
  --private-results-dir /tmp/open-imagine-h3-private
```

Add `--stub` to verify the form without loading models. The sample config offers
H3 and the existing LTX-2.5 backend. An ordinary config can add `minimax_h3` to
`visible_video_backends` after installing its engine and weights.

The optional `[minimax_h3]` settings are `engine_dir`, `model_dir` and `python_path`.
Defaults match the commands above. Startup does not inspect or load weights.
The worker checks the engine commit and tracked source before running.
Generation stays offline and refuses incomplete weights.

H3 ships with Studio. If an earlier setup installed `open-imagine-minimax-h3`, remove
that distribution from Studio's environment (`uv pip uninstall open-imagine-minimax-h3`)
and remove its old `--with` option. Its entry point would otherwise conflict with the
built-in `minimax_h3` ID; duplicate-ID protection remains enabled.

## Fast mode

Send `fast_mode: true`, or press Fast mode under Advanced on the page. H3 then runs four
transformer evaluations in place of eight, on the same weights. It differs from LTX-2.5's Fast
mode, which keeps its steps and computes in float16.

Measured on 2026-11-09 on an M5 Pro with 64 GiB. Each run drove this integration's worker directly
with one still, at 1024 x 576, 124 frames and seed 42:

| Schedule | Denoise | Whole clip | Worker peak |
|---|---|---|---|
| Eight evaluations | not recorded | 754 s, through the Studio API | about 29.3 GiB |
| Four evaluations, seven scenes | 344 to 347 s | 413 to 450 s | 29.2 GiB |

The memory gate keeps the base figure, because the peak did not change. Fast mode refuses a clip
with more packed video rows than the measured clip: 1024 x 576 at 124 frames with one keyframe,
which is 21,888 rows. Each keyframe adds one latent frame of rows, so the same clip with three
keyframes is refused. The engine's own campaign found that a shorter schedule fails first on long clips: eight evaluations duplicated a subject at
about 25,000 rows. That figure counts the text and audio rows too, so the margin is smaller than
the difference suggests. 1280 x 704 takes Fast mode only at 73 frames.

No blind test compared four evaluations against eight. The seven clips at four looked coherent,
but generated details and motion can differ.

A distilled Turbo LoRA was tried for Fast mode and dropped. On the Q8 layers a LoRA cannot
merge, so each of its evaluations costs about a third more, and four of them took 609 s for the
same clip. It also burned the spoken line into the picture as a subtitle.

## LoRAs

H3 takes LoRA files for its DiT. List each file in a `[[minimax_h3.loras]]` table under the
section. The keys are the ones of a built-in model's table, in
[the configuration reference](../../../../../docs/reference/configuration.md#loras), except `modes`:
a video LoRA applies to every mode. `max_loras` sets how many LoRAs one clip can pick. It is 1
when the section does not set it. Keep it at 1: the memory gate takes one LoRA per clip.

```toml
[[minimax_h3.loras]]
id = "example_style"
label = "Example style"
path = "~/Library/Caches/models/minimax-h3/loras/example-style.safetensors"
strength = 0.7
recommended = [0.5, 0.9]
trigger = "example trigger"
```

The page and the API show the id and the label, never the path. If the names of your LoRAs
are private, keep their tables in a settings file outside the repository, and pass that file
with `--config`.

The engine adds each LoRA beside the Q8 layers at run time, because a LoRA cannot merge into a
quantized weight. It stacks the LoRAs of a clip in the order picked. It reads:

| Part of the file | What the engine takes |
|---|---|
| Tensor names | `<module>.lora_A.weight` and `<module>.lora_B.weight`, with or without a `diffusion_model.`, `transformer.` or `model.diffusion_model.` prefix |
| Modules | `attn.qkv_proj`, `attn.out_proj`, `mlp.fc1` and `mlp.fc2` of the 50 blocks and the 2 token refiner blocks |
| Data types | BF16 and F32. It computes an F16 file in BF16, because F16 overflows in the MLP |
| Scale | The strength you pick. The engine reads no `alpha` tensor, so strength 1.0 assumes alpha equals the rank |

Before the denoise, the worker reads the engine's count of the layers it applied. It stops the
run, and the page names the LoRA by its id, in two cases:

- H3 can load no layer of the file. A kohya file with `lora_down` and `lora_up` names and a
  LoKr file are two examples.
- Some parts of the file match no layer. The adaLN pairs of a distilled speed LoRA are an
  example, because the pruned DiT has no input for them.

These limits apply:

- A clip that follows an audio track takes no LoRA. The host refuses the pair until a real run
  tries it.
- The memory gate takes one LoRA per clip, and refuses two. It adds 2.5 GiB to the clip's own
  figure up to 1024 x 576 at 175 frames, and more for a larger clip. One run measured it, with
  an 86 MB LoRA. A LoRA file of several GiB is not covered.
- The engine reads the two halves of `mlp.fc1` as `[gate; value]`. ai-toolkit trains H3 LoRAs
  in the same order, so this integration does not pass `--lora-fc1-swap`. A file in the other order
  still makes a plausible clip, and nothing reports it: the same LoRA with and without the swap
  gave two clean clips.

One LoRA costs little on the measured runs. At 512 x 288 and 73 frames, it added 2.1 s to a
53.6 s denoise and 0.14 GiB to its peak. A clip of 1024 x 576 and 175 frames with it took
1,175 s.

## Private operations

The parent sends the prompt, the keyframes and the audio track over stdin and receives MP4
bytes over stdout. None of them enters the process command line, and their file names stay in
the parent. The worker gives the engine each still and the track under a path that does not
exist on disk, and it answers the engine's three reads from memory: the file check,
`Image.open` and `read_audio`. A read that bypasses them fails.
ffmpeg decodes the track from a pipe. A pipe reads forward only, so the worker first moves an
M4A index that follows the audio data to the front, the way `qt-faststart` does. The adapter replaces the engine's
metrics writer with an in-memory recorder and disables persistent prompt caches.
The encoder pipes video and WAV data into ffmpeg and returns a fragmented MP4.
No prompt, still, track, metrics, WAV, frames or MP4 file is written by this path.
Only numerical step and phase metrics cross stderr, with the index and layer counts of a LoRA
that does not fit. Engine diagnostics are suppressed.
The path of each picked LoRA goes to the worker over stdin with the rest of the request, so no
pick enters a command line. The engine reads the file from where the settings name it, and
its report on each LoRA goes to the suppressed output. A missing file is refused by its id,
and no log line names the pick.
Studio applies its existing private ownership checks and encrypted result storage.

## Why it looks like this

Studio's model provider supplies selection, LoRA settings and the shared model lock.
A separate runtime keeps H3's MLX and tokenizer dependencies out of the LTX environment.
The adapter retains the upstream staged sampler and full VAE decode.
The main subprocess driver adds optional binary pipes and owned-group cancellation.
Existing engines keep their previous transport by default.

One real-model smoke test on an M5 Pro with 64 GiB passed through this integration's gateway and worker.
It rendered 512 x 288, 73 frames at 24 fps, with seed 7 and native stereo audio.
The child took 75.6 seconds. MLX peak allocation was 25.6 GiB; sampled child RSS peaked at 25.8 GiB.
These are one run's measurements, not total system memory or a speed guarantee.
The MP4 passed full video/audio decoding.
The browser stopped a real render after its first step in 0.24 seconds in a separate check.
A real private render passed ownership checks, encrypted storage checks, repeated downloads and deletion.

Keyframes and a track were measured on 2026-11-07 on the same machine, at 512 x 288, 73 frames
and seed 11. Each run went through the Studio HTTP API on this integration's gateway and worker:

| Inputs | Seconds |
|---|---|
| First frame, a keyframe at frame 36, last frame | 100 |
| An 11.7 MB M4A voice track, index after the data | 73 |
| First frame, last frame and a voice track, private | 86 |

The text-only clip above took 75.6 seconds. An earlier spike drove the same worker directly
with the same inputs. Its MLX peak was 25.6 GiB for text or a track alone and 27.0 GiB with
three stills. The text encoder sets the peak.

The first frame matched its still at about 31 dB PSNR. A keyframe or a last frame steers the
picture without copying it, at about 27 dB against 24 dB without one. The clip's sound followed
the voice track after the AAC encoder's own 1024-sample lead-in. No run left a new file under
the temp folders or the caches. The private run stayed hidden from callers without its key.
A cancel from the page's status bar stopped a real render 0.4 seconds after the press.

175-frame clips were measured on 2026-11-07 on the same machine, at 512 x 288 and seed 11.
Each run went through the Studio HTTP API on this integration's gateway and worker:

| Inputs | Seconds |
|---|---|
| Text | 187 |
| First frame, a last frame on frame 174 and a 5.9 s voice track | 209 |

Each time runs from the request to the finished operation, read by the caller every 2 seconds.
Each clip had exactly 175 frames and 7.3 seconds of stereo sound. Sampled child RSS peaked at
23.4 GiB for text and at 24.0 GiB with the stills and the track. RSS leaves out most of the GPU
memory, so these figures are low. The 1024 x 576 run below reads the footprint instead.

The two stills were frames 100 and 20 of the text clip, and both runs used seed 11. The first
frame matched its still at 31.1 dB PSNR, and frame 174 matched the last still at 31.2 dB. Frame
174 scored 26.7 dB against the other still. The stills show the same scene as the seed's own
clip, so these scores are not comparable with the 27 dB figure above. The clip's loudness
followed the voice track with a correlation of 0.80 over the track's 5.9 seconds.

The model denoises 2.4 times as many video tokens at 175 frames as at 73. The text run took 2.5
times the 75.6 s child time above, which a different clock measured.

One 1024 x 576 clip of 175 frames was measured on 2026-11-07 on the same machine. A page run
drove it through this integration's gateway and worker, on a build without the memory gate. It took
1,257.6 seconds from start to finish by the studio's own clock, about 2.5 minutes a step. Once a
second, a sampler read the worker's `phys_footprint`, which counts its GPU memory, and the free
memory that `memory_pressure` reports:

| Phase | Worker footprint | macOS free memory |
|---|---|---|
| Denoise | 32.9 GiB | 33 to 34 percent |
| Video decode, about 70 s | 12 to 13.5 GiB | 66 to 69 percent |
| MP4 encode | 1.3 GiB | 86 percent |
| After the run | none | 86 percent |

The sampler started at step 6 of 8. The denoise footprint stays flat from step to step, and the
text encoder before it peaked at 25.6 GiB in the runs above. Free memory fell by 53 percent of
64 GiB, about 34 GiB. In the same run, RSS read 17.9 GiB.

One 1280 x 704 clip of 175 frames was measured the same evening, the same way. This sampler ran
from the worker's first second. The clip took 2,540.5 seconds, about 5 minutes a step:

| Phase | Worker footprint | macOS free memory |
|---|---|---|
| Before the run | none | 87 percent |
| Text encoder, about 10 s | up to 28.8 GiB | down to 38 percent |
| Denoise, about 40 minutes | 39.3 GiB | 13 to 15 percent, 11 at the lowest |
| Video decode, about 2 minutes | 10 to 16.6 GiB | 58 to 61 percent |
| After the run | none | 83 percent |

At the lowest point, free memory fell by 76 percent of 64 GiB, about 48.6 GiB, against a 39.3
GiB footprint. Other programs moved free memory by up to 4 percent over the run. 1280 x 704 has
about 1.5 times the tokens of 1024 x 576, and the step took twice as long. 704 x 1280 has the
same tokens as 1280 x 704. It, 576 x 1024, 288 x 512 and 512 x 512 are offered, but no run
measured them at any length.
A size off the menu, such as 640 x 480, has no run either.

### Memory gate

The studio starts an H3 run only when its memory estimate plus an 8 GiB reserve fits in the
free memory that macOS reports. The estimate is the free memory drop of the two runs above, plus
1 GiB. Between them it follows a straight line by packed rows. A latent frame holds (W / 32) x
(H / 32) rows. Each still adds one latent frame of rows, and a track adds none, because the
engine writes it into the clip's own audio rows. A clip with no more rows than the 1024 x 576
run takes that run's 35.6 GiB.

An idle 64 GiB Mac reported 87 percent free, about 55.7 GiB, before the runs above. At 1280 x 704
it takes these lengths:

| Frames | Estimate plus reserve | Idle 64 GiB Mac |
|---|---|---|
| 124 | 45.9 GiB | starts |
| 158 | 53.7 GiB, 55.3 with two stills | starts |
| 158 with three stills | 56.0 GiB | refused |
| 175 | 57.6 GiB | refused |

A 175 frame clip at 1280 x 704 with any still, and any clip longer than 175 frames, has no
estimate, so the gate refuses it too. Neither measured run recorded its stills or its track.
The estimate for stills and a track comes from the engine's row layout, not from a run.

CPU tests verify frame counts, stereo audio, memory transport, the in-memory keyframes and track,
the M4A index move, private diagnostic suppression and cancellation.

## License

This integration's code is MIT. The engine port is Apache-2.0. The weights use the
[MiniMax H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/42ed227ee7df40d41602854ae760620d6eb651fe/LICENSE),
which includes territory restrictions. The Qwen text encoder retains its source terms.
Read the downloaded LICENSE, NOTICE and modification notices before use or redistribution.
No model weights are included in this package.
