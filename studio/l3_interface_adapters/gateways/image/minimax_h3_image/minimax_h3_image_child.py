"""Standalone child: one engine stage, then exit. No Studio imports, no nested subprocesses."""

import json
import sys
import time
from pathlib import Path


def event(**data):
    print("\nH3_IMAGE_EVENT " + json.dumps(data), file=sys.stderr, flush=True)


def run_stage(stage, work):
    import mlx.core as mx
    from h3_image_mlx import _stage, dit

    started = time.monotonic()
    if stage == "dit":
        denoise = dit.denoise

        def denoise_with_progress(*args, **kwargs):
            # The engine calls the hook after it evaluates the step, so each event is a finished step.
            return denoise(*args, progress=lambda step, _seconds: event(type="step", step=step), **kwargs)

        # The stage runner reads `denoise` from the module at call time and passes no hook.
        dit.denoise = denoise_with_progress
    _stage.main(stage, Path(work))
    event(
        type="result",
        stage=stage,
        engine_seconds=time.monotonic() - started,
        peak_memory_bytes=mx.get_peak_memory(),
    )


if __name__ == "__main__":
    run_stage(sys.argv[1], sys.argv[2])
