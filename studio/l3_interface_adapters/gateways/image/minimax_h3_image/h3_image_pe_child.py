#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "mlx-vlm==0.7.3",
#   "mlx==0.32.2",
#   "pillow>=12.3,<13",
#   "transformers==5.17.0",
# ]
# ///
"""MiniMax H3-Image prompt enhancer, run as a script child.

The release is a Qwen3.8-27B fine-tune that rewrites a short prompt into a full caption and
chooses a canvas ratio, or rewrites an editing instruction while reading the reference
pictures. Its two task templates ship with the model and are read from the pack.

One JSON job per line on stdin, one reply per line on stdout, logs on stderr.
"""

import argparse
import base64
import contextlib
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

MAX_TOKENS = 4096


def log(message):
    print(message, file=sys.stderr, flush=True)


sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

from h3_image_pe_text import (  # noqa: E402  (a script's own directory is not on the path yet)
    caption_reply,
    edit_messages,
    image_messages,
    picture_ratio,
)


class Enhancer:
    def __init__(self, model_dir, prompt_dir):
        self.model_dir = Path(model_dir).expanduser()
        self.prompt_dir = Path(prompt_dir).expanduser() if prompt_dir else self.model_dir / "prompt"
        self.model = None
        self.processor = None

    def load(self):
        from mlx_vlm import load

        if not (self.model_dir / "config.json").is_file():
            raise ValueError(f"The prompt enhancer pack is missing at {self.model_dir}.")
        self.model, self.processor = load(str(self.model_dir))
        log("ready")

    def ask(self, messages, images=(), max_tokens=MAX_TOKENS):
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        # generate takes ready text, so the chat template, the image tokens and the thinking
        # switch are applied here, exactly as the release's own client does.
        prompt = apply_chat_template(
            self.processor, self.model.config, messages, num_images=len(images), enable_thinking=False
        )
        result = generate(
            self.model,
            self.processor,
            prompt,
            image=list(images) or None,
            max_tokens=max_tokens,
            temperature=1.0,
            top_p=0.95,
            top_k=20,
        )
        return result.text

    def answer(self, job):
        if self.model is None:
            self.load()
        kind = job.get("kind", "generate")
        prompt = (job.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Write a prompt before asking for a longer one.")
        if kind == "generate":
            return self.rewrite_image(prompt)
        if kind == "edit":
            return self.rewrite_edit(prompt, job)
        raise ValueError(f"Unknown prompt-enhancer kind {kind!r}.")

    def rewrite_image(self, prompt):
        text = self.ask(image_messages(self.prompt_dir, prompt))
        return caption_reply(text, "aspect_ratio")

    def rewrite_edit(self, prompt, job):
        pictures = [base64.b64decode(raw) for raw in job.get("images") or []]
        ratio = str(job.get("ratio") or "adaptive")
        messages = edit_messages(self.prompt_dir, prompt, [picture_ratio(raw) for raw in pictures], ratio)
        with TemporaryDirectory(prefix="h3-pe-", dir=os.environ.get("SPEECH_GEN_SCRATCH")) as scratch:
            paths = []
            for index, raw in enumerate(pictures, start=1):
                path = Path(scratch) / f"picture-{index}.png"
                path.write_bytes(raw)
                paths.append(str(path))
            text = self.ask(messages, paths)
        return caption_reply(text, "target_aspect_ratio", ratio)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--prompt-dir")
    args = parser.parse_args()
    with contextlib.redirect_stdout(sys.stderr):
        enhancer = Enhancer(args.model_dir, args.prompt_dir)
        enhancer.load()
    try:
        for line in sys.stdin:
            job = {}
            try:
                job = json.loads(line)
                with contextlib.redirect_stdout(sys.stderr):
                    reply = enhancer.answer(job)
            except (ValueError, FileNotFoundError) as error:
                log(f"{type(error).__name__}: {error}")
                reply = {"error": str(error), "kind": "input"}
            except Exception as error:
                log(f"{type(error).__name__}: {error}")
                reply = {"error": "The H3-Image prompt enhancer failed; check its pack and try again."}
            reply["request_id"] = job.get("request_id", "")
            print(json.dumps(reply), flush=True)
    finally:
        enhancer.model = None


if __name__ == "__main__":
    main()
