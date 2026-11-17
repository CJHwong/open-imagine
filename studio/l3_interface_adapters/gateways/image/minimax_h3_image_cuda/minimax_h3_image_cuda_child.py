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
import hashlib
import io
import json
import shutil
import sys
import time
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
        "versions": versions(),
        "source": source_revision(model),
    }


def source_revision(model: str) -> str:
    """The committed snapshot this model resolves to, when this machine can name one.

    A repository id can point at a branch that moves, so the id alone does not say which
    weights a pack holds. `huggingface_hub` caches a repo under
    `models--org--name/snapshots/<commit>/`, and that commit is the identity to record. A
    local directory is named by its file list and sizes, which catches another snapshot but
    not a same-size change inside one. Anything else reports unknown.
    """
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
    except ImportError:  # the unit tests run without the engine's packages
        HF_HUB_CACHE = ""
    cache = Path(HF_HUB_CACHE) / f"models--{model.replace('/', '--')}" / "snapshots"
    if HF_HUB_CACHE and cache.is_dir():
        commits = sorted(one.name for one in cache.iterdir() if one.is_dir())
        if len(commits) == 1:
            return commits[0]
    local = Path(model).expanduser()
    if local.is_dir():
        digest = hashlib.sha256()
        for path in sorted(local.rglob("*")):
            if path.is_file():
                digest.update(f"{path.relative_to(local)}:{path.stat().st_size}".encode())
        return "local:" + digest.hexdigest()[:16]
    return "unknown"


def staging_directory(directory: Path) -> Path:
    """An empty folder beside the pack in use, where a new one is assembled."""
    staging = directory.with_name(directory.name + ".building")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    return staging


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
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Half a manifest is an interrupted write, not a pack. Absent means build one.
        say(f"{path} cannot be read, so the pack is built again")
        return None


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


def copy_to_host(tensor):
    """Wait before serialization reads a nonblocking device copy."""
    if tensor.device.type == "cpu":
        return tensor
    import torch

    copied = tensor.to("cpu", non_blocking=True)
    torch.cuda.synchronize(tensor.device)
    return copied


def write_pack(pipe, directory: Path, manifest: dict) -> None:
    """One safetensors file per component, assembled beside the pack in use and swapped in."""
    import torch
    from safetensors.torch import save_file

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
                tensors[f"{key}.qdata"] = copy_to_host(weight.qdata)
                tensors[f"{key}.scale"] = copy_to_host(weight.scale)
                if weight.per_tensor_scale is not None:
                    tensors[f"{key}.per_tensor_scale"] = copy_to_host(weight.per_tensor_scale)
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
                tensors[f"{key}.qdata"] = copy_to_host(weight.qdata)
                tensors[f"{key}.scale"] = copy_to_host(weight.scale)
                entry.update({"block_size": weight.block_size, "dtype": str(weight.dtype)})
            else:
                tensors[key] = copy_to_host(weight)
            entries[key] = entry
        try:
            save_file(tensors, str(staging / f"{component_name}.safetensors"))
        finally:
            tensors.clear()
            torch.accelerator.memory.empty_host_cache()
    manifest["tensors"] = entries
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
        from torchao.quantization import Float8Tensor

        return Float8Tensor(
            qdata=part("qdata"),
            scale=part("scale"),
            block_size=entry["block_size"],
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


def load_packed(model: str, directory: Path, manifest: dict):
    """Build the components empty and give them the weights the pack holds."""
    import torch
    from diffusers import ModularPipeline
    from safetensors import safe_open

    started = time.time()
    pipe = ModularPipeline.from_pretrained(local_snapshot(model))
    pipe.load_components(names=list(PACK_COMPONENTS), device_map="meta")
    pipe.load_components(names=["processor", "tokenizer", "scheduler"], dtype=torch.bfloat16, device_map="cpu")
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


def load(model: str, quantize: str, root: Path | None = None):
    if quantize not in ("nvfp4", "fp8", "bf16"):
        raise SystemExit(f"quantize must be nvfp4, fp8 or bf16, not {quantize}")
    if quantize == "bf16" or root is None:
        return build(model, quantize)
    directory = pack_directory(root, model)
    manifest = read_manifest(directory)
    expected = expected_manifest(model, quantize)
    files = [directory / f"{name}.safetensors" for name in PACK_COMPONENTS]
    if manifest is None or not manifest_matches(manifest, expected) or not all(path.is_file() for path in files):
        pipe = build(model, quantize)
        started = time.time()
        try:
            write_pack(pipe, directory, expected)
            say(f"wrote the pack in {time.time() - started:.1f}s")
        except OSError as error:
            # A full or read-only disk costs the next start a rebuild, not this run.
            say(f"could not write the pack: {error}")
        return pipe
    return load_packed(model, directory, manifest)


def build(model: str, quantize: str):
    import torch
    from diffusers import ModularPipeline

    started = time.time()
    pipe = ModularPipeline.from_pretrained(local_snapshot(model))
    say(f"loaded the pipeline shell in {time.time() - started:.1f}s")
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
    arguments = parser.parse_args()
    import torch

    if not torch.cuda.is_available():
        say("CUDA is not available in this environment")
        return 2
    pack_dir = Path(arguments.pack_dir) if arguments.pack_dir else None
    pipe = load(arguments.model, arguments.quantize, pack_dir)
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
