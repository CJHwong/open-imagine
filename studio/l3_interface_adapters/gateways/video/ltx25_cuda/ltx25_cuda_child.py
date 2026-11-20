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

The prompt enhancer is the checkpoint's own Gemma 4 E2B, a component of the same pipeline, so it
is resident beside the video model. It serves two calls. A job with `"task": "rewrite"` asks it
for the longer prompt and returns the text, which is the page's Rewrite. A clip whose `enhance`
is true runs it inside the call first; the studio sends false for a prompt it rewrote already.
Its chat template keeps thinking off unless asked, and nothing asks: the answer starts with the
prompt, with no thought block.

The enhancer's language layers run NVFP4 W4A4 with a static cache, so its decode step compiles
once. Measured on the DGX Spark on 2026-11-20, three prompts after a warm-up: bf16 eager wrote
27.7 tokens/s, NVFP4 eager 23.8, bf16 static 33.7, NVFP4 static 60.0. A rewrite of about 150
tokens takes about 2.5 s instead of 5 to 7, and the enhancer holds 7.0 GiB instead of 9.5. The
first rewrite of a child pays the compile, 27.9 s. The NVFP4 text keeps every element of each
prompt and reads a little shorter.
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
    # One transformer block is compiled and its code serves every block. The compile runs
    # on the first call of each canvas and frame count, inside that run. On the DGX Spark a
    # 768 x 768, 97-frame clip took 70.8 s eager, 65.6 s on its first compiled run and 53.6
    # s after; the transformer alone went from 60.4 s to 43.0 s.
    # Each canvas and frame count is its own graph, and the page offers 30 of them. Dynamo
    # stops at 8 and runs every later one eager: on the DGX Spark the tenth count in one
    # session hit the limit, and the transformer runs about 40% slower eager. 64 leaves room.
    torch._dynamo.config.recompile_limit = 64
    pipe.transformer.compile_repeated_blocks(fullgraph=False, dynamic=False)
    # A whole long clip decodes in one piece and peaks past the machine: on the DGX Spark a
    # 768 x 768, 361-frame clip left 5 GiB free, and in tiles 14 GiB. Tiles decoded a 121-frame
    # clip in 4.4 s against 5.1 s, and the frames differ by 45.3 dB, where the tiles overlap.
    pipe.vae.enable_tiling()
    prepare_enhancer(pipe)
    torch.cuda.synchronize()
    say(f"loaded {model} in {time.time() - started:.1f}s")
    return pipe


def video_chunks(frames):
    """Keep the exporter's rounding without its complete-clip temporary arrays."""
    import numpy as np

    frames = np.asarray(frames)
    if not frames.size or not (frames.min(initial=0) >= 0 and frames.max(initial=1) <= 1):
        return frames

    import torch

    return (torch.from_numpy((frame[None] * 255).round().astype("uint8")) for frame in frames)


def encode(frames, rate: int, audio=None, audio_sample_rate: int | None = None) -> bytes:
    """Use the pinned pipeline's encoder to keep video and audio in one MP4."""
    import tempfile

    from diffusers.utils.export_utils import encode_video

    with tempfile.TemporaryDirectory(prefix="ltx-cuda-", dir=os.environ.get("SPEECH_GEN_SCRATCH")) as scratch:
        target = Path(scratch) / "clip.mp4"
        encode_video(video_chunks(frames), rate, str(target), audio=audio, audio_sample_rate=audio_sample_rate)
        return target.read_bytes()


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


def enhancer_linear(module, name: str) -> bool:
    """A linear layer of the enhancer's language model: not its vision or audio tower, not
    its output head."""
    import torch

    return isinstance(module, torch.nn.Linear) and "language_model" in name and "lm_head" not in name


def prepare_enhancer(pipe) -> None:
    """Quantize the enhancer where it computes, and give it a static cache so its decode
    compiles. The module docstring holds the measurement."""
    enhancer = getattr(pipe, "prompt_enhancer", None)
    if enhancer is None:
        return
    from torchao.prototype.mx_formats import NVFP4DynamicActivationNVFP4WeightConfig
    from torchao.quantization import quantize_

    quantize_(enhancer, NVFP4DynamicActivationNVFP4WeightConfig(), filter_fn=enhancer_linear)
    enhancer.generation_config.cache_implementation = "static"


def rewrite(pipe, job: dict) -> dict:
    """The enhancer's longer prompt, with the instructions a run would use: the image ones when
    a keyframe is given, read from the first, as the pipeline reads a clip's first condition."""
    from diffusers.pipelines.ltx2.utils import (
        LTX2_5_I2V_DEFAULT_SYSTEM_PROMPT,
        LTX2_5_T2V_DEFAULT_SYSTEM_PROMPT,
    )

    references = job.get("references") or []
    image = reference_image(references[0]) if references else None
    system = LTX2_5_I2V_DEFAULT_SYSTEM_PROMPT if image is not None else LTX2_5_T2V_DEFAULT_SYSTEM_PROMPT
    return {"text": pipe.enhance_prompt(job["prompt"], system, image=image)[0]}


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
    audio, audio_sample_rate = None, None
    if job.get("include_audio", True):
        if result[1] is None:
            raise ValueError("LTX-2.5 returned no audio for a clip that requires audio.")
        audio = result[1][0]
        audio_sample_rate = int(pipe.vocoder.config.output_sampling_rate)
    payload = encode(frames, int(arguments["frame_rate"]), audio, audio_sample_rate)
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
        job = {}
        try:
            job = json.loads(line)
            reply = rewrite(pipe, job) if job.get("task") == "rewrite" else run(pipe, job)
            answer({**reply, "request_id": job.get("request_id", "")})
        except Exception as error:  # the parent turns this into a failed job
            answer({"error": f"{type(error).__name__}: {error}", "request_id": job.get("request_id", "")})
        finally:
            # PyTorch keeps a run's peak in its cache. On the DGX Spark a 768 x 768, 241-frame
            # clip left the child holding 99.7 GiB, against 78.2 GiB with this release, and the
            # next clips ran up to 1.7 times slower in the memory that was left.
            torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
