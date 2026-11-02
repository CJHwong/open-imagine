#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "hf_xet", "mlx==0.32.2", "mlx-lm==0.31.1", "mlx-vlm==0.4.3", "transformers==5.3.0",
#   "ltx-core-mlx @ git+https://github.com/dgrauet/ltx-2-mlx@5fed9e2a588102c231658d2a2b7be1ef7bf350b4#subdirectory=packages/ltx-core-mlx",
#   "ltx-pipelines-mlx @ git+https://github.com/dgrauet/ltx-2-mlx@5fed9e2a588102c231658d2a2b7be1ef7bf350b4#subdirectory=packages/ltx-pipelines-mlx",
# ]
# ///
"""The LTX engine, built and run from the environment this file declares.

`uv` builds that environment once, at the pinned commit above, and caches it beside
the script. The studio calls this file where it used to call a separately installed
engine: the arguments go to the engine's own CLI, and `--studio-child` runs one of
the studio's child scripts in this same environment.
"""

import runpy
import sys


def main():
    arguments = sys.argv[1:]
    if arguments[:1] == ["--studio-child"]:
        rest = arguments[1:]
        if not rest:
            raise SystemExit("--studio-child needs a script path")
        script, *arguments = rest
        sys.argv = [script, *arguments]
        runpy.run_path(script, run_name="__main__")
        return
    from ltx_pipelines_mlx.cli import main as engine_main

    sys.argv = ["ltx-2-mlx", *arguments]
    engine_main()


if __name__ == "__main__":
    main()
