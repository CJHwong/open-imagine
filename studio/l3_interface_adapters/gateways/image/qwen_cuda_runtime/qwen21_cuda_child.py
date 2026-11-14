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
#   "hf-xet",
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
"""Qwen-Image-2.1 on a CUDA GPU, one JSON job per line.

The parent sends a job on stdin and reads one JSON answer on stdout. Progress goes
to stderr as `step N/M`, because that is the line the parent already reads. The
model loads once and stays loaded: a second load of these weights costs minutes.

The transformer runs NVFP4 W4A4 unless `--quantize bf16` is given. W4A4 is the only
4-bit path that pays: measured on the DGX Spark, 2.9x over bf16 at 512 tokens and
1.4x at 4096, with the weights 72% smaller. Weight-only NVFP4 stores four bits and
computes in bf16, which measured slower than doing nothing.
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


def local_snapshot(model: str) -> str:
    """The cached directory of a model id, so the pipeline does not ask the Hub.

    Asking the Hub costs about 3 s per start on this machine even when every file is
    cached. An id with no complete cache stays as it is, and the loader fetches it.
    """
    try:
        from huggingface_hub import snapshot_download

        return snapshot_download(model, local_files_only=True)
    except Exception:  # any failure means the loader should fetch it
        return model


def move_by_way_of_memory(module, device: str = "cuda") -> None:
    """Send each weight through ordinary memory before it lands on the device.

    Measured on the DGX Spark on 2026-11-13: moving safetensors' mmap-backed tensors
    straight to the device ran at 128 MB/s, and the same tensors moved from ordinary
    memory at 14 GiB/s. A 16 GiB shard went from 135 s to 1.3 s. One group of aliased
    weights is cloned and moved at a time and the clone is dropped as the group lands,
    so the host high-water mark is one tensor rather than the component.
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
    from diffusers import QwenImage21Pipeline

    started = time.time()
    pipe = QwenImage21Pipeline.from_pretrained(local_snapshot(model), torch_dtype=torch.bfloat16)
    if quantize not in ("nvfp4", "bf16"):
        raise SystemExit(f"quantize must be nvfp4 or bf16, not {quantize}")
    for component in (pipe.transformer, pipe.text_encoder, pipe.vae):
        move_by_way_of_memory(component, "cuda")
    # Quantize where the run computes. torchao's NVFP4 tensor is a CUDA kernel, so the
    # weights go to the GPU first and the packing happens there.
    pipe.to("cuda")
    if quantize == "nvfp4":
        from torchao.prototype.mx_formats import NVFP4DynamicActivationNVFP4WeightConfig
        from torchao.quantization import quantize_

        quantize_(pipe.transformer, NVFP4DynamicActivationNVFP4WeightConfig())
        torch.cuda.empty_cache()
    torch.cuda.synchronize()
    say(f"loaded {model} as {quantize} in {time.time() - started:.1f}s")
    return pipe


def run(pipe, job: dict) -> dict:
    import torch

    steps = int(job["steps"])
    total = steps

    def on_step(_pipe, index, _timestep, callback_kwargs):
        say(f"step {index + 1}/{total}")
        return callback_kwargs

    image = pipe(
        prompt=job["prompt"],
        negative_prompt=job.get("negative") or None,
        height=int(job["height"]),
        width=int(job["width"]),
        num_inference_steps=steps,
        true_cfg_scale=float(job.get("guidance", 1.0)),
        generator=torch.Generator("cuda").manual_seed(int(job["seed"])),
        callback_on_step_end=on_step,
    ).images[0]
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return {
        "png_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "width": image.width,
        "height": image.height,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen-Image-2.1-Turbo")
    parser.add_argument("--quantize", default="nvfp4", choices=["nvfp4", "bf16"])
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
