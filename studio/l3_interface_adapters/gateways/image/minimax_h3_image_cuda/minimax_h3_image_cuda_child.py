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
encoder is therefore quantized first, alone, and the transformer after it lands. Peak during
the quantize is the bf16 transformer plus the packed copy, so the order is encoder first,
transformer second, quantize third.

`fp8` holds both in fp8 and multiplies in fp8 (W8A8, one scale per row). On the DGX Spark
a 1024 image took 39.8 s with an NVFP4 weight-only encoder and an fp8 weight-only
transformer, and 5.9 s this way: the encoder pass went from 17.3 s to 0.2 s and the
transformer from 21.8 s to 5.0 s. A weight-only tensor widens itself on every pass, and that
widening was the time. The kernels are pinned to torch's, because mslk's cutlass path will
not initialize on this card.
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
import uuid
from pathlib import Path


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
        if tensors[0].data.device.type == device:
            continue
        landed = tensors[0].data.clone().to(device)
        for tensor in tensors:
            tensor.data = landed


PACK_FORMAT = 1
"""The pack holds the quantized weights of the transformer, the encoder and the vae.

Each weight is stored by its plain parts: `qdata` and `scale` for an `Float8Tensor`,
`qdata`, `scale` and `per_tensor_scale` for an `NVFP4Tensor`, and the tensor itself for
everything else. Rebuilding from those parts was checked bit-identical on 2026-11-14.
"""

PACK_COMPONENTS = ("transformer", "text_encoder", "vae")

# A quantizer whose recipe changed names the new one here, so a pack built by the old
# recipe is rebuilt instead of trusted. A quantizer missing here matches a pack that names
# no recipe, which every pack built before this key did.
RECIPES = {"fp8": "w8a8-per-row"}


def versions() -> dict:
    """What the pack was built with. A pack from another set is rebuilt, not trusted."""
    import diffusers
    import torch
    import torchao

    return {
        "torch": torch.__version__,
        "torchao": torchao.__version__,
        "diffusers": diffusers.__version__,
    }


def pack_directory(root: Path, model: str) -> Path:
    return Path(root) / model.replace("/", "--")


def expected_manifest(model: str, quantize: str) -> dict:
    return {
        "format": PACK_FORMAT,
        "model": model,
        "quantize": quantize,
        "recipe": RECIPES.get(quantize),
        "versions": versions(),
        "source": source_revision(model),
    }


def source_revision(model: str) -> str:
    """The committed snapshot this model resolves to, when this machine can name one.

    The cache writes `refs/main`, and that is the commit `local_snapshot` hands the
    pipeline. Counting snapshot directories answered `unknown` as soon as a second one was
    cached, which let a pack built from one revision serve another.

    A local folder is named by each file's path, size and modification time. Rewriting a
    shard changes the identity even at the same length, and hashing every shard on every
    start would cost minutes on a machine that keeps its weights locally.
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
    for name in PACK_COMPONENTS:
        path = directory / f"{name}.safetensors"
        if not path.is_file() or path.stat().st_size != files.get(f"{name}.safetensors"):
            return f"{path.name} is missing or the wrong size"
    return None


def quarantine(directory: Path) -> None:
    """Move a pack that will not load out of the way, so a new one can be built."""
    aside = directory.with_name(f"{directory.name}.corrupt-{int(time.time())}")
    try:
        directory.rename(aside)
        say(f"moved the pack that would not load to {aside.name}")
    except OSError:
        pass


def manifest_matches(manifest: dict, expected: dict) -> bool:
    return all(manifest.get(key) == value for key, value in expected.items())


def weight_kind(tensor) -> str:
    from torchao.prototype.mx_formats.nvfp4_tensor import NVFP4Tensor
    from torchao.quantization import Float8Tensor

    if isinstance(tensor, NVFP4Tensor):
        return "nvfp4"
    if isinstance(tensor, Float8Tensor):
        return "fp8"
    return "plain"


def quantize_kwargs(weight) -> dict | None:
    """The act-quant settings an NVFP4Tensor carries, as plain values.

    A weight-only pack keeps `None` here, and that is not the same as no settings: passing
    an empty `QuantizeTensorToNVFP4Kwargs` turns the activation quantization on.
    """
    values = getattr(weight, "act_quant_kwargs", None)
    return dict(vars(values)) if values is not None else None


def float8_settings(weight) -> dict:
    """How an fp8 weight multiplies, as plain values.

    Without these a rebuilt weight takes torchao's defaults: no activation quantization,
    which is the slow weight-only path, and the automatic kernel, which fails on this card.
    """
    activation = weight.act_quant_kwargs
    return {
        "mm_config": list(weight.mm_config) if weight.mm_config is not None else None,
        "kernel_preference": weight.kernel_preference.value,
        "act_quant": None
        if activation is None
        else {
            "float8_dtype": str(activation.float8_dtype),
            "row_dim": activation.granularity.dim,
            "kernel_preference": activation.kernel_preference.value,
        },
    }


def copy_to_host(tensor):
    """Wait before serialization reads a nonblocking device copy."""
    if tensor.device.type == "cpu":
        return tensor
    import torch

    copied = tensor.to("cpu", non_blocking=True)
    torch.cuda.synchronize(tensor.device)
    return copied


SAFETENSORS_DTYPES = {
    "torch.bfloat16": "BF16",
    "torch.float16": "F16",
    "torch.float32": "F32",
    "torch.float8_e4m3fn": "F8_E4M3",
    "torch.uint8": "U8",
    "torch.int32": "I32",
    "torch.int64": "I64",
    "torch.bool": "BOOL",
}


def stream_safetensors(path: Path, parts: list) -> None:
    """safetensors' own layout, written one tensor at a time.

    `save_file` takes every tensor of a file at once, so a component's whole host copy stood
    beside its device copy. While the W8A8 pack was written that took the DGX Spark to 4.0
    GiB available. Here one tensor is on the host at a time, and `safe_open` reads the file
    as it reads one `save_file` wrote.
    """

    header = {}
    offset = 0
    for key, tensor in parts:
        kind = SAFETENSORS_DTYPES.get(str(tensor.dtype))
        if kind is None:
            raise ValueError(f"the pack cannot store {key} as {tensor.dtype}")
        size = tensor.numel() * tensor.element_size()
        header[key] = {"dtype": kind, "shape": list(tensor.shape), "data_offsets": [offset, offset + size]}
        offset += size
    encoded = json.dumps(header, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 8)
    with open(path, "wb") as sink:
        sink.write(len(encoded).to_bytes(8, "little"))
        sink.write(encoded)
        for _, tensor in parts:
            write_tensor(sink, tensor)


def write_tensor(sink, tensor) -> None:
    """One tensor's bytes; its host copy is gone when this returns."""
    import torch

    host = copy_to_host(tensor).contiguous().reshape(-1)
    sink.write(host.view(torch.uint8).numpy().tobytes())


def write_pack(pipe, directory: Path, manifest: dict) -> None:
    """One safetensors file per component, assembled beside the pack in use and swapped in."""
    import torch

    staging = staging_directory(directory)
    torch.cuda.empty_cache()
    entries = {}
    for component_name in PACK_COMPONENTS:
        module = component(pipe, component_name)
        tensors = {}
        for name, value in [*module.named_parameters(), *module.named_buffers()]:
            key = f"{component_name}.{name}"
            weight = value.data
            kind = weight_kind(weight)
            entry = {"kind": kind}
            if kind == "nvfp4":
                tensors[f"{key}.qdata"] = weight.qdata
                tensors[f"{key}.scale"] = weight.scale
                if weight.per_tensor_scale is not None:
                    tensors[f"{key}.per_tensor_scale"] = weight.per_tensor_scale
                entry.update(
                    {
                        "block_size": weight.block_size,
                        "dtype": str(weight.dtype),
                        "is_swizzled_scales": weight.is_swizzled_scales,
                        "use_triton_kernel": weight.use_triton_kernel,
                        "act_quant": quantize_kwargs(weight),
                        "per_tensor_scale": weight.per_tensor_scale is not None,
                    }
                )
            elif kind == "fp8":
                tensors[f"{key}.qdata"] = weight.qdata
                tensors[f"{key}.scale"] = weight.scale
                entry.update({"block_size": weight.block_size, "dtype": str(weight.dtype), **float8_settings(weight)})
            else:
                tensors[key] = weight
            entries[key] = entry
        try:
            stream_safetensors(staging / f"{component_name}.safetensors", list(tensors.items()))
        finally:
            tensors.clear()
            torch.accelerator.memory.empty_host_cache()
    manifest["tensors"] = entries
    # The sizes are what a later start can check cheaply. A truncated or replaced file is
    # a different size, and a pack that fails to load is moved aside and built again.
    manifest["files"] = {
        f"{name}.safetensors": (staging / f"{name}.safetensors").stat().st_size for name in PACK_COMPONENTS
    }
    (staging / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    publish(staging, directory)


def rebuild(entry: dict, key: str, handle, device: str):
    """One weight, back from the parts the pack stored."""
    import torch

    def part(suffix: str):
        return handle.get_tensor(f"{key}.{suffix}").clone().to(device)

    if entry["kind"] == "plain":
        return handle.get_tensor(key).clone().to(device)
    if entry["kind"] == "fp8":
        from torchao.quantization import Float8MMConfig, Float8Tensor, PerRow
        from torchao.quantization.quantize_.common.kernel_preference import KernelPreference
        from torchao.quantization.quantize_.workflows.float8.float8_tensor import QuantizeTensorToFloat8Kwargs

        activation = entry["act_quant"]
        return Float8Tensor(
            qdata=part("qdata"),
            scale=part("scale"),
            block_size=entry["block_size"],
            mm_config=None if entry["mm_config"] is None else Float8MMConfig(*entry["mm_config"]),
            act_quant_kwargs=None
            if activation is None
            else QuantizeTensorToFloat8Kwargs(
                float8_dtype=getattr(torch, activation["float8_dtype"].removeprefix("torch.")),
                granularity=PerRow(activation["row_dim"]),
                kernel_preference=KernelPreference(activation["kernel_preference"]),
            ),
            kernel_preference=KernelPreference(entry["kernel_preference"]),
            dtype=getattr(torch, entry["dtype"].removeprefix("torch.")),
        )
    if entry["kind"] == "nvfp4":
        from torchao.prototype.mx_formats.inference_workflow import QuantizeTensorToNVFP4Kwargs
        from torchao.prototype.mx_formats.nvfp4_tensor import NVFP4Tensor

        dtype = getattr(torch, entry["dtype"].removeprefix("torch."))
        scale = part("per_tensor_scale") if entry["per_tensor_scale"] else None
        return NVFP4Tensor(
            part("qdata"),
            part("scale"),
            entry["block_size"],
            dtype,
            scale,
            None,
            entry["is_swizzled_scales"],
            entry["use_triton_kernel"],
            None if entry["act_quant"] is None else QuantizeTensorToNVFP4Kwargs(**entry["act_quant"]),
        )
    raise SystemExit(f"the pack holds a weight of kind {entry['kind']!r}, which this child cannot rebuild")


def drop_unread_encoder_parts(pipe) -> None:
    """Remove the encoder layers and the head that H3 never reads.

    H3 conditions on `hidden_states[pipe.text_encoder_layer]`, 50, of its 64-layer Qwen3-VL
    encoder, and reads it off `text_encoder.model`, so the language-model head never runs.
    `hidden_states[k]` is the input of layer k, so the first 51 layers give that state
    unchanged and still before the final norm; the 13 after it only cost time and memory.
    A pack written with every layer still loads, because its extra tensors are never read.
    """
    import torch

    encoder = component(pipe, "text_encoder")
    del encoder.model.language_model.layers[pipe.text_encoder_layer + 1 :]
    encoder.lm_head = torch.nn.Identity()


def load_packed(model: str, directory: Path, manifest: dict):
    """Build the components empty and give them the weights the pack holds."""
    import torch
    from diffusers import ModularPipeline
    from safetensors import safe_open

    started = time.time()
    pipe = ModularPipeline.from_pretrained(local_snapshot(model))
    pipe.load_components(names=list(PACK_COMPONENTS), device_map="meta")
    pipe.load_components(names=["processor", "tokenizer", "scheduler"], dtype=torch.bfloat16, device_map="cpu")
    drop_unread_encoder_parts(pipe)
    say(f"built empty in {time.time() - started:.1f}s")
    for component_name in PACK_COMPONENTS:
        module = component(pipe, component_name)
        state = {}
        with safe_open(str(directory / f"{component_name}.safetensors"), framework="pt") as handle:
            for name, _ in [*module.named_parameters(), *module.named_buffers()]:
                key = f"{component_name}.{name}"
                state[name] = rebuild(manifest["tensors"][key], key, handle, "cuda")
        module.load_state_dict(state, strict=False, assign=True)
        # `load_state_dict` leaves a non-persistent buffer alone, and a rotary module's
        # `inv_freq` is one: it is built at construction, and a meta construction has no
        # values to build it from. The pack carries them, so give them back by hand.
        for name, buffer in module.named_buffers():
            if buffer.device.type != "meta":
                continue
            owner_name, _, leaf = name.rpartition(".")
            owner = module.get_submodule(owner_name) if owner_name else module
            owner._buffers[leaf] = state[name]
        del state
        torch.cuda.synchronize()
        say(f"{component_name} on the device in {time.time() - started:.1f}s")
    say(f"loaded {model} from the pack in {time.time() - started:.1f}s")
    return pipe


PACK_NOT_READY = "the H3 pack is missing or out of date for this torch build; prepare the model again"


class PackNotReady(RuntimeError):
    """A run found no usable pack, and only a prepare may build one."""


def load(model: str, quantize: str, root: Path | None = None, may_build: bool = False):
    """Load from the pack. Only a child started by a prepare (`may_build`) builds a missing
    or out-of-date pack, because a build takes minutes and tens of GiB a run never pays."""
    if quantize not in ("nvfp4", "fp8", "bf16"):
        raise SystemExit(f"quantize must be nvfp4, fp8 or bf16, not {quantize}")
    if quantize == "bf16" or root is None:
        return build(model, quantize)
    directory = pack_directory(root, model)
    expected = expected_manifest(model, quantize)
    attempt = 0
    while True:
        attempt += 1
        recover(directory)
        reason = pack_state(directory, expected)
        if reason is not None and not may_build:
            raise PackNotReady(f"{PACK_NOT_READY} ({reason})")
        if reason is not None:
            with pack_lock(directory):
                # Another studio may have published a pack while this one waited.
                recover(directory)
                if pack_state(directory, expected) is not None:
                    say(f"{reason}, so the pack is built again")
                    return build_and_write(model, quantize, directory, expected)
                say("another studio built the pack while this one waited")
        try:
            return load_packed(model, directory, read_manifest(directory))
        except Exception as error:
            # A pack that will not load is a cache fault, not a reason to stop. Move it
            # aside and build once; a second failure raises with nothing left to try.
            if not may_build:
                raise PackNotReady(f"{PACK_NOT_READY} (the pack did not load: {error})") from error
            if attempt == 2:
                raise
            say(f"the pack did not load ({error}), so it is built again")
            quarantine(directory)


def build_and_write(model: str, quantize: str, directory: Path, expected: dict):
    pipe = build(model, quantize)
    started = time.time()
    try:
        write_pack(pipe, directory, expected)
        say(f"wrote the pack in {time.time() - started:.1f}s")
    except OSError as error:
        # A full or read-only disk costs the next start a rebuild, not this run.
        say(f"could not write the pack: {error}")
    return pipe


def build(model: str, quantize: str):
    import torch
    from diffusers import ModularPipeline

    started = time.time()
    pipe = ModularPipeline.from_pretrained(local_snapshot(model))
    say(f"loaded the pipeline shell in {time.time() - started:.1f}s")
    if quantize == "bf16":
        pipe.load_components(dtype=torch.bfloat16, device_map="cuda")
        drop_unread_encoder_parts(pipe)
        return pipe

    # The encoder first, alone, then quantized, then the transformer. Loading both at
    # bf16 needs 135 GB and this machine has 121.7. The NVFP4 build keeps its encoder
    # weight-only, the smaller of the two; the fp8 build quantizes it W8A8 on the device.
    from torchao.prototype.mx_formats import NVFP4WeightOnlyConfig
    from torchao.quantization import quantize_

    pipe.load_components(names=["text_encoder"], dtype=torch.bfloat16, device_map="cpu")
    say(f"encoder loaded in {time.time() - started:.1f}s")
    drop_unread_encoder_parts(pipe)
    encoder = component(pipe, "text_encoder")
    if quantize == "nvfp4":
        quantize_(encoder, NVFP4WeightOnlyConfig())
    else:
        land_in_fp8(encoder, kept=("visual", "lm_head"))
    torch.cuda.empty_cache()
    say(f"encoder packed in {time.time() - started:.1f}s")
    # The weights land on the host first and then travel one tensor at a time, because the
    # straight mapping to the device moves at 0.19 GB/s. Loading both components to the
    # device at bf16 needs 135 GB against this machine's 121.7, so the encoder above is
    # already packed before the transformer arrives.
    pipe.load_components(
        names=["transformer", "vae", "processor", "tokenizer", "scheduler"], dtype=torch.bfloat16, device_map="cpu"
    )
    if quantize == "nvfp4":
        from torchao.prototype.mx_formats import NVFP4DynamicActivationNVFP4WeightConfig

        move_by_way_of_memory(component(pipe, "transformer"), "cuda")
        quantize_(component(pipe, "transformer"), NVFP4DynamicActivationNVFP4WeightConfig())
    else:
        land_in_fp8(component(pipe, "transformer"))
    move_by_way_of_memory(component(pipe, "vae"), "cuda")
    torch.cuda.synchronize()
    say(f"transformer on the device in {time.time() - started:.1f}s")
    encoder.to("cuda")
    torch.cuda.synchronize()
    say(f"loaded {model} as {quantize} in {time.time() - started:.1f}s")
    return pipe


def land_in_fp8(module, kept: tuple[str, ...] = ()) -> None:
    """Move a module to the device one linear at a time, each quantized as it lands.

    fp8 weights and fp8 activations, one scale per row, on torch's own kernels. Landing the
    whole bf16 transformer first and quantizing it after held it beside the fp8 encoder, and
    the DGX Spark fell to 13.8 GiB available while it landed; one bf16 linear at a time kept
    it at 45.9 GiB or more. A row scale needs a bf16 weight, so a linear in another dtype
    lands as it is. The encoder keeps its vision tower and output head at bf16, `kept` by
    name. What is not a linear follows in one move at the end.
    """
    import torch
    from torchao.quantization import Float8DynamicActivationFloat8WeightConfig, PerRow, quantize_
    from torchao.quantization.quantize_.common.kernel_preference import KernelPreference

    config = Float8DynamicActivationFloat8WeightConfig(granularity=PerRow(), kernel_preference=KernelPreference.TORCH)
    for name, layer in list(module.named_modules()):
        if not isinstance(layer, torch.nn.Linear) or layer.weight.dtype != torch.bfloat16:
            continue
        if any(part in name for part in kept):
            continue
        move_by_way_of_memory(layer, "cuda")
        quantize_(layer, config)
    move_by_way_of_memory(module, "cuda")


def reference_image(encoded: str):
    """A reference the parent sent as a base64 PNG, as the pipeline wants it."""
    from PIL import Image

    with Image.open(io.BytesIO(base64.b64decode(encoded))) as found:
        return found.convert("RGB")


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
        "min_generation_area": 1024,
        "generator": torch.Generator().manual_seed(int(job["seed"])),
        "output": "images",
    }
    if job.get("mode") == "edit":
        # The pipeline's own condition input: with `image` set, the resize, text-encoder
        # and vae blocks switch to their image-conditioned paths.
        arguments["image"] = [reference_image(encoded) for encoded in job["references"]]
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
    parser.add_argument("--pack-dir", default="")
    parser.add_argument("--may-build", action="store_true", help="build a missing pack; only a prepare passes it")
    arguments = parser.parse_args()
    import torch

    if not torch.cuda.is_available():
        say("CUDA is not available in this environment")
        return 2
    pack_dir = Path(arguments.pack_dir) if arguments.pack_dir else None
    try:
        pipe = load(arguments.model, arguments.quantize, pack_dir, may_build=arguments.may_build)
    except PackNotReady as error:
        say(str(error))
        return 3
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
