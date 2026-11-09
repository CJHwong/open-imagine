# Test a LoRA on Qwen Turbo

A LoRA trained for Qwen-Image-2.1 can fit Turbo's transformer, but its visual behavior
still needs testing on Turbo's eight-step schedule. A matching filename or base-model
label alone does not prove compatibility.

[Danrisi's film-stills adapter](https://huggingface.co/Danrisi/filmstills_qwen2.1)
was tested through Studio's real API on 2026-11-09, using official Qwen-Image-2.1-Turbo
at bf16 on an M5 Pro with 64 GB. The model card labels the adapter `qwen-research`
and suggests strength 0.7. It is a useful loading test; at 0.7, the sampled Turbo
Generate output showed ghosting, so this is not a quality recommendation.

Download only its 80 MB adapter, pinned to the tested revision:

```sh
uv run hf download Danrisi/filmstills_qwen2.1 filmstills_qwen21.safetensors \
  --revision 29242138fcc2eea95970fe7b66e6e17c4bb373a8 \
  --local-dir ~/Library/Caches/models/qwen-filmstills-lora
```

Add this table to a copy of your `studio.toml`, then start Studio with `--config`:

```toml
[[qwen21_turbo.loras]]
id = "film_stills"
label = "Film stills"
path = "~/Library/Caches/models/qwen-filmstills-lora/filmstills_qwen21.safetensors"
strength = 0.7
recommended = [0.7, 0.7]
trigger = "film still"
```

The tested file's SHA-256 is
`ad4812903c6f6b8966885d09dff23344422d0d1f8b2bebad038f8a802f55e30a`.
Studio offers the adapter in Generate and Edit. The page's Add-ons slider starts at
zero; move it to select the adapter. API requests select it explicitly:

```json
{
  "kind": "image",
  "backend": "qwen21_turbo",
  "mode": "generate",
  "prompt": "film still, a blue bicycle outside a corner cafe at dusk",
  "size": "512x512",
  "seed": 7,
  "loras": [{"id": "film_stills", "strength": 0.7}]
}
```

The real check confirmed all 384 tensor keys applied to 224 layers, with no unmatched
keys. Generate and Edit completed and recorded the selected strength. A two-item
Generate batch completed with the same adapter. With identical prompt, seed and size,
disabling the adapter reproduced the original pixels exactly. Both Generate and Edit
outputs differed when the adapter was enabled; the Generate difference was much larger.

Memory admission rejected one retry while the previous model was resident. Releasing
model memory and retrying succeeded. These checks prove loading, selection, output
metadata, batch handling and disabling. They do not certify every strength, prompt,
resolution or model-family adapter.
