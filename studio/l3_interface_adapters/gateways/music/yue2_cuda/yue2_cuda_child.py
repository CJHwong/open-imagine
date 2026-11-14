#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "yue2-infer @ git+https://github.com/multimodal-art-projection/YuE@1116bea76032bee5668e5f097294d082fa0b84f0",
#   "torch==2.15.0",
#   "torchao==0.18.0",
#   "mslk==1.4.0",
#   "soundfile",
#   "numpy",
# ]
# [tool.uv]
# index-strategy = "unsafe-best-match"
# extra-index-url = ["https://download.pytorch.org/whl/cu130"]
# override-dependencies = ["torch==2.15.0"]
# ///
"""YuE2 on a CUDA GPU, one JSON job per line.

The upstream package, `yue2-infer`, is the whole engine: it plans, generates, synthesizes
and decodes, and its own pins keep torch, transformers and huggingface-hub consistent.
This child only maps a studio job onto its request and its artifacts back onto the
studio's reply.

The header moves torch from the engine's 2.10.0 to 2.15.0, which needs
`override-dependencies` because `yue2-infer` pins the exact version. Without the move,
`mslk` 1.4.0 will not load, and the nvfp4 path needs the Triton kernels in it: torchao's
fp4 matmul takes both operands in fp4, so the activations must be quantized by that
kernel. Measured on the DGX Spark on 2026-11-14: nvfp4 W4A4 sang 3.2x faster than bf16
in the same environment, where weight-only nvfp4 without those kernels ran 19.5x slower.
"""

import argparse
import base64
import io
import json
import sys
import time
from pathlib import Path


def say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def answer(document: dict) -> None:
    print(json.dumps(document), flush=True)


def request_for(job: dict) -> dict:
    """The studio's job as YuE2's request. The style carries the instrumental marker."""
    style = job["style"]
    if job.get("instrumental") and not style.lower().startswith("instrumental"):
        style = "Instrumental, " + style
    request = {
        "style": style,
        "lyrics": job.get("lyrics", ""),
        "cot": job.get("cot", "full"),
        "seed": int(job["seed"]),
    }
    score = (job.get("abc") or "").strip()
    if score:
        request["abc"] = score
    return request


QUANTIZERS = {"bf16", "fp8", "nvfp4"}
"""`bf16` is unquantized, `fp8` is the engine's own FP8 arithmetic for the lyric stages,
and `nvfp4` is torchao's fp4 weights with fp4 activations, served from a pack."""

ENGINE_QUANTIZATION = {"bf16": "none", "fp8": "fp8"}
PACK_FORMAT = 1


def versions() -> dict:
    """The versions a pack depends on. A pack built by another set is not reused."""
    import mslk
    import torch
    import torchao

    return {
        "torch": torch.__version__,
        "torchao": torchao.__version__,
        "mslk": getattr(mslk, "__version__", "unknown"),
    }


def quantize_ar(module) -> None:
    """Put the lyrics stages in fp4, weights and activations, so the matmul runs on fp4."""
    from torchao.prototype.mx_formats import NVFP4DynamicActivationNVFP4WeightConfig
    from torchao.quantization import quantize_

    quantize_(module, NVFP4DynamicActivationNVFP4WeightConfig())


def packed_layers(model) -> list[str]:
    import torch
    from torchao.prototype.mx_formats.nvfp4_tensor import NVFP4Tensor

    return [
        name
        for name, module in model.named_modules()
        if isinstance(module, torch.nn.Linear) and isinstance(module.weight, NVFP4Tensor)
    ]


def expected_manifest(model_name: str) -> dict:
    """Every field of a pack that must match before it is trusted."""
    from torchao.prototype.mx_formats.inference_workflow import (
        NVFP4DynamicActivationNVFP4WeightConfig,
    )

    config = NVFP4DynamicActivationNVFP4WeightConfig()
    return {
        "format": PACK_FORMAT,
        "model": model_name,
        "versions": versions(),
        "block_size": 16,
        "orig_dtype": "torch.bfloat16",
        "is_swizzled_scales": True,
        "use_triton_kernel": config.use_triton_kernel,
        "act_quant": {
            "block_size": 16,
            "is_swizzled_scales": True,
            "use_triton_kernel": config.use_triton_kernel,
            "use_dynamic_per_tensor_scale": config.use_dynamic_per_tensor_scale,
        },
    }


def manifest_matches(manifest: dict, expected: dict) -> bool:
    return all(manifest.get(key) == value for key, value in expected.items())


def pack_path(root: Path, model_name: str) -> Path:
    return Path(root) / model_name.replace("/", "--")


def read_manifest(directory: Path) -> dict | None:
    path = directory / "pack.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_pack(model, directory, manifest: dict) -> None:
    """The packed tensors as they sit, so a later start skips the quantization pass."""
    from safetensors.torch import save_file

    tensors = {}
    has_scale = True
    for name in manifest["layers"]:
        weight = model.get_submodule(name).weight
        tensors[f"{name}.qdata"] = weight.qdata.detach().clone().contiguous()
        tensors[f"{name}.scale"] = weight.scale.detach().clone().contiguous()
        if weight.per_tensor_scale is None:
            has_scale = False
        else:
            tensors[f"{name}.per_tensor_scale"] = (
                weight.per_tensor_scale.detach().clone().float().reshape(1).contiguous()
            )
    manifest = {**manifest, "has_per_tensor_scale": has_scale}
    directory.mkdir(parents=True, exist_ok=True)
    save_file(tensors, str(directory / "weights.safetensors"))
    (directory / "pack.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def empty_model(model_dir) -> "object":
    """The model's shapes and no weights, so a start never reads the bf16 checkpoints."""
    from accelerate import init_empty_weights
    from yue2.modeling_yue2 import YuE2Config, YuE2ForCausalLM

    with init_empty_weights():
        return YuE2ForCausalLM(YuE2Config.from_pretrained(str(model_dir)))


def load_unpacked(model, model_dir, packed: set[str]) -> int:
    """Every weight the pack does not carry, read straight from the checkpoint shards."""
    from safetensors import safe_open

    skipped = {f"{name}.weight" for name in packed}
    loaded = 0
    for shard in sorted(model_dir.glob("*.safetensors")):
        with safe_open(str(shard), framework="pt") as handle:
            # `keys()` is the documented call; a safetensors handle is not a mapping.
            wanted = {
                key: handle.get_tensor(key)
                for key in handle.keys()  # noqa: SIM118
                if key not in skipped
            }
        if wanted:
            model.load_state_dict(wanted, strict=False, assign=True)
            loaded += len(wanted)
    return loaded


def attach_pack(model, tensors: dict, manifest: dict) -> None:
    import torch
    from torchao.prototype.mx_formats.nvfp4_tensor import (
        NVFP4Tensor,
        QuantizeTensorToNVFP4Kwargs,
    )

    kwargs = QuantizeTensorToNVFP4Kwargs(**manifest["act_quant"])
    dtype = getattr(torch, manifest["orig_dtype"].removeprefix("torch."))
    for name in manifest["layers"]:
        scale = tensors.get(f"{name}.per_tensor_scale")
        model.get_submodule(name).weight = torch.nn.Parameter(
            NVFP4Tensor(
                tensors[f"{name}.qdata"],
                tensors[f"{name}.scale"],
                manifest["block_size"],
                dtype,
                scale.reshape(()) if scale is not None else None,
                None,
                manifest["is_swizzled_scales"],
                manifest["use_triton_kernel"],
                kwargs,
            ),
            requires_grad=False,
        )


def load_packed(model_name: str, root: Path):
    """The fp4 path: a pack when it matches this host, a build when it does not."""
    from safetensors.torch import load_file
    from yue2 import YuE2Pipeline

    pipe = YuE2Pipeline.from_pretrained(model_name, device="cuda")
    pipe.__enter__()
    directory = pack_path(root, model_name)
    manifest = read_manifest(directory)
    if manifest is None or not manifest_matches(manifest, expected_manifest(model_name)):
        started = time.time()
        model = pipe._load_model()
        quantize_ar(model)
        write_pack(model, directory, {**expected_manifest(model_name), "layers": packed_layers(model)})
        say(f"built the pack in {directory} in {time.time() - started:.1f}s")
        return pipe

    started = time.time()
    model = empty_model(pipe.model_dir)
    loaded = load_unpacked(model, pipe.model_dir, set(manifest["layers"]))
    attach_pack(
        model,
        {key: value.to("cuda") for key, value in load_file(str(directory / "weights.safetensors")).items()},
        manifest,
    )
    model.eval()
    pipe._model = model
    say(
        f"served {len(manifest['layers'])} packed layers and {loaded} unpacked tensors "
        f"from {directory} in {time.time() - started:.1f}s"
    )
    return pipe


def load(model: str, name: str = "bf16", root: Path | None = None):
    from yue2 import YuE2Pipeline

    if name not in QUANTIZERS:
        raise SystemExit(f"quantize must be one of {', '.join(sorted(QUANTIZERS))}, not {name}")
    if name == "nvfp4":
        if root is None:
            raise SystemExit("nvfp4 needs --pack-dir, where the packed weights are kept")
        return load_packed(model, root)
    started = time.time()
    pipe = YuE2Pipeline.from_pretrained(model, device="cuda", quantization=ENGINE_QUANTIZATION[name])
    pipe.__enter__()
    say(f"loaded {model} as {name} in {time.time() - started:.1f}s")
    return pipe


def run(pipe, job: dict) -> dict:
    """The engine's sampling overrides reach both stages, as they do on the MLX backend.

    An empty map keeps each stage's own recipe. Without this the studio's sampling
    controls are accepted and silently ignored on this engine.
    """
    sampling = job.get("sampling") or {}
    plan_sampling = {"abc_sampling": sampling} if sampling else {}
    if job.get("mode", "generate") == "plan":
        plan = pipe.plan(**request_for(job), **plan_sampling)
        return {"score": getattr(plan, "abc", "") or "", "metadata": {"mode": "plan"}}
    import soundfile

    song_sampling = {**plan_sampling, "semantic_sampling": sampling} if sampling else {}
    song = pipe(**request_for(job), **song_sampling)
    buffer = io.BytesIO()
    soundfile.write(buffer, song.audio, 48000, format="WAV", subtype="FLOAT")
    return {
        "wav": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "score": getattr(song, "abc", "") or "",
        "truncated": dict(getattr(song, "truncated", {}) or {}),
        "metadata": {"mode": "generate", "cot": job.get("cot", "full")},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="m-a-p/YuE2-3B")
    parser.add_argument("--quantize", default="bf16", choices=sorted(QUANTIZERS))
    parser.add_argument("--pack-dir", default="")
    arguments = parser.parse_args()
    import torch

    if not torch.cuda.is_available():
        say("CUDA is not available in this environment")
        return 2
    pipe = load(arguments.model, arguments.quantize, Path(arguments.pack_dir) if arguments.pack_dir else None)
    say("ready")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            answer(run(pipe, json.loads(line)))
        except Exception as error:  # the parent turns this into a failed job
            answer({"error": f"{type(error).__name__}: {error}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
