"""Run native LTX prompt enhancement in its pinned engine environment."""

import hashlib
import json
import tempfile
from collections import OrderedDict
from pathlib import Path

from studio.l1_entities.errors import StudioError
from studio.l3_interface_adapters.gateways.video.shared.engine_paths import (
    checked_executable,
    child_command,
    engine_executable,
)
from studio.l3_interface_adapters.gateways.video.shared.process_errors import crash_report


class Gemma3PromptEnhancer:
    def __init__(self, settings, execute_process):
        self._cli = engine_executable(settings)
        self._execute_process = execute_process
        self._enhanced = OrderedDict()

    def __call__(self, prompt, references, on_writing, should_stop):
        engine = checked_executable(
            self._cli, "The bundled Video engine is missing. Reinstall the studio, or set cli_path under [mlx_video]."
        )
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
                child_command(engine, child, str(source), str(destination)),
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
