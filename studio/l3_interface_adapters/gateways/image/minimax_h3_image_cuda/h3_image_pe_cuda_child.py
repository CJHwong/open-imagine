#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "transformers>=5.23.0",
#   "accelerate>=1.0",
#   "torchvision",
#   "pillow",
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


def load(model: str):
    import torch
    from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration

    started = time.time()
    processor = AutoProcessor.from_pretrained(local_snapshot(model))
    weights = Qwen3_5ForConditionalGeneration.from_pretrained(
        local_snapshot(model), torch_dtype=torch.bfloat16, device_map="cpu"
    )
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
        try:
            answer(generate(processor, model, json.loads(line), prompt_dir))
        except Exception as error:  # the parent turns this into a failed job
            answer({"error": f"{type(error).__name__}: {error}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
