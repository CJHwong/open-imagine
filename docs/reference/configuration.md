# CLI and configuration

Run from the checkout with `uv run studio`. The console command remains `studio`.

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address. |
| `--port` | `8765` | Server port. Browser storage belongs to the address and port. |
| `--backend` | `default_backend` | Initial Image model; adds it to the offered models. |
| `--all-backends` | Off | Enable model selectors across Image, Video, and Voice. |
| `-q`, `--quantize` | Model configuration | Opening Image model quantization: 0, 3, 4, 5, 6, or 8 bits; 0 means full precision. |
| `--config` | `studio.toml` | Configuration file. |
| `--allow-origin` | None | Let a page at this origin post, such as a Tailscale serve URL. Repeat it for each origin. See [Open from another device](../how-to/open-from-another-device.md). |
| `--stub` | Off | Simulated engines: placeholder images, a Voice test tone, and Video metadata. No model loading. |

## Settings

[studio.toml](../../studio.toml) contains the current defaults and path examples.

| Key | Meaning |
|---|---|
| `default_backend`, `visible_backends` | Initial and available Image models. |
| `default_video_backend`, `visible_video_backends` | Initial and available Video models. |
| `default_voice_backend`, `visible_voice_backends` | Initial and available Voice models. |
| Image backend `quantize` | Weight quantization; 0 is the default. |
| Image backend `model_dir` / `lora_path` | Local weights or adapter path, where supported. |
| Image backend `rewrite_generate_model`, `rewrite_edit_model`, `rewrite_quantize` | Prompt rewriter for each mode, and its load-time quantization. 0, the default, keeps full precision; 2, 3, 4, 5, 6 and 8 are the widths MLX offers, and any other value stops the studio at start. The shipped `studio.toml` sets 8. |
| `[mlx_video].cli_path`, `ffmpeg_path` | Separate Video executable and media tool. |
| `[mlx_video].model_ltx25`, `model_ltx23` | Video pack identifiers. |
| `[mlx_video].lora_dir`, `fetch_loras` | Effect adapter directory and opt-in download policy. |
| `[mlx_video].batch_policy` | `auto`, `enhance_only`, or `sequential`. |
| Backend `max_loras`, `[[<backend>.loras]]` | The LoRAs a model offers. See [LoRAs](#loras). |
| `[auk].child_script` | AuK child implementation. |
| `[drama3].child_script`, `python_path` | Drama-3 child and optional prebuilt environment. |

A workspace shows its model selector only when more than one model is offered.
Selecting a model does not load it. Paths relative to the configuration file resolve from that file.

## LoRAs

A built-in model can offer your own LoRA files. Add one `[[<backend>.loras]]` table for
each file under the model's section. These models take them:

| Section | Engine | Modes |
|---|---|---|
| `qwen21`, `qwen21_turbo`, `viggle_turbo` | mflux | Generate and Edit; `modes` limits a LoRA to some of them |
| `ltx25_mlx` | ltx-2-mlx | Generate and Edit, but not with an audio track |
| `ltx23_mlx` | ltx-2-mlx | Generate, but not with an audio track |

`flux2` takes no LoRAs, and a table under it stops the studio at start.

```toml
[qwen21_turbo]
max_loras = 2

[[qwen21_turbo.loras]]
id = "warm_film"
label = "Warm film"
path = "loras/warm-film.safetensors"
strength = 0.8
recommended = [0.6, 1.0]
trigger = "warm film"
modes = ["generate"]
```

| Key | Default | Meaning |
|---|---|---|
| `id` | Required | Lowercase letters, digits and underscores. A request names the LoRA by this id. |
| `label` | Required | The name the page shows. |
| `path` | Required | The weights file. A relative path resolves from the configuration file. |
| `strength` | 1.0 | The strength a request gets when it names the LoRA without one. The page starts every slider at 0. |
| `min_strength`, `max_strength`, `strength_step` | 0, 2, 0.05 | The range the slider offers and a request may send. It must reach 0 and go above it: 0 is off. |
| `recommended` | None | `[low, high]` inside that range, shown as a suggestion. |
| `trigger` | None | Words added after the prompt when the prompt does not hold them. |
| `hint` | None | One sentence under the slider. |
| `modes` | All | Image only: the mode ids the LoRA applies to. A video table refuses it. |
| `max_loras` | 1 | On the section: how many LoRAs one run takes. |

Put the tables of an LTX model under its own section, such as `[ltx25_mlx]`. A table under
`[mlx_video]` stops the studio at start.

The studio does not check the files at start, so the stub runs without them. A run refuses
a missing file by the LoRA's id, and the server log names the path. It never downloads one.
The path stays on the server: the page, the API and the operation record name the LoRA by
its id, also when an engine error names the file.

A different set of picks rebuilds the image model before the run, so an image batch takes
one set for each mode. An LTX batch takes one set for all its clips. An LTX run attaches the
LoRAs unfused, because fusing them into the 8-bit pack loses most of a small update. A Video
Edit effect stays fused, because the mode applies to the effect's own adapter too, and its
recipe was measured fused.

To keep private files out of this checkout, copy `studio.toml` to a folder of your own, add
the tables there, and start with `uv run studio --config <that file>`. The relative paths of
the other settings then resolve from that folder too, so make them absolute.

## Development checks

```sh
uv run pytest
uv run prek run --all-files
```

The CPU suite enforces 100% statement and branch coverage for `studio/`.
Tests marked `live` require installed weights and a free GPU.
Use a fresh `uv run studio --stub --all-backends --port 8895` server for browser checks under `tests/e2e/`.
The page is read at startup; restart the stub after page changes and between suites.
