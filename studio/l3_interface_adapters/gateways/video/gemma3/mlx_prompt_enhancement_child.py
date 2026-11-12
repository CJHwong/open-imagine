#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mlx==0.32.2", "mlx-lm==0.31.1", "mlx-vlm==0.7.3",
#   "transformers==5.17.0", "pillow==12.3.0",
#   "ltx-core-mlx @ git+https://github.com/dgrauet/ltx-2-mlx@5fed9e2a588102c231658d2a2b7be1ef7bf350b4#subdirectory=packages/ltx-core-mlx",
#   "ltx-pipelines-mlx @ git+https://github.com/dgrauet/ltx-2-mlx@5fed9e2a588102c231658d2a2b7be1ef7bf350b4#subdirectory=packages/ltx-pipelines-mlx",
# ]
# ///
"""Expose the same Gemma strategies used by the LTX CLI without rendering video.

`uv` builds the environment this file declares, so the enhancer needs neither the video
engine nor a separate Python. The versions are the ones the studio resolves.
"""

import importlib
import json
import sys
from pathlib import Path


def main():
    source, destination = map(Path, sys.argv[1:])
    request = json.loads(source.read_text())
    cli = importlib.import_module("ltx_pipelines_mlx.cli")
    encoder = importlib.import_module("ltx_core_mlx.text_encoders.gemma.encoders.base_encoder")
    cleanup = importlib.import_module("ltx_core_mlx.utils.memory").aggressive_cleanup
    image = request["image"]
    model = (
        importlib.import_module("mlx_image_prompt_enhancement").ImagePromptEnhancer()
        if image
        else encoder.GemmaLanguageModel()
    )
    try:
        model.load(cli.DEFAULT_GEMMA)
        print("[Studio enhancer writing]", file=sys.stderr, flush=True)
        prompt = (
            model.enhance_i2v(request["prompt"], image, seed=10)
            if image
            else model.enhance_t2v(request["prompt"], seed=10)
        )
        destination.write_text(json.dumps({"prompt": prompt}))
    finally:
        del model
        cleanup()


if __name__ == "__main__":
    main()
