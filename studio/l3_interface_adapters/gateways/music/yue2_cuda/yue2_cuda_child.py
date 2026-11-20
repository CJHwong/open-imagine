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
#   "torchaudio",
#   "pretty_midi",
#   "mir_eval",
#   "mido",
#   "imageio-ffmpeg",
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
import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import time
import urllib.request
import uuid
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory


def say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def answer(document: dict) -> None:
    print(json.dumps(document), flush=True)


def blob_sha1(data: bytes) -> str:
    """The git object hash of a file's bytes, which the upstream pins quote."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def fetch_pinned(name: str) -> bytes:
    with urllib.request.urlopen(f"{TRANSCRIBER_ROOT}/skills/yue2-music/scripts/{name}", timeout=120) as answer:
        data = answer.read()
    if blob_sha1(data) != TRANSCRIBER_FILES[name]:
        raise ValueError(f"Upstream transcriber file {name} does not match its pin.")
    return data


def install_transcriber(extras_dir: Path) -> Path:
    """The pinned transcriber scripts, written once and reused afterwards."""
    directory = Path(extras_dir).expanduser() / TRANSCRIBER_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    for name in TRANSCRIBER_FILES:
        target = directory / name
        if target.is_file() and blob_sha1(target.read_bytes()) == TRANSCRIBER_FILES[name]:
            continue
        target.write_bytes(fetch_pinned(name))
    return directory


def audio_suffix(raw: bytes) -> str:
    """The extension the decoder infers a format from. A file called `.audio` needs ffmpeg."""
    if raw.startswith(b"RIFF"):
        return ".wav"
    if raw.startswith(b"ID3") or raw[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    if raw.startswith(b"OggS"):
        return ".ogg"
    if raw[:4] == b"fLaC":
        return ".flac"
    return ".bin"


# The transcriber, loaded by the first transcription and kept for the child's life.
TRANSCRIBER: dict = {}
SCORE_PROMPTS = ["timestamp", "downbeat_meter", "structure", "key"]


def move_by_way_of_memory(module, device: str) -> None:
    """Send each weight through ordinary memory before it lands on the device.

    The checkpoint's tensors are mapped from the file, and the device copy reads them at
    about 0.18 GB/s on the DGX Spark: 14.3 s for SheetSage2's 2.52 GiB, measured on
    2026-11-19. From ordinary memory the same copy is a fraction of a second.
    """
    groups: dict[int, list] = {}
    for tensor in [*module.parameters(), *module.buffers()]:
        groups.setdefault(tensor.data.data_ptr(), []).append(tensor)
    for tensors in groups.values():
        landed = tensors[0].data.clone().to(device)
        for tensor in tensors:
            tensor.data = landed


def transcriber(extras_dir: Path):
    """SheetSage2 on MERT-v2, held after the first transcription.

    The pinned script loaded both on every call, in a new interpreter: measured on the
    DGX Spark on 2026-11-19, a ten-second clip took 21.7 to 27.5 s, of which the model
    itself spent 1.0 s and the load 16.5 s. Held, the two cost 2.52 GiB beside YuE's
    weights. The script's helpers are imported from the pinned copy, so its score
    checks are the ones that run here.
    """
    if TRANSCRIBER:
        return TRANSCRIBER["model"], TRANSCRIBER["tools"]
    from huggingface_hub import snapshot_download

    directory = install_transcriber(extras_dir)
    patterns = ["config.json", "*.json", "*.safetensors", "*.py", "LICENSE"]
    snapshot_download(SHEETSAGE, revision=SHEETSAGE_REVISION, allow_patterns=patterns)
    base_model = snapshot_download(MERT, revision=MERT_REVISION, allow_patterns=patterns)
    import imageio_ffmpeg

    # The transcriber's decoder asks for a command called `ffmpeg`. The package ships a
    # binary under a longer name, so a link with that name goes first on PATH.
    binaries = Path(extras_dir).expanduser() / "bin"
    binaries.mkdir(parents=True, exist_ok=True)
    # The link outlives the environment it points into, so it follows the binary when uv
    # rebuilds that environment somewhere else.
    link = binaries / "ffmpeg"
    target = imageio_ffmpeg.get_ffmpeg_exe()
    if not link.is_symlink() or os.readlink(link) != target:
        link.unlink(missing_ok=True)
        link.symlink_to(target)
    os.environ["PATH"] = os.pathsep.join([str(binaries), os.environ.get("PATH", "")])
    sys.path.insert(0, str(directory))
    import abc_tools
    from transformers import AutoModel

    started = time.time()
    model = AutoModel.from_pretrained(
        SHEETSAGE,
        trust_remote_code=True,
        local_files_only=True,
        revision=SHEETSAGE_REVISION,
        code_revision=SHEETSAGE_REVISION,
        base_model_path=base_model,
    ).eval()
    move_by_way_of_memory(model, "cuda")
    say(f"loaded the transcriber in {time.time() - started:.1f}s")
    TRANSCRIBER.update(model=model, tools=abc_tools)
    return model, abc_tools


def transcribe(job: dict, extras_dir: Path) -> tuple[str, dict]:
    """The reference audio as native ABC, through the pinned SheetSage2 interface."""
    raw = base64.b64decode(job.get("reference_audio") or "")
    if not raw:
        raise ValueError("Upload reference audio before transcribing or covering a song.")
    task = job.get("transcription_task", "melody-full")
    model, abc_tools = transcriber(extras_dir)
    prompts = [*SCORE_PROMPTS, *(["chord_full", "melody_full"] if task == "full" else [])]
    options = {}
    if task != "full":
        prompts.append("melody_vocal" if task == "melody-vocal" else "melody_full")
        options["melody_only"] = True
    with TemporaryDirectory(prefix="yue2-transcribe-") as scratch:
        audio = Path(scratch) / f"reference{audio_suffix(raw)}"
        audio.write_bytes(raw)
        output = Path(scratch) / "transcription"
        output.mkdir()
        result = model.transcribe(
            str(audio),
            output_dir=str(output),
            prompts=prompts,
            dtype="bf16",
            preset="default",
            max_seconds=None,
            **options,
        )
        if result.get("abc_error") or not result.get("abc"):
            raise ValueError(f"Transcription failed: no usable ABC: {result.get('abc_error')}")
        parsed = abc_tools.parse_abc(result["abc"])
        if task != "full" and any(voice.chords for voice in parsed.voices.values()):
            raise ValueError("Transcription failed: the melody carries chord symbols")
        if not (output / "score.abc").is_file():
            raise ValueError("Transcription failed: the transcriber saved no score.abc")
        score = (output / "score.abc").read_text(encoding="utf-8")
    manifest = {"status": "complete", "warnings": result.get("warnings", [])}
    artifacts = [
        {
            "name": "score.abc",
            "content_type": "text/plain",
            "base64": base64.b64encode(score.encode("utf-8")).decode("ascii"),
        }
    ]
    return score, {
        "transcription": {"status": manifest.get("status"), "warnings": manifest.get("warnings", [])},
        "artifacts": artifacts,
    }


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
    if "cfg_scale" in job:
        request["cfg_scale"] = job["cfg_scale"]
    return request


# The upstream transcriber is a PyTorch script, not part of `yue2-infer`: SheetSage2 through
# its Transformers interface. This child imports the pinned script's helpers and holds the
# model after the first transcription; see `transcriber`.
TRANSCRIBER_REVISION = "1647252d68b70cbead046ffd3f7caf036dde47ee"
TRANSCRIBER_ROOT = f"https://raw.githubusercontent.com/multimodal-art-projection/YuE/{TRANSCRIBER_REVISION}"
TRANSCRIBER_DIRECTORY = "yue2-transcriber"
# The same two helpers the MLX child installs, with the script that drives them.
TRANSCRIBER_FILES = {
    "transcribe.py": "0a637296dc72278d81c41204f2b7c23c0ff29272",
    "abc_tools.py": "88b66e5bb73a4ba3633ae4c7a417118806e0e606",
    "common.py": "4b6c2d502f131539b26069753b6e4482eb2db280",
}
SHEETSAGE = "m-a-p/SheetSage2"
SHEETSAGE_REVISION = "eab522a8168e8b8b8c4856bf8609cd86198f01fe"
# The adapter's base model. The script wants a local snapshot for an offline load.
MERT = "m-a-p/MERT-v2-FullSong"
MERT_REVISION = "d8ba1c745e733b3908ce6ad16ebeb17ac7600a42"

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
        "source": source_revision(model_name),
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


def source_revision(model: str) -> str:
    """The committed snapshot this model resolves to, when this machine can name one.

    The cache writes `refs/main`, and that is the commit the engine's loader takes. Counting
    snapshot directories answered `unknown` as soon as a second one was cached, which let a
    pack built from one revision serve another. A local folder is named by each file's
    path, size and modification time: a rewrite changes the identity even at the same
    length, and hashing every shard on every start would cost minutes.
    """
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
    except ImportError:  # the unit tests run without the engine's packages
        HF_HUB_CACHE = ""
    if HF_HUB_CACHE:
        root = Path(HF_HUB_CACHE) / f"models--{model.replace('/', '--')}"
        reference = root / "refs" / "main"
        if reference.is_file():
            commit = reference.read_text().strip()
            if (root / "snapshots" / commit).is_dir():
                return commit
        snapshots = root / "snapshots"
        if snapshots.is_dir():
            commits = sorted(one.name for one in snapshots.iterdir() if one.is_dir())
            if len(commits) == 1:
                return commits[0]
    local = Path(model).expanduser()
    if local.is_dir():
        digest = hashlib.sha256()
        for path in sorted(local.rglob("*")):
            if path.is_file():
                stat = path.stat()
                digest.update(f"{path.relative_to(local)}:{stat.st_size}:{stat.st_mtime_ns}".encode())
        return "local:" + digest.hexdigest()[:16]
    return "unknown"


def staging_directory(directory: Path) -> Path:
    """An empty folder beside the pack in use, where a new one is assembled.

    The name carries this process, so two studios preparing the same model never delete
    each other's work.
    """
    staging = directory.with_name(f"{directory.name}.building-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    staging.mkdir(parents=True)
    return staging


def recover(directory: Path) -> None:
    """Put a valid pack back when a previous publish died between its two renames."""
    previous = directory.with_name(directory.name + ".old")
    if not directory.exists() and previous.is_dir():
        previous.rename(directory)


@contextlib.contextmanager
def pack_lock(directory: Path):
    """One builder per pack. A second studio waits, then uses what the first built.

    A lock left by a process that died is taken over: its pid no longer runs.
    """
    lock = directory.with_name(directory.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                holder = int(lock.read_text().strip() or "0")
            except (OSError, ValueError):
                holder = 0
            if holder and not _running(holder):
                lock.unlink(missing_ok=True)
                continue
            if not holder and time.time() - lock.stat().st_mtime > 60:
                # A lock with no pid that nobody has touched for a minute is a leftover.
                lock.unlink(missing_ok=True)
                continue
            time.sleep(5)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        lock.unlink(missing_ok=True)


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def publish(staging: Path, directory: Path) -> None:
    """Swap a finished pack in, and never leave half of one under the published name."""
    previous = directory.with_name(directory.name + ".old")
    shutil.rmtree(previous, ignore_errors=True)
    if directory.exists():
        directory.rename(previous)
    staging.rename(directory)
    shutil.rmtree(previous, ignore_errors=True)


def read_manifest(directory: Path) -> dict | None:
    path = directory / "pack.json"
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Half a manifest is an interrupted write, not a pack. Absent means build one.
        say(f"{path} cannot be read, so the pack is built again")
        return None
    if not isinstance(manifest, dict):
        # `[]` or `"text"` parses, and then fails inside the first lookup.
        say(f"{path} is not a pack manifest, so the pack is built again")
        return None
    return manifest


def pack_state(directory: Path, expected: dict) -> str | None:
    """Why this pack cannot be used, or None when it can."""
    manifest = read_manifest(directory)
    if manifest is None:
        return "there is no readable pack"
    if not manifest_matches(manifest, expected):
        return "the pack was made for another model, version or revision"
    files = manifest.get("files")
    if not isinstance(files, dict):
        return "the pack does not name its files"
    weights = directory / "weights.safetensors"
    if not weights.is_file() or weights.stat().st_size != files.get("weights.safetensors"):
        return "weights.safetensors is missing or the wrong size"
    return None


def quarantine(directory: Path) -> None:
    """Move a pack that will not load out of the way, so a new one can be built."""
    aside = directory.with_name(f"{directory.name}.corrupt-{int(time.time())}")
    try:
        directory.rename(aside)
        say(f"moved the pack that would not load to {aside.name}")
    except OSError:
        pass


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
    staging = staging_directory(directory)
    save_file(tensors, str(staging / "weights.safetensors"))
    # The size is what a later start checks cheaply. A truncated or replaced file is a
    # different size, and a pack that fails to load is moved aside and built again.
    manifest["files"] = {"weights.safetensors": (staging / "weights.safetensors").stat().st_size}
    (staging / "pack.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    publish(staging, directory)


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
    from yue2 import YuE2Pipeline

    pipe = YuE2Pipeline.from_pretrained(model_name, device="cuda")
    pipe.__enter__()
    directory = pack_path(root, model_name)
    expected = expected_manifest(model_name)
    attempt = 0
    while True:
        attempt += 1
        recover(directory)
        reason = pack_state(directory, expected)
        if reason is not None:
            with pack_lock(directory):
                # Another studio may have published a pack while this one waited.
                recover(directory)
                if pack_state(directory, expected) is not None:
                    say(f"{reason}, so the pack is built again")
                    build_packed(pipe, directory, expected)
                    return pipe
                say("another studio built the pack while this one waited")
        try:
            return serve_packed(pipe, directory, read_manifest(directory))
        except Exception as error:
            # A pack that will not load is a cache fault, not a reason to stop. Move it
            # aside and build once; a second failure raises with nothing left to try.
            if attempt == 2:
                raise
            say(f"the pack did not load ({error}), so it is built again")
            quarantine(directory)


def build_packed(pipe, directory: Path, expected: dict):
    started = time.time()
    model = pipe._load_model()
    quantize_ar(model)
    write_pack(model, directory, {**expected, "layers": packed_layers(model)})
    say(f"built the pack in {directory} in {time.time() - started:.1f}s")
    return pipe


def serve_packed(pipe, directory: Path, manifest: dict):
    from safetensors.torch import load_file

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


class Worker:
    """Keep one transcription in this child, without retaining its reference audio."""

    def __init__(self, pipe, extras_dir: Path):
        self.pipe = pipe
        self.extras_dir = extras_dir
        self.transcription_key = None
        self.transcription_result = None

    def transcribe(self, job: dict) -> tuple[str, dict]:
        reference_hash = hashlib.sha256(base64.b64decode(job.get("reference_audio") or "")).digest()
        key = (reference_hash, job.get("transcription_task", "melody-full"))
        if key != self.transcription_key:
            self.transcription_key = None
            self.transcription_result = None
            result = transcribe(job, self.extras_dir)
            self.transcription_result = deepcopy(result)
            self.transcription_key = key
        return deepcopy(self.transcription_result)

    def run(self, job: dict) -> dict:
        return run(self.pipe, job, self.extras_dir, transcriber=self.transcribe)


def reporters():
    """Step lines for the studio, in the MLX child's shape. `step 0/0` ends the loading
    stage; generated tokens count up with no total, as a song has none; the synthesis and
    decode stages report their own done and total. Every 16th token keeps the pipe quiet."""
    tokens = 0

    def on_token(_phase, _token):
        nonlocal tokens
        tokens += 1
        if tokens == 1 or tokens % 16 == 0:
            say(f"step {tokens}/0")

    def on_progress(_stage, done, total):
        say(f"step {done}/{total}")

    say("step 0/0")
    return on_token, on_progress


def run(pipe, job: dict, extras_dir: Path, *, transcriber=None) -> dict:
    """The engine's sampling overrides reach both stages, as they do on the MLX backend.

    An empty map keeps each stage's own recipe. Without this the studio's sampling
    controls are accepted and silently ignored on this engine.
    """
    mode = job.get("mode", "generate")
    on_token, on_progress = reporters()
    transcribed = {}
    if mode in {"transcribe", "cover"}:
        score, transcribed = transcribe(job, extras_dir) if transcriber is None else transcriber(job)
        if mode == "transcribe":
            return {"wav": "", "score": score, "metadata": {**transcribed, "mode": "transcribe"}}
        # A cover sings the transcribed score with the request's own style and lyrics.
        task = job.get("transcription_task", "melody-full")
        job = {**job, "abc": score, "cot": "full" if task == "full" else "melody"}
    sampling = job.get("sampling") or {}
    plan_sampling = {"abc_sampling": sampling} if sampling else {}
    if job.get("mode", "generate") == "plan":
        plan = pipe.plan(**request_for(job), **plan_sampling, on_token=on_token)
        return {"score": getattr(plan, "abc", "") or "", "metadata": {"mode": "plan"}}
    import soundfile

    song_sampling = {**plan_sampling, "semantic_sampling": sampling} if sampling else {}
    previous_config = pipe.generation_config
    if "steps" in job:
        pipe.generation_config = replace(previous_config, ode_steps=job["steps"])
    try:
        song = pipe(**request_for(job), **song_sampling, on_token=on_token, on_progress=on_progress)
    finally:
        pipe.generation_config = previous_config
    buffer = io.BytesIO()
    soundfile.write(buffer, song.audio, 48000, format="WAV", subtype="FLOAT")
    return {
        "wav": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "score": getattr(song, "abc", "") or "",
        "truncated": dict(getattr(song, "truncated", {}) or {}),
        "metadata": {"mode": mode, "cot": job.get("cot", "full"), **transcribed},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="m-a-p/YuE2-3B")
    parser.add_argument("--quantize", default="bf16", choices=sorted(QUANTIZERS))
    parser.add_argument("--pack-dir", default="")
    parser.add_argument("--extras-dir", default="~/.cache/open-imagine/yue2")
    arguments = parser.parse_args()
    import torch

    if not torch.cuda.is_available():
        say("CUDA is not available in this environment")
        return 2
    pipe = load(arguments.model, arguments.quantize, Path(arguments.pack_dir) if arguments.pack_dir else None)
    worker = Worker(pipe, Path(arguments.extras_dir))
    say("ready")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        job = {}
        try:
            job = json.loads(line)
            answer({**worker.run(job), "request_id": job.get("request_id", "")})
        except Exception as error:  # the parent turns this into a failed job
            answer({"error": f"{type(error).__name__}: {error}", "request_id": job.get("request_id", "")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
