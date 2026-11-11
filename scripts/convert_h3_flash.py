#!/usr/bin/env python3
"""Convert the HyperFlow H3 Flash transformer (diffusers layout) to the MLX engine layout, Q8.

The source has three kinds of block linears: dense, low-rank (`down` / `up`) and INT8 with a
Hadamard rotation of the input (`qweight` / `wscale`). This script makes each one dense, maps it
to the engine names, and quantizes it with the recipe that `load_dit` replays (8 bit, group 64).
It holds one layer in memory at a time and computes on the CPU stream.

    python -I convert_h3_flash.py --engine <engine dir> --src <fl2va_int8_convrot> --out <pack dir> \
        [--base <pruned bf16 H3 file>]

`--base` compares four layers of block 0 with the base model. A wrong rotation, a wrong QKV
order or a wrong half swap gives a cosine near zero.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

GROUP, BITS = 64, 8
MAX_SHARD = 5 * 1024**3
TOP = {
    "proj_in": "video_patch_proj",
    "audio_proj_in": "audio_patch_proj",
    "context_embedder": "condition_proj",
    "time_embedder.linear_1": "time_embedder.proj_in",
    "time_embedder.linear_2": "time_embedder.proj_out",
    "endpoint_time_embedder.linear_1": "endpoint_time_embedder.proj_in",
    "endpoint_time_embedder.linear_2": "endpoint_time_embedder.proj_out",
    "norm_out.norm": "final_layer.norm",
    "norm_out.linear": "final_layer.adaln_proj.linear",
    "proj_out": "final_layer.video_out",
    "audio_proj_out": "final_layer.audio_out",
    "token_refiner.final_norm": "token_refiner.final_norm",
}
FP32 = (
    "video_patch_proj.",
    "audio_patch_proj.",
    "time_embedder.",
    "endpoint_time_embedder.",
    "final_layer.video_out.",
    "final_layer.audio_out.",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", type=Path, required=True)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--base", type=Path)
    a = ap.parse_args()
    sys.path.insert(0, str(a.engine))

    import mlx.core as mx
    import numpy as np
    from minimax_h3_mlx.config import DiTConfig
    from minimax_h3_mlx.dit import MiniMaxH3DiT
    from minimax_h3_mlx.quantize import QuantConfig, apply_quantization_structure
    from mlx.utils import tree_flatten

    t0 = time.time()
    raw = json.loads((a.src / "config.json").read_text())
    dropped = sorted(int(i) for i in raw["dropped_blocks"])
    quant = raw["quantization"]
    if quant["method"] != "int8_convrot":
        raise SystemExit(f"unknown quantization {quant['method']}")
    rot_group = int(quant["group"])
    heads, head_dim, ffn = raw["num_attention_heads"], raw["attention_head_dim"], raw["ffn_dim"]
    cfg = DiTConfig(
        hidden_size=raw["hidden_size"],
        num_layers=raw["num_layers"],
        token_refiner_num_layers=raw["num_refiner_layers"],
        num_attention_heads=heads,
        attention_head_dim=head_dim,
        ffn_hidden_size=ffn,
        latents_dim=raw["in_channels"],
        audio_latents_dim=raw["audio_in_channels"],
        patch_size=tuple(raw["patch_size"]),
        text_dim=raw["text_dim"],
        timestep_input_dim=raw["freq_dim"],
        time_embed_hidden_size=raw["time_embed_hidden_dim"],
        time_embed_dim=raw["time_embed_dim"],
        rope_inv_freq_len=raw["rope_freq_dim"],
        rope_theta=raw["rope_theta"],
        norm_eps=raw["norm_eps"],
        qk_norm_eps=raw["qk_norm_eps"],
        final_norm_eps=raw["final_norm_eps"],
        adaln_curve_grid=None,
    )
    qc = QuantConfig(bits=BITS, group_size=GROUP, quantize_adaln=False)
    model = MiniMaxH3DiT(cfg)
    apply_quantization_structure(model, qc)
    expected = {k: tuple(v.shape) for k, v in tree_flatten(model.parameters())}
    del model

    index = json.loads((a.src / "diffusion_pytorch_model.safetensors.index.json").read_text())
    shards = {name: mx.load(str(a.src / name)) for name in sorted(set(index["weight_map"].values()))}
    src = {key: shards[name][key] for key, name in index["weight_map"].items()}
    print(f"{len(src)} source tensors in {len(shards)} shards", flush=True)

    h4 = np.array([[1, 1, 1, -1], [1, 1, -1, 1], [1, -1, 1, 1], [-1, 1, 1, 1]], np.float64) / 2
    had = np.ones((1, 1))
    while had.shape[0] < rot_group:
        had = np.kron(had, h4)
    if had.shape[0] != rot_group or not np.allclose(had @ had.T, np.eye(rot_group)):
        raise SystemExit("the Hadamard rotation is not orthonormal")
    rotation = mx.array(had.astype(np.float32))
    used: set[str] = set()

    def take(key: str):
        used.add(key)
        return src[key]

    def dense(name: str):
        """The float32 weight of one bias-free linear, whatever its stored form."""
        if f"{name}.weight" in src:
            return take(f"{name}.weight").astype(mx.float32)
        if f"{name}.qweight" in src:
            q = take(f"{name}.qweight").astype(mx.float32)
            scale = take(f"{name}.wscale").astype(mx.float32)
            rows, cols = q.shape
            rotated = (q * scale[:, None]).reshape(rows, cols // rot_group, rot_group)
            # qweight holds W R. R is orthonormal and symmetric, so W = (W R) R.
            return (rotated @ rotation).reshape(rows, cols)
        up = take(f"{name}.up.weight").astype(mx.float32)
        down = take(f"{name}.down.weight").astype(mx.float32)
        return up @ down

    def block_linears(source: str):
        attn = f"{source}.attn"
        q, k, v = (dense(f"{attn}.{part}") for part in ("to_q", "to_k", "to_v"))
        cols = q.shape[1]
        # The engine keeps QKV rows per head: [h0: q, k, v][h1: q, k, v]...
        fused = mx.stack([m.reshape(heads, head_dim, cols) for m in (q, k, v)], axis=1)
        yield "attn.qkv_proj", fused.reshape(3 * heads * head_dim, cols)
        del q, k, v, fused
        yield "attn.out_proj", dense(f"{attn}.to_out.0")
        proj = dense(f"{source}.ff.net.0.proj")
        # diffusers holds [value; gate]. The engine holds [gate; value].
        yield "mlp.fc1", mx.concatenate([proj[ffn:], proj[:ffn]], axis=0)
        del proj
        yield "mlp.fc2", dense(f"{source}.ff.net.2")

    def plain(source: str, target: str):
        """Norms, biases and unquantized linears: copy at the engine's precision."""
        for suffix in ("weight", "bias"):
            if f"{source}.{suffix}" in src:
                tensor = take(f"{source}.{suffix}")
                key = f"{target}.{suffix}"
                yield key, tensor.astype(mx.float32 if key.startswith(FP32) else mx.bfloat16)

    def units():
        for source, target in TOP.items():
            yield from ((key, tensor, False) for key, tensor in plain(source, target))
        stacks = [
            ("token_refiner.refiner_blocks", "token_refiner.blocks", raw["num_refiner_layers"], ()),
            ("transformer_blocks", "blocks", raw["num_layers"], dropped),
        ]
        for source_stack, target_stack, count, skip in stacks:
            for i in range(count):
                if i in skip:
                    continue
                s, t = f"{source_stack}.{i}", f"{target_stack}.{i}"
                for a_name, b_name in (
                    ("norm1", "norm1"),
                    ("norm2", "norm2"),
                    ("attn.norm_q", "attn.q_norm"),
                    ("attn.norm_k", "attn.k_norm"),
                    ("adaln_proj.linear", "adaln_proj.linear"),
                ):
                    yield from ((key, tensor, False) for key, tensor in plain(f"{s}.{a_name}", f"{t}.{b_name}"))
                for name, weight in block_linears(s):
                    yield f"{t}.{name}", weight, True
                print(f"  {t} done ({time.time() - t0:.0f}s)", flush=True)

    base = mx.load(str(a.base)) if a.base else None
    a.out.mkdir(parents=True, exist_ok=True)
    shard_idx, shard_bytes, shard = 1, 0, {}
    weight_map: dict[str, str] = {}
    written: dict[str, tuple] = {}
    worst = 0.0

    def flush() -> None:
        nonlocal shard_idx, shard_bytes, shard
        if not shard:
            return
        name = f"model-{shard_idx:05d}.safetensors"
        mx.save_safetensors(str(a.out / name), shard)
        weight_map.update({key: name for key in shard})
        print(f"  wrote {name} ({shard_bytes / 1e9:.2f} GB, {len(shard)} tensors)", flush=True)
        shard_idx += 1
        shard_bytes, shard = 0, {}

    with mx.stream(mx.cpu):
        for key, tensor, core in units():
            if core:
                if base is not None and key.startswith("blocks.0."):
                    ref = base[f"{key}.weight"].astype(mx.float32)
                    cosine = (tensor * ref).sum() / mx.sqrt((tensor * tensor).sum() * (ref * ref).sum())
                    print(f"  base check {key}: cosine {cosine.item():.4f}", flush=True)
                    del ref
                packed, scales, biases = mx.quantize(tensor, group_size=GROUP, bits=BITS)
                back = mx.dequantize(packed, scales, biases, group_size=GROUP, bits=BITS)
                error = (mx.sqrt(((back - tensor) ** 2).sum()) / mx.sqrt((tensor**2).sum())).item()
                worst = max(worst, error)
                add = {
                    f"{key}.weight": packed,
                    f"{key}.scales": scales.astype(mx.bfloat16),
                    f"{key}.biases": biases.astype(mx.bfloat16),
                }
                del back
            else:
                add = {key: tensor}
            mx.eval(list(add.values()))
            for name, value in add.items():
                if name.startswith("endpoint_time_embedder."):
                    twin = name.removeprefix("endpoint_")
                    if expected[twin] != tuple(value.shape):
                        raise SystemExit(f"{name}: shape {value.shape} differs from {twin}")
                elif expected.get(name) != tuple(value.shape):
                    raise SystemExit(f"{name}: shape {value.shape}, the engine wants {expected.get(name)}")
                written[name] = tuple(value.shape)
            size = sum(value.nbytes for value in add.values())
            if shard_bytes + size > MAX_SHARD and shard:
                flush()
            shard.update(add)
            shard_bytes += size
            del tensor, add
    flush()

    unused = sorted(set(src) - used)
    if unused:
        raise SystemExit(f"{len(unused)} source tensors were not used, for example {unused[:4]}")
    absent = sorted(
        key for key in expected if key not in written and not any(key.startswith(f"blocks.{i}.") for i in dropped)
    )
    if absent:
        raise SystemExit(f"{len(absent)} engine tensors have no source, for example {absent[:4]}")

    (a.out / "model.safetensors.index.json").write_text(
        json.dumps({"metadata": {"total_shards": shard_idx - 1}, "weight_map": weight_map}, indent=1)
    )
    (a.out / "config.json").write_text(json.dumps(dataclasses.asdict(cfg), indent=1))
    (a.out / "quant_config.json").write_text(
        json.dumps(
            {
                "bits": BITS,
                "group_size": GROUP,
                "quantize_adaln": False,
                "adaln_bits": None,
                "writer": "convert_h3_flash",
                "source": "hyperflow-h3-flash fl2va_int8_convrot",
            },
            indent=1,
        )
    )
    (a.out / "flash.json").write_text(
        json.dumps({"hyperflow_gate": raw["hyperflow_gate"], "dropped_blocks": dropped}, indent=1)
    )
    print(f"worst Q8 relative error {worst:.5f}", flush=True)
    print(f"DONE in {time.time() - t0:.0f}s -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
