# Local Studio API

Discover `GET /api/docs` and its OpenAPI link, then `GET /api/v1/studio` and `/api/v1/state`. Inspect the actual backend with `/api/v1/{images|videos|voice}/backends/{id}`. Modes and installed models can differ by server; a documentation example is not proof that its model is available.

Prefer asynchronous operations when offered. Only one generation operation owns this Studio's model memory; there is no queue on a conflict. Ordered batches are useful, but choose batch size according to the preview/review stage. Save exact requests separately, including the real supplied references. Inspect the current operation schema and result types rather than assuming image JSON, binary WAV, and binary MP4 use the same parser.

An acceptance response may have a null `result_url`. Refresh the operation and use its latest non-null URL. A finished sampler may still be decoding or saving. Fetch completed batch items as they become available and after cancellation/failure; preserve them locally. Server results expire and a restart clears them.

## Owned production runner

`scripts/production_runner.py` owns a server on its own port inside an exclusive
GPU slot. It never borrows an existing server. Point it at the Studio checkout with
`--repo`, or set `STUDIO_REPO`; without either, it uses the current directory when that
holds `studio.toml`. A queue is a list of single-result
jobs with `name`, `request`, `out`, `allowance_seconds`, and optional
`references: [{path, ...API reference fields}]`. All media paths are project-local.
Discovery starts no model job. The normal slot limit is thirty minutes.

The runner checks `execution_constraints.gpu_allowed` and `generation_hold` in
the project before taking a token or starting a server. `gpu_allowed: false`
permits CPU preparation only; both `run` and owned-server `discover` refuse.
The direct job helper checks the same instruction. CPU export registration
remains available. Only a new producer instruction can lift the restriction.

```bash
uv run python <skill-dir>/scripts/production_runner.py /abs/project.json discover
uv run python <skill-dir>/scripts/production_runner.py /abs/project.json run queues/images.json --minutes 15
uv run python <skill-dir>/scripts/production_runner.py /abs/project.json export exports/animatic.mp4 --label "Timed storyboard" --kind animatic
```

Each attempt keeps its request, reference snapshots, client ID, accepted operation,
terminal status and completion hash beside its output. An uncertain POST or partial
download is preserved for recovery, never submitted again automatically. A new
attempt needs a new output path. Valid completed media is checked before resuming.
The export command registers the named file first and rebuilds the shared page;
it does not reconstruct shots or alter their approval hashes.

Video jobs additionally name `shot`. Their request and reference specifications
must exactly match one of that shot's `staging.submission_specs` entries (or its
single `staging.submission_spec`). These fields are covered by the existing shot
approval hash. List intended seed choices before review. Each entry has the shape
`{request: {...}, references: [{path, frame_index: 0, strength: 1}]}`. The runner
checks the real gate immediately before each POST, including direct helper calls.
It requires `settings.video_attempt_limit` and `settings.video_attempts_per_shot`;
uncertain submitted requests count toward the ceiling. Inline media and multi-result
batches are refused. The runner does not queue audio-conditioned jobs; for a
singing clip, submit the `audio` field through the API directly, as
[quick-clip.md](quick-clip.md) shows. Driving-clip transport is not implemented in
this runner yet. Keep both out of its queues.

Video frame counts can follow a grid such as `frames % 8 == 1`; conform the edit to the intended duration. Some backends rewrite prompts even when asked not to, so save the enhanced prompt with the take.

For LTX prompt writing, consult the [official guide](https://ltx.io/blog/ltx-2-5-prompt-guide) and the [LTX-2.5 agent prompt skill](https://github.com/benjiyaya/LTX-2.5-Agent-Prompt-Skill) when relevant. Single-shot I2V should emphasize motion after the supplied first frame, one dominant action, concrete physical cues, camera behavior, and sound. Exact UI lettering and captions belong in post when spelling matters. Do not copy upstream training/ComfyUI flags into the Studio request or assume features such as duration prediction, adapters, or upscalers are exposed locally.

For endpoint/intermediate-frame references and motion-onset defects, read [motion-control.md](motion-control.md). A saved OpenAPI snapshot described `references[].frame_index` and `strength`; verify current backend semantics and accepted indices before execution. Multi-image identity references, timed keyframes and driving-video adapters serve different purposes. Do not infer one from another or assume a documented ComfyUI feature is exposed locally.
