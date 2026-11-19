"""What a voice or music run would do, without running it.

The voice and music sides of `plan_image_use_case.py`. The controller makes the run's own job,
with the run's own checks, and this answers with the settings that the job holds and its
time. It reads the backend's capabilities only, so it loads no weights, takes no lock and
records no operation.
"""

from dataclasses import dataclass, replace

from studio.l1_entities.audio_estimate import AudioEstimate, estimate_song, estimate_speech
from studio.l1_entities.lora import LoraUse
from studio.l1_entities.music_capabilities import MusicCapabilities
from studio.l1_entities.music_job import MusicJob
from studio.l1_entities.voice_capabilities import Capabilities
from studio.l1_entities.voice_job import SpeechJob


@dataclass(frozen=True)
class PlanAudioResponse:
    backend: str
    mode: str
    count: int
    effective_options: dict[str, object]
    """The settings of the job: a voice mode's own settings, such as `voice` and `ref_text`, or
    a song's settings. The script, the style, the lyrics, the score, the media and a drawn seed
    stay out."""
    estimate: AudioEstimate
    loras: tuple[LoraUse, ...] = ()
    offers_loras: bool = False


def plan_speech(backend_id: str, capabilities: Capabilities, job: SpeechJob) -> PlanAudioResponse:
    estimate = estimate_speech(capabilities.mode(job.mode), job)
    estimate = replace(estimate, load_seconds=capabilities.load_seconds, may_add=capabilities.may_add)
    return PlanAudioResponse(backend_id, job.mode, 1, dict(job.options), estimate)


def plan_song(backend_id: str, capabilities: MusicCapabilities, job: MusicJob) -> PlanAudioResponse:
    estimate = estimate_song(capabilities.estimate, job.mode, job.lyrics, job.instrumental)
    estimate = replace(estimate, load_seconds=capabilities.load_seconds, may_add=capabilities.may_add)
    options: dict[str, object] = {
        "instrumental": job.instrumental,
        "cot": job.cot,
        "steps": job.steps,
        "cfg_scale": job.cfg_scale,
        "transcription_task": job.transcription_task,
        "sampling": dict(job.sampling),
    }
    return PlanAudioResponse(backend_id, job.mode, 1, options, estimate)
