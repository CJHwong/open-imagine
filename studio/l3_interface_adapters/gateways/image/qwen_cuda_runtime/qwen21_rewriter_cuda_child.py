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
"""The Qwen prompt rewriter cards on a CUDA GPU, one JSON job per line.

The same two cards the MLX rewriter loads, through transformers instead of mlx-vlm. The
studio sends the instructions and the request; this child runs the model and returns the
text, so the answer is parsed on the studio side and both machines read it the same way.

One card is resident at a time: a mode maps to its own card and the two do not both fit.
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
    """The cached directory of a model id, so the card does not ask the Hub.

    Asking the Hub costs about 13 s per start on this machine even when every file is
    cached. The directory is found in the cache rather than through
    `snapshot_download(local_files_only=True)`, which refuses a partial cache.
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

    Measured on the DGX Spark: moving safetensors' mmap-backed tensors straight to the
    device ran at 128 MB/s, and the same tensors moved from ordinary memory at 14 GiB/s.
    One group of aliased weights is cloned and moved at a time, so the temporary is one
    tensor rather than the model.
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


def resident(state: dict, role: str, models: dict) -> dict:
    """The card this role needs, loading it when the other card is the one held."""
    import torch

    if state.get("role") == role:
        return state
    if state:
        say(f"swapping {state['role']} for {role}")
        state["processor"] = None
        state["model"] = None
        torch.cuda.empty_cache()
    processor, model = load(models[role])
    return {"role": role, "processor": processor, "model": model}


def reference_image(encoded: str):
    from PIL import Image

    with Image.open(io.BytesIO(base64.b64decode(encoded))) as found:
        return found.convert("RGB")


def generate(state: dict, job: dict) -> dict:
    import torch

    processor, model = state["processor"], state["model"]
    images = [reference_image(encoded) for encoded in job.get("references") or []]
    content = [{"type": "image"} for _ in images] + [{"type": "text", "text": job["user"]}]
    messages = [
        {"role": "system", "content": job["system"]},
        {"role": "user", "content": content},
    ]
    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=bool(job.get("enable_thinking", True)),
    )
    inputs = processor(text=[text], images=images or None, return_tensors="pt").to("cuda")
    with torch.inference_mode():
        written = model.generate(
            **inputs,
            max_new_tokens=int(job.get("max_tokens", 16384)),
            do_sample=True,
            temperature=float(job.get("temperature", 1.0)),
            top_p=float(job.get("top_p", 0.95)),
            top_k=int(job.get("top_k", 20)),
        )
    return {"text": processor.batch_decode(written[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True)[0]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate-model", default="Qwen/Qwen-Image-2.1-PE-T2I")
    parser.add_argument("--edit-model", default="Qwen/Qwen-Image-2.1-PE-I2I")
    arguments = parser.parse_args()
    import torch

    if not torch.cuda.is_available():
        say("CUDA is not available in this environment")
        return 2
    models = {"generate": arguments.generate_model, "edit": arguments.edit_model}
    state: dict = {}
    say("ready")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        job = {}
        try:
            job = json.loads(line)
            role = job["role"]
            if role not in models:
                raise ValueError(f"the rewriter does not serve {role}")
            state = resident(state, role, models)
            answer({**generate(state, job), "request_id": job.get("request_id", "")})
        except Exception as error:  # the parent turns this into a failed job
            answer({"error": f"{type(error).__name__}: {error}", "request_id": job.get("request_id", "")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
