#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "transformers>=5.23.0",
#   "accelerate>=1.0",
#   "torchvision",
#   "pillow",
#   "numpy",
#   "huggingface-hub>=1.0",
#   "safetensors",
# ]
# [tool.uv]
# index-strategy = "unsafe-best-match"
# extra-index-url = ["https://download.pytorch.org/whl/cu130"]
# ///
"""The MiniMax H3-Image prompt enhancer on a CUDA GPU, one JSON job per line.

The same 27B release the MLX child runs, through transformers instead of mlx-vlm. Its two
task templates ship beside the weights, and `shared/h3_image_pe_text` builds the messages
and reads the answer, so both machines ask the same thing.

One model serves both modes, so nothing is swapped in or out between presses.
"""

import argparse
import base64
import contextlib
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

from h3_image_pe_text import (  # ty: ignore[unresolved-import]
    caption_reply,
    edit_messages,
    image_messages,
    picture_ratio,
)

MAX_TOKENS = 4096


def say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def answer(document: dict) -> None:
    print(json.dumps(document), flush=True)


def local_snapshot(model: str) -> str:
    """The cached directory of a model id, so the enhancer does not ask the Hub."""
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

    Measured on the DGX Spark: moving safetensors' mmap-backed tensors straight to the
    device ran at 128 MB/s, and the same tensors moved from ordinary memory at 14 GiB/s.
    """
    groups: dict[int, list] = {}
    for tensor in [*module.parameters(), *module.buffers()]:
        groups.setdefault(tensor.data.data_ptr(), []).append(tensor)
    for tensors in groups.values():
        landed = tensors[0].data.clone().to(device)
        for tensor in tensors:
            tensor.data = landed


def dequantize_nvfp4(packed, scales, global_scale):
    """Decode the release's low-nibble-first weights, in blocks of sixteen."""
    import numpy as np

    if packed.dtype != np.uint8 or packed.ndim != 2 or packed.shape[1] % 8:
        raise ValueError("NVFP4 weights must hold uint8 rows with eight-byte blocks.")
    if scales.shape != (packed.shape[0], packed.shape[1] // 8) or global_scale.size != 1:
        raise ValueError("NVFP4 scales do not match the packed weights.")
    levels = np.array([0, 0.5, 1, 1.5, 2, 3, 4, 6, -0.0, -0.5, -1, -1.5, -2, -3, -4, -6], dtype=np.float32)
    decoded = np.empty((packed.shape[0], packed.shape[1] * 2), dtype=np.float32)
    decoded[:, 0::2] = levels[packed & 15]
    decoded[:, 1::2] = levels[packed >> 4]
    decoded.reshape(packed.shape[0], packed.shape[1] // 8, 16)[:] *= scales.astype(np.float32)[:, :, None]
    decoded *= global_scale.astype(np.float32).reshape(())
    return decoded


def indexed_tensor_reader(source: Path, index: dict, stack):
    """Keep shard readers open because a weight and its scales can occupy different shards."""
    from safetensors import safe_open

    readers = {}

    def read(name):
        shard = index[name]
        if shard not in readers:
            readers[shard] = stack.enter_context(safe_open(str(source / shard), framework="pt", device="cpu"))
        return readers[shard].get_tensor(name)

    return read


def checkpoint_tensor(read, index: dict, name: str):
    import torch

    packed = read(name)
    if f"{name}_scale" not in index:
        return packed.clone()
    decoded = dequantize_nvfp4(
        packed.numpy(), read(f"{name}_scale").float().numpy(), read(f"{name}_scale_2").float().numpy()
    )
    return torch.from_numpy(decoded).to(torch.bfloat16)


def load_nvfp4(source: str, config):
    """Load one decoded weight at a time without a dense checkpoint copy on disk."""
    from accelerate import init_empty_weights  # ty: ignore[unresolved-import]
    from accelerate.utils import set_module_tensor_to_device  # ty: ignore[unresolved-import]
    from huggingface_hub import snapshot_download
    from transformers import GenerationConfig, Qwen3_5ForConditionalGeneration

    if config.quantization_config.get("quant_method") != "modelopt":
        raise ValueError("The prompt enhancer requires the ModelOpt NVFP4 checkpoint layout.")
    if config.quantization_config.get("group_size") != 16:
        raise ValueError("The prompt enhancer requires NVFP4 groups of sixteen.")
    directory = Path(source) if Path(source).is_dir() else Path(snapshot_download(source))
    index = json.loads((directory / "model.safetensors.index.json").read_text())["weight_map"]
    del config.quantization_config
    with init_empty_weights():
        weights = Qwen3_5ForConditionalGeneration(config)
    expected = set(weights.state_dict())
    found = {name for name in index if not name.endswith((".input_scale", ".weight_scale", ".weight_scale_2"))}
    if expected != found:
        raise ValueError(
            f"Checkpoint weights differ: missing {sorted(expected - found)}, unexpected {sorted(found - expected)}"
        )
    with contextlib.ExitStack() as stack:
        read = indexed_tensor_reader(directory, index, stack)
        for name in sorted(expected):
            tensor = checkpoint_tensor(read, index, name)
            set_module_tensor_to_device(weights, name, "cuda", value=tensor, dtype=tensor.dtype)
    weights.tie_weights()
    for buffer in weights.buffers():
        buffer.data = buffer.data.clone().to("cuda")
    if (directory / "generation_config.json").is_file():
        weights.generation_config = GenerationConfig.from_pretrained(str(directory))
    return weights.eval()


def load(model: str):
    import torch
    from transformers import AutoConfig, AutoProcessor, Qwen3_5ForConditionalGeneration

    started = time.time()
    source = local_snapshot(model)
    processor = AutoProcessor.from_pretrained(source)
    config = AutoConfig.from_pretrained(source)
    if (getattr(config, "quantization_config", None) or {}).get("quant_algo") == "NVFP4":
        weights = load_nvfp4(source, config)
    else:
        weights = Qwen3_5ForConditionalGeneration.from_pretrained(source, torch_dtype=torch.bfloat16, device_map="cpu")
        move_by_way_of_memory(weights, "cuda")
    torch.cuda.synchronize()
    say(f"loaded {model} in {time.time() - started:.1f}s")
    return processor, weights


def reference_image(raw: bytes):
    from PIL import Image

    with Image.open(io.BytesIO(raw)) as found:
        return found.convert("RGB")


def ask(processor, model, messages, images=(), max_tokens: int = MAX_TOKENS) -> str:
    import torch

    if images:
        # The processor needs a template marker for each separately supplied image.
        content = [{"type": "image"} for _ in images]
        content.append({"type": "text", "text": messages[-1]["content"]})
        messages = [*messages[:-1], {**messages[-1], "content": content}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    inputs = processor(text=[text], images=list(images) or None, return_tensors="pt").to("cuda")
    with torch.inference_mode():
        written = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=True,
            temperature=1.0,
            top_p=0.95,
            top_k=20,
        )
    return processor.batch_decode(written[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True)[0]


def generate(processor, model, job: dict, prompt_dir: Path) -> dict:
    kind = job.get("kind", "generate")
    prompt = (job.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("Write a prompt before asking for a longer one.")
    pictures = [base64.b64decode(raw) for raw in job.get("images") or []]
    if kind == "generate":
        return caption_reply(ask(processor, model, image_messages(prompt_dir, prompt)), "aspect_ratio")
    if kind == "edit":
        ratio = str(job.get("ratio") or "adaptive")
        messages = edit_messages(prompt_dir, prompt, [picture_ratio(raw) for raw in pictures], ratio)
        text = ask(processor, model, messages, [reference_image(raw) for raw in pictures])
        return caption_reply(text, "target_aspect_ratio", ratio)
    raise ValueError(f"Unknown prompt-enhancer kind {kind!r}.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="MiniMaxAI/MiniMax-H3-Image-PE")
    parser.add_argument("--prompt-dir")
    arguments = parser.parse_args()
    import torch

    if not torch.cuda.is_available():
        say("CUDA is not available in this environment")
        return 2
    processor, model = load(arguments.model)
    prompt_dir = Path(arguments.prompt_dir or Path(local_snapshot(arguments.model)) / "prompt")
    say("ready")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        job = {}
        try:
            job = json.loads(line)
            answer({**generate(processor, model, job, prompt_dir), "request_id": job.get("request_id", "")})
        except Exception as error:  # the parent turns this into a failed job
            answer({"error": f"{type(error).__name__}: {error}", "request_id": job.get("request_id", "")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
