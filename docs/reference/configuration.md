# CLI and configuration

Run from the checkout with `uv run studio`. The console command remains `studio`.

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address. |
| `--port` | `8765` | Server port. Browser storage belongs to the address and port. |
| `--backend` | `default_backend` | Initial Image model; adds it to the offered models. |
| `--memory-policy` | `[memory].policy` | `immediate` or `boundary`. Overrides the file for this start. |
| `--memory-boundary-percent` | `[memory].boundary_percent` | The share of physical memory loaded models may hold under the boundary policy. Overrides the file. |
| `--queue-max-size` | `[queue].max_size` | How many asynchronous operations may wait behind the running one. `0` refuses instead of queuing. Overrides the file. |
| `--all-backends` | Off | Enable model selectors across Image, Video, and Voice. |
| `-q`, `--quantize` | Model configuration | Opening Image model quantization: 0, 3, 4, 5, 6, or 8 bits; 0 means full precision. |
| `--config` | `studio.toml` | Configuration file. |
| `--allow-origin` | None | Let a page at this origin post, such as a Tailscale serve URL. Repeat it for each origin. See [Open from another device](../how-to/open-from-another-device.md). |
| `--stub` | Off | Simulated engines: placeholder images, a Voice test tone, and Video metadata. No model loading. |
| `--connect[=on|off]` | On | Start the phone connection and print its QR code. `--connect=off` disables it for this start. |

## Settings

[studio.toml](../../studio.toml) contains the current defaults and path examples.

| Key | Meaning |
|---|---|
| `default_backend`, `visible_backends` | Initial and available Image models. |
| `default_video_backend`, `visible_video_backends` | Initial and available Video models. |
| `default_voice_backend`, `visible_voice_backends` | Initial and available Voice models. |
| `require_memory_estimate` | `false`. Require a measured peak for every media run and batch item. Settings → Memory or `POST /api/v1/settings` can change this app-wide policy. `false` allows unmeasured workflows while retaining checks for known limits. Saved app preferences override this startup default. |
| `settings_path` | `~/.config/open-imagine/settings.json`. Stores app preferences across restarts, without operation data. Relative paths resolve beside the TOML file. Stub servers keep preferences in memory and do not read or write this file. |
| `[memory].policy` | `immediate` or `boundary`. `immediate` frees the previous model when another runs or the page leaves its workspace. `boundary` keeps loaded models and frees the oldest first when the next would pass `boundary_percent` of physical memory. |
| `[memory].boundary_percent` | `84`. The share of physical memory that loaded models may hold under the boundary policy. |
| `[queue].max_size` | `8`. Asynchronous operations that wait behind the running one. `0` restores the single-slot refusal. |
| `[connect].enabled` | `true`. Start the dumbpipe listener and print a phone pairing QR code at startup. |
| `[connect].transport` | `dumbpipe`. The Tailcat adapter is not built yet. |
| `[connect].studio_port` | `8765`. The port the phone binds on its own loopback. Keep it equal to the studio's `--port`. |
| `[connect].dumbpipe_path` | Blank runs the precompiled `openimagine-pipe` in `studio/l4_frameworks_and_drivers/bin`. Set a path to use another build. |
| `[connect].identity_path` | `~/.config/open-imagine/dumbpipe-identity`. The stable dumbpipe identity, created with mode 0600. |
| Image backend `quantize` | Weight quantization; 0 is the default. |
| Image backend `model_dir` / `lora_path` | Local weights or adapter path, where supported. |
| Image backend `rewrite_generate_model`, `rewrite_edit_model`, `rewrite_quantize` | Prompt rewriter for each mode, and its load-time quantization. 0, the default, keeps full precision; 2, 3, 4, 5, 6 and 8 are the widths MLX offers, and any other value stops the studio at start. The shipped `studio.toml` sets 8. |
| `[minimax_h3_image].rewrite_model_dir`, `rewrite_prompt_dir` | The model's own 27B prompt enhancer, as a converted MLX pack, and its prompt templates, which default to `<pack>/prompt`. Without the pack the page offers no Rewrite toggle. The setup recipe is in [Set up models](../how-to/set-up-models.md#optional-the-models-own-prompt-enhancer). |
| Image backend `rewrite_generate_local`, `rewrite_edit_local` | A converted rewriter checkpoint on disk, such as a 4-bit MLX directory. When the directory exists it is used instead of the repo id, and its own quantization is kept. When it does not, the repo id above is downloaded and quantized at load, so a fresh machine needs no conversion. |
| `[mlx_video].cli_path`, `ffmpeg_path` | Optional Video engine executable, and the media tool. Empty `cli_path` runs the wrapper the studio ships with `uv run --script`. The prompt enhancer ignores `cli_path` and runs its own `uv` script. |
| `[mlx_video].model_ltx25`, `model_ltx23` | Video pack identifiers. |
| `[mlx_video].lora_dir`, `fetch_loras` | Effect adapter directory and opt-in download policy. |
| `[mlx_video].batch_policy` | `auto`, `enhance_only`, or `sequential`. |
| Backend `max_loras`, `[[<backend>.loras]]` | The LoRAs a model offers. See [LoRAs](#loras). |
| LTX pack plugin `pack_dir` | The folder of the pack's weights. See [LTX packs](model-plugins.md#ltx-packs). |
| Qwen checkpoint plugin `model_dir` | The folder of the checkpoint's weights. See [Qwen checkpoints](model-plugins.md#qwen-checkpoints). |
| `[auk].child_script` | AuK child implementation. |
| `[drama3].child_script`, `python_path` | Drama-3 child and optional prebuilt environment. |

A workspace shows its model selector only when more than one model is offered.
Selecting a model does not load it. Paths relative to the configuration file resolve from that file.

Voice implementation modules live under `gateways/voice`. If an older copied configuration
sets `child_script` to the former `audio` location, update it to the path in the shipped
`studio.toml`, or remove that override to use the built-in default. Custom scripts outside
the checkout keep their configured paths.

## LoRAs

A built-in model can offer your own LoRA files. Add one `[[<backend>.loras]]` table for
each file under the model's section. These models take them:

| Section | Engine | Modes |
|---|---|---|
| `qwen21`, `qwen21_turbo`, `viggle_turbo` | mflux | Generate and Edit; `modes` limits a LoRA to some of them |
| `ltx25_mlx` | ltx-2-mlx | Generate and Edit, but not with an audio track |
| `ltx23_mlx` | ltx-2-mlx | Generate, but not with an audio track |
| An LTX pack plugin | ltx-2-mlx | As its family, `ltx25_mlx` or `ltx23_mlx` |
| A Qwen checkpoint plugin | mflux | Generate and Edit; `modes` limits a LoRA to some of them |
| `minimax_h3`, the [MiniMax H3](../../studio/l3_interface_adapters/gateways/video/minimax_h3/README.md#loras) | Phosphene's staged H3 runner | Generate, but not with an audio track. The memory gate takes one LoRA per clip |

`flux2`, `krea2` and `minimax_h3_image` take no LoRAs, and a table under any of them stops the studio at start.

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

## Music

`default_music_backend = "yue2"` and `visible_music_backends = ["yue2"]` select the
independent Music catalog. YuE2 uses native Apple Silicon MLX Q8 exclusively.
`[yue2]` takes `model_dir`, a separate `vae_dir`, and `transcription_cache_dir` for the
pinned transcription weights and the instrumental helpers. The worker always runs as a
uv script with its own pinned environment, so `python_path` is rejected. `engine` may be
omitted or set to `mlx-q8`; legacy engine values are rejected. The default runtime environment and weight setup are in
[Music setup](../how-to/music.md).
Startup loads no Music weights; generation uses installed local checkpoints only.
See [Music setup](../how-to/music.md) for the default download recipe and input controls.

## Memory policy

The Settings menu's Memory section applies to every workspace and API caller.
“Require a measured memory estimate” is off by default, so a setup with no measured
peak may run. Turn it on to refuse an unmeasured setup with 503 and instructions
for changing the setting; that is not a claim that a workflow is unsupported.
Known estimates continue to enforce the model peak plus the macOS reserve in either mode.
When the model is loaded already, the check subtracts its declared `resident_gib` from
the peak, so a second run does not pay for the weights twice.
The current measurements apply to a 64 GiB Mac; other hosts have no calibrated
estimate. Smaller output alone
does not create an estimate for an unmeasured workflow.

Changes take effect on the next admission check and do not stop a running operation.
Saved preferences take precedence over `require_memory_estimate` in TOML; remove
the preferences file to return to the configured default.

## Phone connection

Phone connections start by default. The dumbpipe listener binds `127.0.0.1:studio_port`
and prints a QR code after the server binds. `--connect=off` disables it for one start.
Set `[connect] enabled = false` to keep it off. `--connect` or `--connect=on` overrides that setting.
The QR carries the ticket and the loopback
port. The phone runs `dumbpipe connect-tcp` and opens `http://127.0.0.1:<port>` in
its embedded browser.

The ticket is a credential. Anyone who scans it reaches the studio, including its
model settings and public operations. Rotate the identity file and restart to revoke
it. The file is created with mode 0600 and is never logged. The listener binds
loopback only; nothing is exposed on the local network.

The terminal prints the pairing QR once the listener runs. The page's **Phone** button
shows the same QR, and **New code** rotates the identity and restarts the listener, so
every phone that held the old ticket stops working. The app stores the ticket from the
QR and keeps it. The ticket stays the same across a restart while the identity file
stays. The studio exits at startup when the connection is enabled but the transport
cannot start, instead of leaving the feature on and broken. The Tailcat adapter is not
built yet; the transport port exists so it can be added without changing the app.
