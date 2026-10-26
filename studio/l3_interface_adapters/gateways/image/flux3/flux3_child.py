"""Standalone child: no Studio imports, no queue, no nested subprocesses."""

import json
import sys
import time
from pathlib import Path


def event(**data):
    print("\nFLUX3_EVENT " + json.dumps(data), file=sys.stderr, flush=True)


def generate(request, output):
    import mlx.core as mx
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux3.variants import Flux3Klein, Flux3KleinEdit

    class Progress:
        def call_in_loop(self, t, seed, prompt, latents, config, time_steps):
            # The upstream hook fires before mx.eval; wait for this step to finish.
            mx.eval(latents)
            event(type="step", step=t + 1, total=config.num_inference_steps)

    started = time.monotonic()
    variant = Flux3KleinEdit if request["references"] else Flux3Klein
    model = variant(
        model_config=ModelConfig.flux3_image_klein(),
        model_path=request.get("model_dir"),
        quantize=request["quantize"],
    )
    model.callbacks.register(Progress())
    loaded = time.monotonic()
    kwargs = dict(
        seed=request["seed"],
        prompt=request["prompt"],
        width=request["width"],
        height=request["height"],
        num_inference_steps=request["steps"],
    )
    if request["references"]:
        kwargs["image_paths"] = request["references"]
    image = model.generate_image(**kwargs).image
    image.save(output, format="PNG")
    mx.synchronize()
    event(
        type="result",
        construction_seconds=loaded - started,
        engine_seconds=time.monotonic() - started,
        peak_memory_bytes=mx.get_peak_memory(),
    )


if __name__ == "__main__":
    generate(json.loads(Path(sys.argv[1]).read_text()), sys.argv[2])
