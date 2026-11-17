#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "torch==2.8.0",
#   "torchaudio==2.8.0",
#   "transformers==5.19.0",
#   "hydra-core>=1.3.2",
#   "loguru>=0.6.0",
#   "kui>=1.6.0",
#   "uvicorn>=0.30.0",
#   "pyrootutils>=1.0.4",
#   "natsort>=8.4.0",
#   "einops>=0.7.0",
#   "librosa>=0.10.1",
#   "resampy>=0.4.3",
#   "einx[torch]==0.2.2",
#   "pydub",
#   "modelscope==1.17.1",
#   "opencc-python-reimplemented==0.1.7",
#   "silero-vad",
#   "ormsgpack",
#   "tiktoken>=0.8.0",
#   "pydantic==2.9.2",
#   "cachetools",
#   "descript-audio-codec",
#   "safetensors",
#   "tokenizers==0.23.2",
#   "soundfile>=0.12.1",
#   "numpy",
#   "huggingface-hub",
# ]
# [tool.uv]
# index-strategy = "unsafe-best-match"
# extra-index-url = ["https://download.pytorch.org/whl/cu129"]
# ///
"""Drama-3 on a CUDA GPU, one JSON job per line.

The engine is fish-speech, taken from its pinned checkout rather than from the package:
the package depends on pyaudio, which needs portaudio headers to build and is only used
for microphone capture. Its loader, ModelManager is the loader that knows how to place the
Drama-3 backbone and the DAC codec, and it refuses to import outside the project checkout
(pyrootutils wants `.project-root`), so this child keeps a pinned checkout in a cache
directory and runs from there. That is the same rule the LTX and H3 engines follow: the
engine brings its own source, and the parent never imports it.

`pyaudio` is not installed. It builds against portaudio for microphone capture, which the
server needs and inference does not.
"""

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = "https://github.com/fishaudio/fish-speech"
REVISION = "0f8a12e8a651062fdee9c33a894bdccd3a8513f1"


PTXAS = Path("/usr/local/cuda/bin/ptxas")


def prepare_environment() -> None:
    """Point Triton at a ptxas that knows this GPU, and avoid the chunked downloader.

    Triton bundles its own `ptxas`, and that build rejects `sm_121a` on the DGX Spark:
    "Value 'sm_121a' is not defined for option 'gpu-name'". CUDA 13.0's own ptxas
    compiles it, so it is used when present. Xet delivery stalls on this network at about
    2 KiB/s against 56 MB/s over plain HTTPS, so the plain path is taken.
    """
    if PTXAS.is_file():
        os.environ.setdefault("TRITON_PTXAS_PATH", str(PTXAS))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


def patch_triton() -> None:
    """Teach Triton that CUDA 13 exists.

    Triton's `ptx_get_version` maps majors 10, 11 and 12 and raises for anything else:
    "Triton only support CUDA 10.0 or higher, but got CUDA version: 13.0", on a machine
    whose toolchain is 13.0. CUDA 13.0 emits PTX ISA 9.0, so that is what it is told.
    """
    import triton.backends.nvidia.compiler as compiler

    original = compiler.ptx_get_version

    def ptx_get_version(cuda_version: str) -> int:
        major, minor = map(int, cuda_version.split("."))
        if major >= 13:
            return 90 + minor
        return original(cuda_version)

    compiler.ptx_get_version = ptx_get_version


def patch_checkpoint_copies() -> None:
    """Clone each checkpoint tensor before the engine copies it to the device.

    The engine's `target.copy_(tensor)` reads straight from safetensors' file mapping,
    which measured 0.19 GB/s on this machine. Cloned into ordinary memory first, the copy
    measured 59.57 GB/s. Measured on the DGX Spark on 2026-11-15: the load fell from
    350 s to under a minute.
    """
    try:
        from fish_speech.models.text2semantic.fish_omni import model as omni
    except ImportError:
        say("the engine's checkpoint iterator is not where this child looked; its load keeps the slow copy")
        return
    original = getattr(omni, "iter_checkpoint_tensors", None)
    if original is None:
        say("the engine has no checkpoint iterator this child can wrap; its load keeps the slow copy")
        return

    def cloned(*args, **kwargs):
        for name, tensor in original(*args, **kwargs):
            yield name, tensor.clone()

    omni.iter_checkpoint_tensors = cloned


def say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def answer(document: dict) -> None:
    print(json.dumps(document), flush=True)


def head_of(root: Path) -> str:
    """The commit a checkout is on, or "" when it cannot say."""
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def checkout(cache: Path) -> Path:
    """The pinned engine source, cloned once, and proved to sit on the pinned commit.

    A `.project-root` marker is not proof. A clone that succeeded followed by a checkout
    that did not leaves the marker on the default branch, and every later start used it.
    Each start reads HEAD, and an install on another commit is replaced: the clone is made
    beside it, checked, and swapped in, so a failed attempt leaves the old one untouched.
    """
    target = cache / REVISION
    if (target / ".project-root").is_file() and head_of(target) == REVISION:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = cache / f".{REVISION}.building-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    say(f"cloning fish-speech {REVISION[:8]}")
    try:
        subprocess.run(["git", "clone", "--quiet", REPO, str(staging)], check=True)
        subprocess.run(["git", "-C", str(staging), "checkout", "--quiet", REVISION], check=True)
        head = head_of(staging)
        if head != REVISION:
            raise RuntimeError(f"fish-speech checked out {head or 'nothing'}, not {REVISION}")
        previous = cache / f"{REVISION}.old"
        shutil.rmtree(previous, ignore_errors=True)
        if target.exists():
            target.rename(previous)
        staging.rename(target)
        shutil.rmtree(previous, ignore_errors=True)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def snapshot(repo: str) -> str:
    """The cached copy of a repository, and a download only when there is none."""
    from huggingface_hub import snapshot_download

    try:
        return snapshot_download(repo, local_files_only=True)
    except Exception:  # no complete cache; the download path below handles it
        return snapshot_download(repo, local_files_only=False)


def load(checkpoint: str, half: bool):

    from tools.server.model_manager import ModelManager

    patch_checkpoint_copies()
    started = time.time()
    manager = ModelManager(
        mode="tts",
        device="cuda",
        half=half,
        compile=False,
        llama_checkpoint_path=checkpoint,
        decoder_checkpoint_path=None,
        decoder_config_name="modded_dac_vq",
    )
    say(f"loaded {checkpoint} in {time.time() - started:.1f}s")
    return manager


def request_for(job: dict):
    """Read the flat Voice payload shared by the gateway and child."""
    from fish_speech.utils.schema import ServeReferenceAudio, ServeTTSRequest

    reference = job.get("audio") or ""
    fields = {
        "text": job["text"],
        "references": [],
        "reference_id": None,
        "format": "wav",
        "chunk_length": 200,
        "normalize": True,
        "use_memory_cache": "on",
        "seed": int(job["seed"]),
        "streaming": False,
        "max_new_tokens": int(job.get("max_tokens", 1024)),
        "top_p": float(job.get("top_p", 0.8)),
        "repetition_penalty": 1.1,
        "temperature": float(job.get("temperature", 0.8)),
    }
    if "top_k" in job:
        fields["top_k"] = int(job["top_k"])
    if reference:
        # This revision of the schema takes a ServeReferenceAudio object, not the
        # (rate, samples) tuple earlier ones took. A tuple reaches its validator and
        # fails with "'tuple' object has no attribute 'get'". The transcript is what
        # the model aligns the reference against, so an empty one clones nothing.
        fields["references"] = [
            ServeReferenceAudio(audio=base64.b64decode(reference), text=str(job.get("ref_text") or ""))
        ]
    return ServeTTSRequest(**fields)


def run(manager, job: dict) -> dict:
    import numpy as np
    import soundfile

    request = request_for(job)
    rate, pieces = None, []
    for event in manager.tts_inference_engine.inference(request):
        if event.code == "error":
            raise ValueError(str(event.error))
        if event.code in ("segment", "final") and isinstance(event.audio, tuple):
            rate, samples = event.audio
            pieces.append(np.asarray(samples, dtype=np.float32))
            say(f"step {len(pieces)}/{len(pieces) + 1}")
    if not pieces or rate is None:
        raise ValueError("no audio was generated")
    audio = np.concatenate(pieces)
    buffer = io.BytesIO()
    soundfile.write(buffer, audio, rate, format="WAV", subtype="PCM_16")
    return {
        "wav": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "seconds": round(len(audio) / rate, 3),
        "sample_rate": int(rate),
        "steps": len(pieces),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="fishaudio/drama-3")
    parser.add_argument("--cache", default=str(Path.home() / ".cache" / "open-imagine" / "fish-speech"))
    parser.add_argument("--half", action="store_true")
    arguments = parser.parse_args()

    prepare_environment()
    import torch

    if not torch.cuda.is_available():
        say("CUDA is not available in this environment")
        return 2
    root = checkout(Path(arguments.cache))
    os.chdir(root)
    sys.path.insert(0, str(root))
    checkpoint = arguments.checkpoint
    if not Path(checkpoint).is_dir():
        checkpoint = snapshot(checkpoint)
    patch_triton()
    manager = load(checkpoint, arguments.half)
    say("ready")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            answer(run(manager, json.loads(line)))
        except Exception as error:  # the parent turns this into a failed job
            answer({"error": f"{type(error).__name__}: {error}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
