# MiniMax H3 model plugin

Experimental MiniMax H3 Q8 generation on Apple Silicon, through Open Imagine's Video workspace.
The plugin drives Phosphene's staged runner at commit
`63893b3f33a62316a8b2065bcfba69ec0cc49aff`. Each large component leaves memory before the next loads.

## Current scope

- Text to video with native stereo audio, 24 fps, 73-124 frames on the `17n+5` grid.
- Landscape, portrait and square canvases. The initial landscape canvas is 512 x 288.
- The base schedule uses nine sigma points and eight transformer evaluations.
- Ordered batches use Studio's sequential fallback. One child renders one clip.
- Cancellation stops the owned process group, including its media encoder.

Reference conditioning, video edits, supplied audio, prompt rewriting, Looks, templates,
long clips and distilled Fast adapters are not offered in this first version.
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

The parent sends the prompt over stdin and receives MP4 bytes over stdout.
The prompt never enters the process command line. The adapter replaces the engine's
metrics writer with an in-memory recorder and disables persistent prompt caches.
The encoder pipes video and WAV data into ffmpeg and returns a fragmented MP4.
No prompt, metrics, WAV, frames or MP4 file is written by this path.
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

CPU tests verify frame counts, stereo audio, memory transport, private diagnostic suppression and cancellation.

## License

This plugin's code is MIT. The engine port is Apache-2.0. The weights use the
[MiniMax H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/42ed227ee7df40d41602854ae760620d6eb651fe/LICENSE),
which includes territory restrictions. The Qwen text encoder retains its source terms.
Read the downloaded LICENSE, NOTICE and modification notices before use or redistribution.
No model weights are included in this package.
