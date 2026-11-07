# MiniMax H3 model plugin

Experimental MiniMax H3 Q8 generation on Apple Silicon, through Open Imagine's Video workspace.
The plugin drives Phosphene's staged runner at commit
`63893b3f33a62316a8b2065bcfba69ec0cc49aff`. Each large component leaves memory before the next loads.

## Current scope

- Text to video with native stereo audio, 24 fps, 73-124 frames on the `17n+5` grid.
- Up to three keyframes, each on its own frame. A still at frame 0 is the first frame. A still on
  the last frame is the last frame, and a still on any other frame is a keyframe there.
  Each still is cover-cropped to the canvas. The page puts stills without a frame on the first
  frame, then the last frame, then the middle, and gives a captured frame the nearest free frame.
- An audio track drives the clip, for example a voice for lip sync. The clip keeps that track as
  its sound. WAV, MP3, FLAC, OGG, M4A and AIFF decode in memory, including an M4A that keeps
  its index after its audio data.
- Landscape, portrait and square canvases. The initial landscape canvas is 512 x 288.
- The base schedule uses nine sigma points and eight transformer evaluations.
- Ordered batches use Studio's sequential fallback. One child renders one clip.
- Cancellation stops the owned process group, including its media encoder.

Video edits, prompt rewriting, Looks, templates, LoRAs, long clips and distilled Fast adapters
are not offered in this version. A keyframe has no strength setting.
H3's distilled Fast schedule differs from LTX's float16 Fast mode.
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
  -r model_plugins/minimax_h3/engine-requirements.txt
uv run --with ./model_plugins/minimax_h3 python -m open_imagine_h3.download
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
uv run --with ./model_plugins/minimax_h3 studio \
  --config model_plugins/minimax_h3/studio.toml --port 8873 \
  --private-results-dir /tmp/open-imagine-h3-private
```

Add `--stub` to verify the form without loading models. The sample config offers
H3 and the existing LTX-2.5 backend. An ordinary config can add `minimax_h3` to
`visible_video_backends` after installing this plugin.

The optional `[minimax_h3]` settings are `engine_dir`, `model_dir` and `python_path`.
Defaults match the commands above. Startup does not inspect or load weights.
The worker checks the engine commit and tracked source before running.
Generation stays offline and refuses incomplete weights.

The host needs the subprocess input/output support in this change. Older Studio
versions do not support this plugin's memory transport.

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
Only numerical step and phase metrics cross stderr. Engine diagnostics are suppressed.
Studio applies its existing private ownership checks and encrypted result storage.

## Why it looks like this

The external plugin contract already provides model selection and the shared model lock.
A separate runtime keeps H3's MLX and tokenizer dependencies out of the LTX environment.
The adapter retains the upstream staged sampler and full VAE decode.
The main subprocess driver adds optional binary pipes and owned-group cancellation.
Existing engines keep their previous transport by default.

One real-model smoke test on an M5 Pro with 64 GiB passed through this plugin's gateway and worker.
It rendered 512 x 288, 73 frames at 24 fps, with seed 7 and native stereo audio.
The child took 75.6 seconds. MLX peak allocation was 25.6 GiB; sampled child RSS peaked at 25.8 GiB.
These are one run's measurements, not total system memory or a speed guarantee.
The MP4 passed full video/audio decoding. Higher resolutions and longer clips remain unmeasured.
The browser stopped a real render after its first step in 0.24 seconds in a separate check.
A real private render passed ownership checks, encrypted storage checks, repeated downloads and deletion.

Keyframes and a track were measured on 2026-11-07 on the same machine, at 512 x 288, 73 frames
and seed 11. Each run went through the Studio HTTP API on this plugin's gateway and worker:

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

CPU tests verify frame counts, stereo audio, memory transport, the in-memory keyframes and track,
the M4A index move, private diagnostic suppression and cancellation.

## License

This plugin's code is MIT. The engine port is Apache-2.0. The weights use the
[MiniMax H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/42ed227ee7df40d41602854ae760620d6eb651fe/LICENSE),
which includes territory restrictions. The Qwen text encoder retains its source terms.
Read the downloaded LICENSE, NOTICE and modification notices before use or redistribution.
No model weights are included in this package.
