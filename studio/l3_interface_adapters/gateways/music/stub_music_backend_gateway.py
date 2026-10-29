"""CPU-only music transport for browser checks; never pretends to be a real song."""

import io
import time
import wave

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.music_job import MusicResult
from studio.l2_use_cases.boundaries.music_backend_gateway import MusicBackendGateway
from studio.l3_interface_adapters.gateways.music.yue2.capabilities import yue2_capabilities


class StubMusicBackendGateway(MusicBackendGateway):
    def capabilities(self):
        return yue2_capabilities()

    def load(self):
        pass

    def release(self):
        pass

    def run(self, job, on_step, should_stop):
        for step in range(1, 6):
            if should_stop():
                raise Cancelled("Music generation was cancelled.")
            time.sleep(0.05)
            on_step(step, 5)
        score = job.abc or (
            'X:1\nT:Stub composition\nM:4/4\nL:1/4\nQ:1/4=88\nV:Vocal\nV:Ins\nK:C\nV:Vocal\n"C"CDEF|\nV:Ins\nC,2E,2|\n'
        )
        metadata = {
            "stub": True,
            "mode": job.mode,
            "instrumental": job.instrumental,
            "steps": job.steps,
            "cfg_scale": job.cfg_scale,
        }
        if job.mode in ("plan", "transcribe"):
            return MusicResult(b"", 0, 48000, job.seed, score, metadata, stub=True)
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setparams((2, 2, 48000, 4800, "NONE", "not compressed"))
            audio.writeframes(bytes(4800 * 4))
        return MusicResult(
            output.getvalue(), 0.1, 48000, job.seed, job.abc if job.mode == "generate" else score, metadata, stub=True
        )
