# Set up model weights and engines

Use this guide to prepare a model before running it. Start from the repository root with `uv` on the server and child processes’ `PATH`, or set `UV` to the `uv` executable.
Edit [studio.toml](../../studio.toml) to change engine paths or model directories.
For model capabilities and reference requirements, see [Models](../reference/models.md).

## Default Image: Qwen Image Turbo

Run an Image generation to download `Qwen/Qwen-Image-2.1-Turbo` into `[qwen21_turbo].model_dir` (about 32.5 GB).
Set that directory before starting if you want another disk or already have the checkpoint.

## Video: LTX-2.5

Video builds its own engine environment on the first run. The studio ships a wrapper,
`studio/l3_interface_adapters/gateways/video/ltx_runtime/ltx_engine.py`, which declares the
pinned [ltx-2-mlx](https://github.com/dgrauet/ltx-2-mlx) port and its exact package versions.
The studio starts it as `uv run --script`. It reads `UV` first, then finds `uv` on `PATH`, so the
engine uses the same `uv` binary as the studio.
`uv` builds and caches that environment, so there is no clone and no `cli_path` to set.
The first run needs network access for the packages, about 1 GB once.

Install `ffmpeg` as well (`brew install ffmpeg` on Homebrew); its configured path is `/opt/homebrew/bin/ffmpeg`.

The engine keeps its own environment because the port pins `mlx-vlm 0.4.3` and
`transformers 5.3.0`, and the studio's image rewriters need `mlx-vlm 0.7.3` or newer with
`transformers` 5.5 or newer. One environment cannot hold both sets.

The prompt enhancer is a second script engine. `mlx_prompt_enhancement_child.py` declares
its own environment with `mlx-vlm 0.7.3`, and the studio runs it with `uv run --script`.
It uses the `uv` that started the studio, from the `UV` variable. A studio started another
way falls back to `uv` on the server's `PATH`. It needs no `cli_path`. The first
enhancement builds that environment, so it takes longer than a warm one.

An engine checkout you already have still works. Set `[mlx_video].cli_path` to its CLI, and the
studio runs its rendering child scripts under that environment's `python`.

Accept the model terms at [dgrauet/ltx-2.5-mlx-q8](https://huggingface.co/dgrauet/ltx-2.5-mlx-q8), then authenticate:

```sh
uv run hf auth login
```

The video pack is about 72 GB. The shipped `model_ltx25` names the same cache the other models
use, `~/Library/Caches/models/ltx-2.5-q8`. Fill it before the first run:

```sh
uv run --with huggingface-hub hf download dgrauet/ltx-2.5-mlx-q8 --local-dir ~/Library/Caches/models/ltx-2.5-q8
```

The `--local-dir` form writes real files. The shared cache form can leave the large weights as Xet
pointers on a client without Xet support, and a run then fails on the first file it opens.
Keep `transformer-dev.safetensors` in the pack. The audio track route uses CFG guidance and fails
with `Dev transformer not found` when only the distilled transformer is present. A text-only clip
still runs without it.
LTX-2.3 keeps a repository id, so its pack downloads on first use.

To use Video Edit effects, accept each adapter’s terms and either place its file in `[mlx_video].lora_dir`
or enable `[mlx_video].fetch_loras`. The default leaves adapter downloads disabled and reports the missing path.
For **Layout to Render**, accept the [adapter terms](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Layout-To-Render), then download to the default adapter directory:

```sh
uv run --with huggingface-hub hf download Lightricks/LTX-2.5-22b-IC-LoRA-Layout-To-Render \
  ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors \
  --local-dir ~/Library/Caches/models/ltx-2.5-loras
```

The LTX-2.5 pack must include `spatial_upscaler_x2_v1_0.safetensors` and its `_config.json`.
Studio checks both before this adapter runs; the pinned engine otherwise silently leaves the upscaler untrained.
LTX-2.3 requires its own pack and is optional.

## Optional Video: MiniMax H3

H3 ships with Studio. Follow its [pinned engine and weight setup](../../studio/l3_interface_adapters/gateways/video/minimax_h3/README.md#install-the-engine),
then add `minimax_h3` to `visible_video_backends`, or use `--all-backends`.
Keep `uv` on the server's PATH, including for its child processes, as the Drama-3 section says.
The worker's PEP 723 header pins the engine's packages, so `uv` builds and caches that environment.
The engine itself stays a source checkout. No model plugin installation is needed.
If you previously installed `open-imagine-minimax-h3`, remove that distribution from
Studio's environment and remove its old `--with` option to avoid a duplicate model ID.

H3 Flash is a second model on the same engine. It needs the base H3 setup and one more
transformer pack. Follow [Install the Flash pack](../../studio/l3_interface_adapters/gateways/video/minimax_h3/README.md#install-the-flash-pack),
then add `minimax_h3_flash` to `visible_video_backends`, or use `--all-backends`.

## Default Voice: Drama-3

The child pins MLX Audio commit `2209e6d76c18d0a24f7ff64d35b4176258acd909` and checkpoint revision `fedc7cc92bab5a180709cbaae6208d10b390bb97`. Its separate environment is declared in the script. To download the weights into the default Hugging Face cache before a run:

```sh
uv run --with huggingface-hub==2.2.0 hf download mlx-community/fish-audio-drama-3-8bit \
  --revision fedc7cc92bab5a180709cbaae6208d10b390bb97
```

`[drama3].python_path` can select an environment with the script's exact dependencies; otherwise `uv` builds its pinned script environment. `[drama3].child_script` selects the child script.
Start a Voice request after the download. The first launch can still prepare its separate dependency environment.
Keep cold setup and warm generation time separate when assessing performance.

## Optional Voice: AuK and AuK Flash

The studio starts its resident Voice child on the first Voice job.
The child uses the pinned AuK revision `6943a1e967409e8c73139a7a345f2a611cfb3dd6`.
Its script declares the separate environment, so the main environment does not need AuK installed.
Keep `uv` on the server's PATH, including for its child processes.
The child downloads `smcleod/AuK-MLX-8bit` at revision `abffd38adf7d9f0a94822e7c153e0c4ef70ef213`.
It uses the default Hugging Face cache. Set `HF_HOME` before starting the server to move that cache.
To fetch the required files before the first job:

```sh
uv run --with huggingface-hub==0.35.3 hf download smcleod/AuK-MLX-8bit \
  --revision abffd38adf7d9f0a94822e7c153e0c4ef70ef213 \
  --include 'dit_flash.q8.safetensors' 'fusion_flash.safetensors' \
    'config_flash.yaml' 'vae.safetensors' 'thinker/*' 'qwen/*'
```

`[auk].child_script` can select another copy of the pinned child script.
With `--all-backends`, the Voice selector offers Drama-3 (`drama3`, the default), AuK (`auk_base`), and AuK Flash (`auk`). Normal startup offers Drama-3 alone.
Flash uses 4 steps. AuK uses the upstream 32-step schedule and guidance 2.
Both offer the same clone, design, edit, and batch controls. A switch releases the previous model.
The selected model loads on the next job. Selecting a model does not download its weights.
AuK shares the Flash encoder and decoder files. Its additional download is about 1.75 GB.
To fetch its files before the first job:

```sh
uv run --with huggingface-hub==0.35.3 hf download smcleod/AuK-MLX-8bit \
  --revision abffd38adf7d9f0a94822e7c153e0c4ef70ef213 \
  --include 'dit_base.q8.safetensors' 'fusion_base.safetensors' \
    'config_base.yaml' 'vae.safetensors' 'thinker/*' 'qwen/*'
```
## Optional Image: Qwen and Viggle Turbo

Use `uv run studio --backend qwen21` to open on full Qwen-Image-2.1. Its approximately 33 GB weights download on first use into the default Hugging Face cache (`HF_HOME` changes the cache root).
Viggle Turbo shares that base and needs its separate adapter. Download the file to `[viggle_turbo].lora_path`:

```sh
uv run hf download Viggle/Qwen-Image-2.1-viggle-turbo \
  Qwen-Image-2.1-viggle-turbo-v0.3-6step-lora-r256.safetensors \
  --local-dir ~/Library/Caches/models/viggle-turbo
```

Then launch with `uv run studio --backend viggle_turbo`.

## Optional Image: FLUX.2

mflux reads one diffusers-layout folder, and its name must contain `klein-base-9b`. The default is `~/Library/Caches/models/mflux-klein-base-9b-uncensored`; `model_dir` in [`studio.toml`](../../studio.toml) moves it. It takes about 33 GB.

1. Everything except the encoder weights comes from the uncensored transformer repo. It is not gated.

       M=~/Library/Caches/models/mflux-klein-base-9b-uncensored
       SRC=https://huggingface.co/darknight9121/FLUX.2-klein-base-9B-bucket-uncensored/resolve/main
       for f in model_index.json scheduler/scheduler_config.json \
                text_encoder/config.json text_encoder/generation_config.json \
                tokenizer/{added_tokens.json,chat_template.jinja,merges.txt} \
                tokenizer/{special_tokens_map.json,tokenizer.json,tokenizer_config.json,vocab.json} \
                transformer/config.json transformer/diffusion_pytorch_model.safetensors.index.json \
                transformer/diffusion_pytorch_model-0000{1,2}-of-00002.safetensors \
                vae/config.json vae/diffusion_pytorch_model.safetensors; do
         curl -L -C - --create-dirs "$SRC/$f" -o "$M/$f"
       done

2. The encoder weights come from the uncensored encoder repo. It is gated: accept its conditions on the HuggingFace page, then pass your token.

       E=~/Library/Caches/models/ponpoke-uncensored-qwen3-8b
       curl -L -C - --create-dirs -H "Authorization: Bearer $HF_TOKEN" \
         https://huggingface.co/ponpoke/flux2-klein-9b-uncensored-text-encoder/resolve/main/model.safetensors \
         -o "$E/model.safetensors"
       ln -s "$E/model.safetensors" "$M/text_encoder/model.safetensors"

   Fetch only `model.safetensors`. The `.gguf` files there are for llama.cpp.

## Optional Image: FLUX3 Image Klein

The child declares its own Python 3.12 environment in a PEP 723 header, so there is no runtime to install. Put `uv` on `PATH`; the studio runs the child with `uv run --script`.

Accept the terms on [the model page](https://huggingface.co/black-forest-labs/flux-3-image-klein), authenticate with `uv run hf auth login`, then download the weights (about 20 GB):

```sh
uv run hf download black-forest-labs/flux-3-image-klein \
  --revision 337337621b8526e120f2275d250242f4a6bedd75 \
  --include 'transformer/*' --include 'text_encoder/*' --include 'vae/*' \
  --local-dir ~/Library/Caches/models/flux3-image-klein
uv run studio --backend flux3
```

Set `[flux3].model_dir` if you install elsewhere. The defaults are eight-bit weights and 16 steps. Write a full scene caption, including for edits.

## Image: Krea 2 Turbo

Krea 2 Turbo is optional. Add `krea2` to `visible_backends` in `studio.toml`, select it with
`--backend krea2`, or use `--all-backends` to expose it alongside the other optional models.
Krea 2 runs on the mflux the studio already pins, so it needs no runtime of its own.
Download the eight-bit weights (about 22 GB):

```sh
uv run hf download mflux-community/krea-2-turbo-mflux-q8 \
  --exclude .DS_Store \
  --local-dir ~/Library/Caches/models/krea-2-turbo-mflux-q8
uv run studio --backend krea2
```

Set `[krea2].model_dir` if you install elsewhere. The weights are stored at eight bits, so the
section takes no `quantize`. The model runs the 8 steps it was distilled for, without guidance.
Add one reference to start from it; the strength sets how close the result stays.

## Optional Image: MiniMax H3-Image

MiniMax H3-Image is optional. It runs on [h3-image-mlx](https://github.com/Anionex/h3-image-mlx),
an Apache-2.0 MLX engine, from the PEP 723 script header of its child. uv builds and caches that
environment, so the studio's own environment needs no engine. The engine's int8 kernel needs an
M5 or M6 GPU. On another chip the engine uses its portable path, which this project did not measure. Read the [license terms](../reference/model-licenses.md) before you download.

Keep `uv` on the server's PATH, including for its child processes, as the Drama-3 and AuK
sections say. The child's script header pins the engine, so the first run builds its environment.

Download the five weight files (about 49 GB), then check their hashes. The fetch and the verify
run in an ephemeral environment with the same pinned engine:

```sh
E="h3-image-mlx @ git+https://github.com/Anionex/h3-image-mlx@64df997cd00a698302b1303f51028eee179487fe"
M=~/Library/Caches/models/minimax-h3-image
uv run --with "$E" h3-image-mlx fetch --models "$M" --source huggingface
uv run --with "$E" h3-image-mlx verify --models "$M"
uv run studio --backend minimax_h3_image
```

`fetch` resumes a partial file, so run it again if the connection drops.
Set `[minimax_h3_image].model_dir` if you install elsewhere. The weights are
stored at eight bits, so the section takes no `quantize`. The model runs six steps without guidance.
Edit takes one to four references at about 4 MP. A smaller edit came out posterized, so the studio
does not offer one. On an M5 Pro, a picture takes about 20 seconds at 1 MP and about a minute at 4 MP.
An edit takes about two and a half minutes with one large reference and about nine with four. Name a reference in the prompt as `<Picture 1>`, in the order you added it.

## Offer the installed models

Start with `uv run studio --all-backends` to show all model selectors, or configure a subset with
`visible_backends`, `visible_video_backends`, and `visible_voice_backends` in `studio.toml`.
Selecting a model does not load its weights. The next operation loads it.
See [model licenses](../reference/model-licenses.md) before choosing a model for your use.
