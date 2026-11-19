"""YuE2 on CUDA: one child, its own environment, released on a workspace switch."""

import base64
import io
from dataclasses import asdict

import numpy as np
import soundfile

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.music_job import MusicResult
from studio.l2_use_cases.boundaries.music_backend_gateway import MusicBackendGateway
from studio.l3_interface_adapters.gateways.music.yue2_cuda.capabilities import (
    MAX_LYRICS_CHARACTERS,
    yue2_cuda_capabilities,
)


class Yue2CudaBackendGateway(MusicBackendGateway):
    def __init__(self, child, *, backend_id="yue2_cuda", name="YuE2", badge="bf16"):
        self._child = child
        self._backend_id = backend_id
        self._name = name
        self._badge = badge

    def capabilities(self):
        return yue2_cuda_capabilities(self._backend_id, self._name, self._badge)

    def load(self):
        self._child.wait_ready()

    def release(self):
        self._child.stop()

    def run(self, job, on_step, should_stop):
        if should_stop():
            raise Cancelled("Music generation was cancelled.")
        if job.mode != "plan" and len(job.lyrics) > MAX_LYRICS_CHARACTERS:
            raise InvalidJob(
                f"YuE2 on CUDA sings up to {MAX_LYRICS_CHARACTERS} characters of lyrics, and this request has "
                f"{len(job.lyrics)}. Shorten the lyrics or split the song."
            )
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
