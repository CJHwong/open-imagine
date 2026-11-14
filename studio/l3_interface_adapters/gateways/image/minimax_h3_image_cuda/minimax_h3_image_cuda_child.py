#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "diffusers==0.43.0",
#   "transformers>=5.23.0",
#   "accelerate>=1.0",
#   "torchvision",
#   "torchao==0.18.0",
#   "mslk==1.4.0",
#   "huggingface-hub>=1.0",
#   "pillow",
#   "numpy",
#   "safetensors",
#   "sentencepiece",
#   "protobuf",
# ]
# [tool.uv]
# index-strategy = "unsafe-best-match"
# extra-index-url = ["https://download.pytorch.org/whl/cu130"]
# ///
"""MiniMax H3-Image on a CUDA GPU, one JSON job per line.

The checkpoint is 68.7 GB of transformer and 66.7 GB of text encoder in bfloat16, which is
more than a 128 GB unified machine holds once the runtime and the VAE join. The text
encoder therefore loads in FP8 and the transformer is quantized to NVFP4 after it lands,
which brings the pair to about 50 GB. Peak during the quantize is the bf16 transformer plus
the packed copy, so the order is encoder first, transformer second, quantize third.
"""

import argparse
import base64
import io
import json
import sys
import time


def say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def answer(document: dict) -> None:
    print(json.dumps(document), flush=True)


def materialize(module) -> None:
    """Copy mmap-backed weights into ordinary memory, keeping shared tensors shared.

    Measured on the DGX Spark: safetensors' mmap-backed tensors move to the device at
    128 MB/s and the same tensors from ordinary memory at 14 GiB/s.
    """
    clones: dict[int, object] = {}
    for tensor in [*module.parameters(), *module.buffers()]:
        key = tensor.data.data_ptr()
        if key not in clones:
            clones[key] = tensor.data.clone()
        tensor.data = clones[key]


def component(pipe, name: str):
    """A modular pipeline exposes its loaded parts as attributes and as a mapping."""
    found = getattr(pipe, name, None)
    if found is None:
        found = pipe.components[name]
    return found


def supports(pipeline, keyword: str) -> bool:
    import inspect

    try:
        return keyword in inspect.signature(pipeline.__call__).parameters
    except (TypeError, ValueError):
        return False


def move_by_way_of_memory(module, device: str) -> None:
    """Send each weight through ordinary memory before it lands on the device.

    A safetensors tensor is a file-backed mapping. On this machine, measured 2026-11-14 on
    one 4.64 GB transformer shard: the mapping to the device ran at 0.19 GB/s, the mapping
    into ordinary memory at 8.35 GB/s, and ordinary memory to the device at 59.57 GB/s.

    One group of aliased weights is cloned, moved, then dropped, so the temporary is one
    tensor rather than the whole model. Cloning the whole 62 GiB transformer is what died
    with CUDA_ERROR_OUT_OF_MEMORY at 110 GiB resident; this order avoids that and keeps the
    aliasing that a per-parameter copy would break.
    """
    groups: dict[int, list] = {}
    for tensor in [*module.parameters(), *module.buffers()]:
        groups.setdefault(tensor.data.data_ptr(), []).append(tensor)
    for tensors in groups.values():
        landed = tensors[0].data.clone().to(device)
        for tensor in tensors:
            tensor.data = landed


def load(model: str, quantize: str):
    import torch
    from diffusers import ModularPipeline

    if quantize not in ("nvfp4", "fp8", "bf16"):
        raise SystemExit(f"quantize must be nvfp4, fp8 or bf16, not {quantize}")
    started = time.time()
    pipe = ModularPipeline.from_pretrained(model)
    say("loaded the pipeline shell")
    if quantize == "bf16":
        pipe.load_components(dtype=torch.bfloat16, device_map="cuda")
        return pipe

    # The encoder first, alone, then quantized, then the transformer. Loading both at
    # bf16 needs 135 GB and this machine has 121.7. Torchao weight-only NVFP4 is used for
    # the encoder because it runs once per prompt and accuracy matters more than speed
    # there; the transformer takes W4A4, which is where the time is spent.
    from torchao.prototype.mx_formats import NVFP4WeightOnlyConfig
    from torchao.quantization import quantize_

    pipe.load_components(names=["text_encoder"], dtype=torch.bfloat16, device_map="cpu")
    say(f"encoder loaded in {time.time() - started:.1f}s")
    quantize_(component(pipe, "text_encoder"), NVFP4WeightOnlyConfig())
    torch.cuda.empty_cache()
    say(f"encoder packed in {time.time() - started:.1f}s")
    # The weights land on the host first and then travel one tensor at a time, because the
    # straight mapping to the device moves at 0.19 GB/s. Loading both components to the
    # device at bf16 needs 135 GB against this machine's 121.7, so the encoder above is
    # already packed before the transformer arrives.
    pipe.load_components(
        names=["transformer", "vae", "processor", "tokenizer", "scheduler"], dtype=torch.bfloat16, device_map="cpu"
    )
    move_by_way_of_memory(component(pipe, "transformer"), "cuda")
    move_by_way_of_memory(component(pipe, "vae"), "cuda")
    torch.cuda.synchronize()
    say(f"transformer on the device in {time.time() - started:.1f}s")
    if quantize == "nvfp4":
        from torchao.prototype.mx_formats import NVFP4DynamicActivationNVFP4WeightConfig

        quantize_(component(pipe, "transformer"), NVFP4DynamicActivationNVFP4WeightConfig())
    else:
        from torchao.quantization import Float8WeightOnlyConfig

        quantize_(component(pipe, "transformer"), Float8WeightOnlyConfig())
    component(pipe, "text_encoder").to("cuda")
    torch.cuda.synchronize()
    say(f"loaded {model} as {quantize} in {time.time() - started:.1f}s")
    return pipe


def run(pipe, job: dict) -> dict:
    import torch

    steps = int(job["steps"])
    total = steps
    seen = {"count": 0}

    def on_step(_pipe, index, _timestep, callback_kwargs):
        seen["count"] = index + 1
        say(f"step {seen['count']}/{total}")
        return callback_kwargs

    arguments = {
        "prompt": job["prompt"],
        "height": int(job["height"]),
        "width": int(job["width"]),
        "generator": torch.Generator().manual_seed(int(job["seed"])),
        "output": "images",
    }
    if supports(pipe, "callback_on_step_end"):
        arguments["callback_on_step_end"] = on_step
    output = pipe(**arguments)
    image = output[0] if isinstance(output, list) else output.images[0]
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return {
        "png_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "width": image.width,
        "height": image.height,
        "steps": seen["count"] or total,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="MiniMaxAI/MiniMax-H3-Image")
    parser.add_argument("--quantize", default="nvfp4", choices=["nvfp4", "fp8", "bf16"])
    arguments = parser.parse_args()
    import torch

    if not torch.cuda.is_available():
        say("CUDA is not available in this environment")
        return 2
    pipe = load(arguments.model, arguments.quantize)
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
