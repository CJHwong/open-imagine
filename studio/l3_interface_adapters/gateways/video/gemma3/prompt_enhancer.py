"""Run native LTX prompt enhancement in the environment its child script declares."""

import hashlib
import json
import os
import shutil
import tempfile
from collections import OrderedDict
from pathlib import Path

from studio.l1_entities.errors import StudioError
from studio.l3_interface_adapters.gateways.video.shared.process_errors import crash_report


def _uv_launcher():
    """The uv that runs the studio, so the child builds with the same version.

    `uv run` sets UV to its own path. A studio started another way falls back to PATH.
    """
    found = os.environ.get("UV") or shutil.which("uv")
    return str(Path(found).absolute()) if found else None


class Gemma3PromptEnhancer:
    def __init__(self, execute_process):
        self._execute_process = execute_process
        self._uv = _uv_launcher()
        self._enhanced = OrderedDict()

    def __call__(self, prompt, references, on_writing, should_stop):
        if self._uv is None:
            raise StudioError("The prompt enhancer needs uv. Install uv, or set UV to the uv binary path.")
        with tempfile.TemporaryDirectory(prefix="studio-ltx-rewrite-") as scratch:
            root = Path(scratch)
            source, destination = root / "request.json", root / "result.json"
            image = None
            if references:
                image = root / "reference.png"
                image.write_bytes(references[0].png)
            source.write_text(json.dumps({"prompt": prompt, "image": str(image) if image else None}))
            child = Path(__file__).with_name("mlx_prompt_enhancement_child.py")
            tail = ""
            writing = False

            def consume(chunk):
                nonlocal tail, writing
                combined = tail + chunk
                tail = combined[-24:]
                if not writing and "[Studio enhancer writing]" in combined:
                    writing = True
                    on_writing()

            self._execute_process(
                [self._uv, "run", "--script", str(child), str(source), str(destination)],
                should_stop,
                consume,
                failure_message=crash_report,
                timeout_message="The MLX video pipeline timed out after one hour.",
                cancel_message="video generation was cancelled",
            )
            result = json.loads(destination.read_text())["prompt"]
            if not isinstance(result, str) or not result.strip():
                raise StudioError("The LTX enhancer returned an empty prompt. Try rewriting again.")
        self._enhanced[result, _reference_key(references)] = None
        while len(self._enhanced) > 128:
            self._enhanced.popitem(last=False)
        return result

    def is_enhanced(self, prompt, references):
        return (prompt, _reference_key(references)) in self._enhanced


def _reference_key(references):
    return hashlib.sha256(references[0].png).hexdigest() if references else None
