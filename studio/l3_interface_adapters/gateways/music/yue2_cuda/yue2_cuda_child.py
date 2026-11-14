#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "yue2-infer @ git+https://github.com/multimodal-art-projection/YuE@1116bea76032bee5668e5f097294d082fa0b84f0",
#   "torch==2.10.0",
#   "soundfile",
#   "numpy",
# ]
# [tool.uv]
# index-strategy = "unsafe-best-match"
# extra-index-url = ["https://download.pytorch.org/whl/cu130"]
# ///
"""YuE2 on a CUDA GPU, one JSON job per line.

The upstream package, `yue2-infer`, is the whole engine: it plans, generates, synthesizes
and decodes, and its own pins keep torch, transformers and huggingface-hub consistent.
This child only maps a studio job onto its request and its artifacts back onto the
studio's reply.
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
    return request


def load(model: str):
    from yue2 import YuE2Pipeline

    started = time.time()
    pipe = YuE2Pipeline.from_pretrained(model, device="cuda")
    pipe.__enter__()
    say(f"loaded {model} in {time.time() - started:.1f}s")
    return pipe


def run(pipe, job: dict) -> dict:
    """The engine's sampling overrides reach both stages, as they do on the MLX backend.

    An empty map keeps each stage's own recipe. Without this the studio's sampling
    controls are accepted and silently ignored on this engine.
    """
    sampling = job.get("sampling") or {}
    plan_sampling = {"abc_sampling": sampling} if sampling else {}
    if job.get("mode", "generate") == "plan":
        plan = pipe.plan(**request_for(job), **plan_sampling)
        return {"score": getattr(plan, "abc", "") or "", "metadata": {"mode": "plan"}}
    import soundfile

    song_sampling = {**plan_sampling, "semantic_sampling": sampling} if sampling else {}
    song = pipe(**request_for(job), **song_sampling)
    buffer = io.BytesIO()
    soundfile.write(buffer, song.audio, 48000, format="WAV", subtype="FLOAT")
    return {
        "wav": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "score": getattr(song, "abc", "") or "",
        "truncated": dict(getattr(song, "truncated", {}) or {}),
        "metadata": {"mode": "generate", "cot": job.get("cot", "full")},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="m-a-p/YuE2-3B")
    arguments = parser.parse_args()
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
