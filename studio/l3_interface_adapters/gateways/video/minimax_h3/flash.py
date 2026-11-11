"""Run a converted HyperFlow H3 Flash pack on the pinned H3 engine.

Flash is H3 with a second time input. Each step tells the transformer the time it is at, `t`,
and the time it steps to, `r`. The engine tree stays as it is: the worker loads this file by
path and `install` changes two functions of the loaded engine module in memory.

1. `load_dit` adds the endpoint time embedder, the gate and the dropped blocks of the pack.
2. `row_timestep_plan` gives every row a `(t, r)` pair in place of one time.

The schedule is the model's own grid of six steps. As on base H3, a step is one evaluation.
"""

import json
from pathlib import Path

# The raw sigma grid of the six-step schedule, from `schedule.py` of the model's inference code:
# github.com/Video-Rebirth/hyperflow-h3-flash at 703747ee414f895985a4c3b87e59f4fd03fc9f14. The
# engine shifts it by 12 for video and by 3 for audio, as that code does and as base H3 does.
SIGMAS = (1.0, 0.825217, 0.471725, 0.147401, 0.049626, 0.015517, 0.0)
ENDPOINT = "endpoint_time_embedder."


def schedule_flags():
    """The engine flags of the Flash schedule. The engine takes its knots as thousandths."""
    knots = ",".join(f"{value * 1000:.6f}".rstrip("0").rstrip(".") for value in SIGMAS)
    return ["--sigma-knots", knots, "--sampler", "euler"]


def install(engine):
    """Change the loaded engine module to run Flash, and return the schedule's flags."""
    import mlx.core as mx
    import numpy as np
    from minimax_h3_mlx.dit import TimestepEmbedder, timestep_embedding
    from minimax_h3_mlx.packing import KEYFRAME_NOISE_AUG, build_row_timesteps
    from mlx.utils import tree_flatten, tree_unflatten

    load_dit = engine.load_dit

    def load_flash(model_dir, verbose=False, **_ignored):
        model_dir = Path(model_dir)
        meta = json.loads((model_dir / "flash.json").read_text())
        # The dropped blocks have no weights, so the strict key check cannot pass.
        dit = load_dit(model_dir, strict=False, verbose=verbose)
        index = json.loads((model_dir / "model.safetensors.index.json").read_text())["weight_map"]
        dropped = tuple(f"blocks.{int(block)}." for block in meta["dropped_blocks"])
        # That load checked no key. A pack with another hole would render noise without an error.
        wanted = {key for key, _ in tree_flatten(dit.parameters())}
        if any(not key.startswith(dropped) for key in wanted - index.keys()) or any(
            not key.startswith(ENDPOINT) for key in index.keys() - wanted
        ):
            raise RuntimeError("The Flash pack does not match the engine's transformer.")
        shards = sorted({shard for key, shard in index.items() if key.startswith(ENDPOINT)})
        weights = [
            (key.removeprefix(ENDPOINT), value.astype(mx.float32))
            for shard in shards
            for key, value in mx.load(str(model_dir / shard)).items()
            if key.startswith(ENDPOINT)
        ]
        if len(weights) != 4:
            raise RuntimeError("The Flash pack does not hold its four endpoint tensors.")
        endpoint = TimestepEmbedder(dit.config)
        endpoint.update(tree_unflatten(weights))
        mx.eval(endpoint.parameters())
        gate = float(meta["hyperflow_gate"])
        dim = dit.config.timestep_input_dim

        class FlashDiT(type(dit)):
            def embed_timesteps(self, pairs):
                if pairs.ndim != 2 or pairs.shape[-1] != 2:
                    raise ValueError("Flash needs one (t, r) pair for each time.")
                current = self.time_embedder(timestep_embedding(pairs[:, 0], dim))
                # Not a child module: the engine walks the tree for LoRA and memory accounting.
                target = endpoint(timestep_embedding(pairs[:, 1], dim))
                return current + gate * (target - current)

        dit.__class__ = FlashDiT
        dit.skip_blocks = frozenset(int(block) for block in meta["dropped_blocks"])
        return dit

    def flash_plan(layout, video_timesteps, audio_timesteps, frozen_video=None, frozen_audio=None):
        video_t, audio_t = video_timesteps.tolist(), audio_timesteps.tolist()
        # The endpoint of a step is the time of the next one. The last step ends clean.
        video_r, audio_r = [*video_t[1:], 1.0], [*audio_t[1:], 1.0]
        per_step = []
        for vt, at, vr, ar in zip(video_t, audio_t, video_r, audio_r, strict=True):
            # A keyframe row and a clean row go nowhere, so both calls give them the same value.
            pinned = (
                max(float(vt), KEYFRAME_NOISE_AUG),
                1.0,
                frozen_video,
                frozen_audio,
                engine.FROZEN_VIDEO_TIMESTEP,
            )
            columns = []
            for video, audio in ((vt, at), (vr, ar)):
                distinct, inverse = build_row_timesteps(layout, float(video), float(audio), *pinned)
                columns.append(np.array(distinct)[np.array(inverse)])
            per_step.append(np.unique(np.stack(columns, axis=1), axis=0, return_inverse=True))
        table = np.unique(np.concatenate([pairs for pairs, _ in per_step]), axis=0)
        lookup = {tuple(pair): index for index, pair in enumerate(table.tolist())}
        plan = []
        for pairs, inverse in per_step:
            remap = np.array([lookup[tuple(pair)] for pair in pairs.tolist()], dtype=np.int32)
            plan.append(mx.array(remap[np.asarray(inverse).reshape(-1)]))
        return mx.array(table.astype(np.float32)), plan

    engine.load_dit = load_flash
    engine.row_timestep_plan = flash_plan
    return schedule_flags()
