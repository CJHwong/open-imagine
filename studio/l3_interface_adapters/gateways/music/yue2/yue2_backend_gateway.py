"""YuE2 owns a separate environment and releases its process on workspace switches."""

import base64
import io
from dataclasses import asdict
from pathlib import Path

import numpy as np
import soundfile

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.music_job import MusicResult
from studio.l2_use_cases.boundaries.music_backend_gateway import MusicBackendGateway
from studio.l3_interface_adapters.gateways.music.yue2.capabilities import yue2_capabilities


class Yue2BackendGateway(MusicBackendGateway):
    def __init__(self, child, model_dir, vae_dir):
        self._child, self._model_dir, self._vae_dir = child, model_dir, vae_dir

    def capabilities(self):
        return yue2_capabilities()

    def load(self):
        model_files = (
            "ar-8bit.safetensors",
            "ar-bf16.safetensors",
            "nar-bf16.safetensors",
            "conversion.json",
            "qwen.tiktoken",
            "config.json",
        )
        for label, path, files in (
            ("model_dir", self._model_dir, model_files),
            ("vae_dir", self._vae_dir, ("model.safetensors", "config.json")),
        ):
            if not path or not all((Path(path) / name).is_file() for name in files):
                raise InvalidJob(f"Set [yue2].{label} to the downloaded YuE2 weights; see docs/how-to/music.md.")
        self._child.wait_ready()

    def release(self):
        self._child.stop()

    def run(self, job, on_step, should_stop):
        if should_stop():
            raise Cancelled("Music generation was cancelled.")
        payload = asdict(job)
        payload["reference_audio"] = base64.b64encode(payload.get("reference_audio", b"")).decode("ascii")
        reply = self._child.request(payload, on_step, should_stop)
        if any(reply.get("truncated", {}).values()):
            raise InvalidJob("YuE2 reached a generation limit. Shorten the lyrics or try another seed.")
        if getattr(job, "mode", "generate") in {"plan", "transcribe"}:
            if not reply.get("score", "").strip():
                raise InvalidJob("YuE2 did not return a composition score.")
            return MusicResult(b"", 0, 48000, job.seed, reply["score"], reply.get("metadata", {}))
        raw = base64.b64decode(reply["wav"], validate=True)
        samples, rate = soundfile.read(io.BytesIO(raw), dtype="float32", always_2d=True)
        if rate != 48000 or samples.shape[1] != 2 or not len(samples) or not np.isfinite(samples).all():
            raise InvalidJob("YuE2 must return finite 48 kHz stereo audio.")
        return MusicResult(raw, len(samples) / rate, rate, job.seed, reply.get("score", ""), reply.get("metadata", {}))
