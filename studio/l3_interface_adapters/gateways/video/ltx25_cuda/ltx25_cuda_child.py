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
#   "imageio",
#   "imageio-ffmpeg",
#   "av",
# ]
# [tool.uv]
# index-strategy = "unsafe-best-match"
# extra-index-url = ["https://download.pytorch.org/whl/cu130"]
# ///
"""
LTX-2.5 on a CUDA GPU, one JSON job per line.

The pipeline is diffusers' `LTX2DFRPipeline`, which is the one the LTX-2.5 checkpoint is
documented for. It runs the distilled eight-value sigma schedule by default, with no
classifier-free guidance, and that is the same schedule the MLX backend runs when it takes
its distilled path. `LTX2Pipeline` would run the base thirty-step schedule instead, which
takes 3.75 times as long for a clip the checkpoint was not trained to make.

The prompt enhancer is a flag on the same call and stays off unless the job asks for it: it
is a 9.5 GiB Gemma that only matters when a caller presses Rewrite.
"""

import argparse
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

PTXAS = Path("/usr/local/cuda/bin/ptxas")
DISTILLED_STEPS = 8
"""`LTX2DFRPipeline` runs `DISTILLED_SIGMA_VALUES`, which holds eight values. The count is
the schedule's, not a setting: the checkpoint is distilled to that schedule."""


def prepare_environment() -> None:
    """Use the CUDA ptxas that knows this GPU, and avoid the chunked downloader.

    Triton's bundled ptxas rejects `sm_121a` on the DGX Spark. CUDA 13.0's own compiles
    it. Xet delivery stalls on this network at about 2 KiB/s against 56 MB/s over plain
    HTTPS.
    """
    if PTXAS.is_file():
        os.environ.setdefault("TRITON_PTXAS_PATH", str(PTXAS))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


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

    Measured on this machine: safetensors' mmap-backed tensors reach the device at
    128 MB/s; the same tensors from ordinary memory at 14 GiB/s. One group of aliased
    weights is cloned and moved at a time and the clone is dropped as the group lands, so
    the host high-water mark is one tensor. Cloning a whole 38 GB component first holds it
    beside the device copy out of the same pool, and the move then crawls.
    """
    groups: dict[int, list] = {}
    for tensor in [*module.parameters(), *module.buffers()]:
        groups.setdefault(tensor.data.data_ptr(), []).append(tensor)
    for tensors in groups.values():
        landed = tensors[0].data.clone().to(device)
        for tensor in tensors:
            tensor.data = landed


def load(model: str):
    import torch
    from diffusers import LTX2DFRPipeline

    started = time.time()
    pipe = LTX2DFRPipeline.from_pretrained(local_snapshot(model), torch_dtype=torch.bfloat16)
    for component in pipe.components.values():
        if hasattr(component, "parameters"):
            move_by_way_of_memory(component, "cuda")
    # Every weight is on the device already; this call sets the pipeline's own bookkeeping.
    pipe.to("cuda")
    torch.cuda.synchronize()
    say(f"loaded {model} in {time.time() - started:.1f}s")
    return pipe


def encode(frames, rate: int) -> bytes:
    """An MP4 through imageio, written to a scratch file.

    imageio's ffmpeg plugin opens a path, not a buffer: "FFMPEG can not handle the given
    uri" is what a BytesIO gets. The file lives in the child's scratch folder, which the
    parent makes per child and removes when it goes.
    """
    import tempfile
    from pathlib import Path

    import imageio.v2 as imageio
    import numpy as np

    scratch = os.environ.get("SPEECH_GEN_SCRATCH") or tempfile.mkdtemp(prefix="ltx-cuda-")
    target = Path(scratch) / "clip.mp4"
    writer = imageio.get_writer(str(target), fps=rate, codec="libx264", quality=7, macro_block_size=1)
    try:
        for frame in frames:
            writer.append_data(np.asarray(frame))
    finally:
        writer.close()
    try:
        return target.read_bytes()
    finally:
        target.unlink(missing_ok=True)


def unpack(frames):
    """The clip's frames, whatever shape the pipeline hands back.

    With `output_type="np"` the result is either a list of per-video frame lists or one
    array of (batch, frames, height, width, channels). Taking the first element blindly
    turned a whole clip into one "frame" and imageio refused it: "Image must have 1, 2, 3
    or 4 channels".
    """
    if hasattr(frames, "ndim"):
        if frames.ndim == 5:
            return frames[0]
        return frames
    if isinstance(frames, (list, tuple)) and frames and isinstance(frames[0], (list, tuple)):
        return frames[0]
    return frames


def reference_image(encoded: str):
    """A keyframe the parent sent as a base64 PNG, as the pipeline wants it."""
    from PIL import Image

    with Image.open(io.BytesIO(base64.b64decode(encoded))) as found:
        return found.convert("RGB")


def run(pipe, job: dict) -> dict:
    import torch

    seen = {"count": 0}

    def on_step(_pipe, index, _timestep, callback_kwargs):
        seen["count"] = index + 1
        say(f"step {seen['count']}/{DISTILLED_STEPS}")
        return callback_kwargs

    arguments = {
        "prompt": job["prompt"],
        "height": int(job["height"]),
        "width": int(job["width"]),
        "num_frames": int(job.get("frames", 97)),
        "frame_rate": float(job.get("frame_rate", 24.0)),
        "generator": torch.Generator(device="cpu").manual_seed(int(job["seed"])),
        "output_type": "np",
        "return_dict": False,
        "callback_on_step_end": on_step,
    }
    if job.get("enhance"):
        arguments["enable_prompt_enhancement"] = True
    if job.get("references"):
        # The pipeline's own conditioning item: it resizes, re-compresses and encodes the
        # picture, and pins one frame at the index with the strength the run asked for.
        from diffusers.pipelines.ltx2 import LTX2VideoCondition

        arguments["conditions"] = [
            LTX2VideoCondition(
                frames=reference_image(entry["png_base64"]),
                index=int(entry.get("frame_index", 0)),
                strength=float(entry.get("strength", 1.0)),
            )
            for entry in job["references"]
        ]
    result = pipe(**arguments)
    frames = unpack(result[0])
    payload = encode(frames, int(arguments["frame_rate"]))
    return {
        "mp4": base64.b64encode(payload).decode("ascii"),
        "seconds": round(len(frames) / arguments["frame_rate"], 3),
        "width": arguments["width"],
        "height": arguments["height"],
        "frames": len(frames),
        "steps": seen["count"] or DISTILLED_STEPS,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Lightricks/LTX-2.5-Diffusers")
    arguments = parser.parse_args()
    prepare_environment()
    import torch

    if not torch.cuda.is_available():
        say("CUDA is not available in this environment")
        return 2
    pipe = load(arguments.model)
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
