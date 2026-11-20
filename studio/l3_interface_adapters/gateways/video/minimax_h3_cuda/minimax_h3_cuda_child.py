#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "torch==2.15.0",
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
#   "av",
# ]
# [tool.uv]
# index-strategy = "unsafe-best-match"
# extra-index-url = ["https://download.pytorch.org/whl/cu130"]
# ///
"""MiniMax H3 on a CUDA GPU, one JSON job per line.

The pipeline is diffusers' modular `MiniMaxH3Blocks`, which picks its workflow per call from
the inputs: text alone is `t2va`, a first or last frame is `fl2va`, and pictures with a track
are `ref2va`. The last runs on its own transformer, so the child holds both.

The checkpoint is 62 GB of each transformer and 62 GB of encoder in bfloat16, more than the
DGX Spark holds. Every linear lands on the device one at a time and is quantized to NVFP4 W4A4
as it lands, so the bf16 copy is never whole on the device. Measured there on 2026-11-20: the
encoder and both transformers held 56.3 GiB, and free memory never fell under 48.7 GiB while
they loaded, in 133 s from the bf16 files. A pack of the quantized weights would save part of
that load and nothing else, so there is none. Against FP8, NVFP4 ran each step 2.0 to 2.2
times as fast, held 24 GiB less, and drew frames with no visible grain at 512 x 288 and
1024 x 576.

The encoder is cut after layer 50, the one H3 reads, and its head is dropped.
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
DEFAULT_MODEL = "MiniMaxAI/MiniMax-H3"
DEFAULT_REVISION = "1cc7549f2cf0af8ff2f09b24f3c57303c8aa6317"
"""The release the measurements ran on. `refs/main` is not trusted: on the DGX Spark it still
named an older snapshot that held only the encoder."""
WEIGHTS = (
    "model_index.json",
    "modular_model_index.json",
    "LICENSE",
    "transformer/*",
    "transformer_ref/*",
    "text_encoder/*",
    "vae/*",
    "audio_vae/*",
    "processor/*",
    "tokenizer/*",
    "scheduler/*",
    "audio_scheduler/*",
)
TRANSFORMERS = ("transformer", "transformer_ref")
QUANTIZED = ("text_encoder", *TRANSFORMERS)


def prepare_environment() -> None:
    """Use the CUDA ptxas that knows this GPU, and avoid the chunked downloader.

    Triton's bundled ptxas rejects `sm_121a` on the DGX Spark, and the NVFP4 kernels compile
    through it. Xet delivery stalls on that network where plain HTTPS runs at full speed.
    """
    if PTXAS.is_file():
        os.environ.setdefault("TRITON_PTXAS_PATH", str(PTXAS))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


def say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def answer(document: dict) -> None:
    print(json.dumps(document), flush=True)


def snapshot(model: str, revision: str) -> str:
    """The pinned release on this machine, fetched once when it is not there.

    A cached snapshot is used without asking the Hub, which costs seconds per start.
    """
    from huggingface_hub import constants, snapshot_download

    cached = Path(constants.HF_HUB_CACHE) / f"models--{model.replace('/', '--')}" / "snapshots" / revision
    if (cached / "transformer_ref").is_dir() and (cached / "transformer").is_dir():
        return str(cached)
    local = Path(model).expanduser()
    if local.is_dir():
        return str(local)
    say(f"fetching {model} at {revision[:12]}")
    return snapshot_download(model, revision=revision, allow_patterns=list(WEIGHTS))


def component(pipe, name: str):
    found = getattr(pipe, name, None)
    return found if found is not None else pipe.components[name]


def move_by_way_of_memory(module, device: str = "cuda") -> None:
    """Send each weight through ordinary memory before it lands on the device.

    safetensors' file-backed tensors reach the device at 0.19 GB/s on the DGX Spark, and the
    same tensors from ordinary memory at 59.6 GB/s. One group of aliased weights is cloned and
    moved at a time, so the host holds one tensor beyond the model.
    """
    groups: dict[int, list] = {}
    for tensor in [*module.parameters(), *module.buffers()]:
        groups.setdefault(tensor.data.data_ptr(), []).append(tensor)
    for tensors in groups.values():
        if tensors[0].data.device.type == device:
            continue
        landed = tensors[0].data.clone().to(device)
        for tensor in tensors:
            tensor.data = landed


def land_in_nvfp4(module, kept: tuple[str, ...] = ()) -> None:
    """Move a module to the device one linear at a time, each quantized to NVFP4 as it lands.

    A bf16 linear that a name in `kept` matches lands as it is: the encoder's vision tower
    reads pictures, and the dropped head never runs. What is not a linear follows at the end.
    """
    import torch
    from torchao.prototype.mx_formats import NVFP4DynamicActivationNVFP4WeightConfig
    from torchao.quantization import quantize_

    config = NVFP4DynamicActivationNVFP4WeightConfig()
    for name, layer in list(module.named_modules()):
        if not isinstance(layer, torch.nn.Linear) or layer.weight.dtype != torch.bfloat16:
            continue
        if any(part in name for part in kept):
            continue
        move_by_way_of_memory(layer, "cuda")
        quantize_(layer, config)
    move_by_way_of_memory(module, "cuda")


def drop_unread_encoder_parts(pipe) -> None:
    """H3 reads the input of encoder layer 50, so the layers after it and the head never run."""
    import torch

    encoder = component(pipe, "text_encoder")
    del encoder.model.language_model.layers[pipe.text_encoder_layer + 1 :]
    encoder.lm_head = torch.nn.Identity()


def load(model: str, revision: str):
    import torch
    from diffusers import ModularPipeline

    started = time.time()
    pipe = ModularPipeline.from_pretrained(snapshot(model, revision))
    small = [name for name in pipe.component_names if name not in QUANTIZED]
    pipe.load_components(names=small, dtype=torch.bfloat16, device_map="cpu")
    for name in ("vae", "audio_vae"):
        move_by_way_of_memory(component(pipe, name))
    # One large component at a time, quantized as it lands, so the bf16 copy on the host is
    # one component and never two.
    pipe.load_components(names=["text_encoder"], dtype=torch.bfloat16, device_map="cpu")
    drop_unread_encoder_parts(pipe)
    land_in_nvfp4(component(pipe, "text_encoder"), kept=("visual", "lm_head"))
    say(f"encoder on the device in {time.time() - started:.1f}s")
    for name in TRANSFORMERS:
        pipe.load_components(names=[name], dtype=torch.bfloat16, device_map="cpu")
        land_in_nvfp4(component(pipe, name))
        component(pipe, name).register_forward_pre_hook(count_step)
        say(f"{name} on the device in {time.time() - started:.1f}s")
    torch.cuda.synchronize()
    say(f"loaded {model} in {time.time() - started:.1f}s")
    return pipe


def picture(encoded: str):
    from PIL import Image

    with Image.open(io.BytesIO(base64.b64decode(encoded))) as found:
        return found.convert("RGB")


def decode_track(encoded: str, rate: int):
    """The track as stereo float samples at the audio VAE's rate, decoded in memory."""
    import av
    import numpy as np

    pieces = []
    with av.open(io.BytesIO(base64.b64decode(encoded))) as container:
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=rate)
        for frame in [*container.decode(audio=0), None]:
            pieces.extend(resampled.to_ndarray() for resampled in resampler.resample(frame))
    if not pieces:
        raise ValueError("The audio track holds no sound this child can decode.")
    return np.concatenate(pieces, axis=1).astype("float32")


STEP = {"count": 0, "total": 0}
"""The run in progress. The modular blocks take no step callback, and a guidance-distilled
step is one transformer call, so a hook on each transformer counts the steps."""


def count_step(*_) -> None:
    STEP["count"] += 1
    say(f"step {STEP['count']}/{STEP['total']}")


def encode(frames, audio, rate: int | None) -> bytes:
    import tempfile

    from diffusers.utils.export_utils import encode_video

    with tempfile.TemporaryDirectory(prefix="h3-cuda-", dir=os.environ.get("SPEECH_GEN_SCRATCH")) as scratch:
        target = Path(scratch) / "clip.mp4"
        encode_video(frames, fps=24, output_path=str(target), audio=audio, audio_sample_rate=rate)
        return target.read_bytes()


def run(pipe, job: dict) -> dict:
    import torch

    steps = int(job["steps"])
    frames = int(job["frames"])
    # `num_inference_steps` counts the sigma points, the final 0 among them.
    STEP.update(count=0, total=steps - 1)
    say("step 0/0")
    arguments = {
        "prompt": job["prompt"],
        "height": int(job["height"]),
        "width": int(job["width"]),
        "num_frames": frames,
        "num_inference_steps": steps,
        "generator": torch.Generator().manual_seed(int(job["seed"])),
        "output": ["videos", "audio", "sampling_rate"],
    }
    track = None
    if job.get("audio"):
        from diffusers.modular_pipelines.minimax_h3 import MiniMaxH3AudioReference, MiniMaxH3ImageReference

        rate = int(pipe.audio_sampling_rate)
        track = decode_track(job["audio"], rate)
        arguments["references"] = [
            *(MiniMaxH3ImageReference(image=picture(encoded)) for encoded in job["pictures"]),
            MiniMaxH3AudioReference(audio=torch.from_numpy(track), sample_rate=rate),
        ]
    else:
        if job.get("first"):
            arguments["image"] = picture(job["first"])
        if job.get("last"):
            arguments["last_image"] = picture(job["last"])
    result = pipe(**arguments)
    video = result["videos"][0]
    rate = int(result["sampling_rate"])
    sound = None
    if track is not None:
        # The clip keeps the track it followed, cut to the clip's length.
        sound = torch.from_numpy(track[:, : round(len(video) / 24 * rate)])
    elif job.get("include_audio", True):
        sound = result["audio"][0]
    payload = encode(video, sound, rate if sound is not None else None)
    width, height = video[0].size
    return {
        "mp4": base64.b64encode(payload).decode("ascii"),
        "width": width,
        "height": height,
        "frames": len(video),
        "steps": STEP["count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    arguments = parser.parse_args()
    prepare_environment()
    import torch

    if not torch.cuda.is_available():
        say("CUDA is not available in this environment")
        return 2
    pipe = load(arguments.model, arguments.revision)
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
            # A run's peak stays in PyTorch's cache otherwise, and the next run has less room.
            torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
