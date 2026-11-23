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

    Asking the Hub costs about 13 s per start on this machine even when every file is
    cached: the empty pipeline took 14.1 s to build from the id. The directory is found
    in the cache rather than through `snapshot_download(local_files_only=True)`, which
    refuses a partial cache, and diffusers only fetches the files it needs.
    """
    from pathlib import Path

    from huggingface_hub import constants

    root = Path(constants.HF_HUB_CACHE) / f"models--{model.replace('/', '--')}"
    reference = root / "refs" / "main"
    if reference.is_file():
        candidate = root / "snapshots" / reference.read_text().strip()
        if candidate.is_dir():
            return str(candidate)
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
    else:
        # Dynamic shapes, because each size and each prompt length is its own sequence length:
        # compiled static, Turbo used up dynamo's eight recompiles by its second size and ran
        # eager from then on. Dynamic, on the DGX Spark, 1024 took 8.9 s against 11.3 s eager,
        # 1328 15.4 against 18.9, with three recompiles over four sizes and two prompts and
        # about 8 s once on the first image. The nvfp4 transformer is not measured compiled.
        pipe.transformer.compile_repeated_blocks(fullgraph=False, dynamic=True)
    torch.cuda.synchronize()
    say(f"loaded {model} as {quantize} in {time.time() - started:.1f}s")
    return pipe


def reference_image(encoded: str):
    """A reference the parent sent as a base64 PNG, as the pipeline wants it."""
    from PIL import Image

    with Image.open(io.BytesIO(base64.b64decode(encoded))) as found:
        return found.convert("RGB")


def report_steps(total: int):
    def on_step(_pipe, index, _timestep, callback_kwargs):
        say(f"step {index + 1}/{total}")
        return callback_kwargs

    return on_step


def reply(image, steps: int) -> dict:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return {
        "png_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "width": image.width,
        "height": image.height,
        "steps": steps,
    }


def run(pipe, job: dict) -> dict:
    """One job through the pipeline: Generate, or Edit with reference images.

    The 2.1 pipeline conditions on images itself. The text encoder reads them as vision
    context and the VAE prepends their latents to the noise, so an edit needs no second
    pipeline and no second checkpoint.
    """
    import torch

    steps = int(job["steps"])
    settings = {
        "prompt": job["prompt"],
        "negative_prompt": job.get("negative") or None,
        "num_inference_steps": steps,
        "true_cfg_scale": float(job.get("guidance", 1.0)),
        "generator": torch.Generator("cuda").manual_seed(int(job["seed"])),
        "callback_on_step_end": report_steps(steps),
    }
    if job.get("mode") == "edit":
        settings["image"] = [reference_image(encoded) for encoded in job["references"]]
        # The pipeline derives height and width from the last condition image at this
        # area, on its own 32-pixel grid.
        settings["output_resolution"] = int(job["output_resolution"])
    else:
        settings["height"] = on_the_grid(int(job["height"]))
        settings["width"] = on_the_grid(int(job["width"]))
        if job.get("start"):
            steps = start_from(pipe, settings, reference_image(job["start"]), float(job["strength"]))
    return reply(pipe(**settings).images[0], steps)


def on_the_grid(side: int) -> int:
    """The side the pipeline renders: it floors each side to its 32-pixel grid itself, and
    a starting image's latents must have the shape of the frame it renders."""
    return max(32, side // 32 * 32)


def start_from(pipe, settings: dict, picture, strength: float) -> int:
    """Start Generate from `picture`: skip the first part of the schedule and put the picture,
    noised to the level of the first step kept, where the noise would go. Returns the steps run.

    The same rule mflux follows on the MLX backends: a strength skips `int(steps * strength)`
    steps, at least one, so a higher strength stays closer to the picture. One step always
    runs. The pipeline takes both parts as arguments, so it needs no image-to-image class.
    """
    import numpy as np
    import torch
    from diffusers.pipelines.qwenimage21.pipeline_qwenimage21 import calculate_shift

    steps = settings["num_inference_steps"]
    # The schedule the pipeline would sample: the checkpoint's own table, else a line.
    schedule = list(pipe.config.sample_sigmas or np.linspace(1.0, 1 / steps, steps))
    skip = min(len(schedule) - 1, max(1, int(len(schedule) * strength)))
    height, width = settings["height"], settings["width"]
    scale = pipe.vae_scale_factor
    config = pipe.scheduler.config
    mu = calculate_shift(
        (height // scale) * (width // scale),
        config.get("base_image_seq_len", 256),
        config.get("max_image_seq_len", 4096),
        config.get("base_shift", 0.5),
        config.get("max_shift", 1.15),
    )
    # The level the pipeline will start at, after any shift its scheduler applies.
    pipe.scheduler.set_timesteps(sigmas=schedule, device="cuda", mu=mu)
    level = float(pipe.scheduler.sigmas[skip])
    with torch.no_grad():
        # The 2.1 VAE reads four channels; the pipeline turns its own condition images RGBA too.
        pixels = pipe.image_processor.preprocess(picture.convert("RGBA"), width=width, height=height).unsqueeze(2)
        encoded = pipe._encode_vae_image(pixels.to(device="cuda", dtype=pipe.vae.dtype), None)
        channels, rows, columns = encoded.shape[1], encoded.shape[3], encoded.shape[4]
        clean = pipe._pack_latents(encoded, 1, channels, rows, columns)
        noise = torch.randn(clean.shape, generator=settings["generator"], device="cuda", dtype=clean.dtype)
        settings["latents"] = level * noise + (1 - level) * clean
    kept = schedule[skip:]
    settings["sigmas"] = kept
    settings["num_inference_steps"] = len(kept)
    settings["callback_on_step_end"] = report_steps(len(kept))
    return len(kept)


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
        job = {}
        try:
            job = json.loads(line)
            answer({**run(pipe, job), "request_id": job.get("request_id", "")})
        except Exception as error:  # the parent turns this into a failed job
            answer({"error": f"{type(error).__name__}: {error}", "request_id": job.get("request_id", "")})
        finally:
            # PyTorch keeps a run's peak in its cache. On the DGX Spark the child held 68.4 GiB
            # after a ten-reference edit and still 68.4 GiB after the next 512 image, which needs
            # 34.1 GiB.
            torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
