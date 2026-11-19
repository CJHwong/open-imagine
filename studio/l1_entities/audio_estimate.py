"""What a voice or music request costs, before it runs.

The voice and music forms write a figure beside their run buttons, from the backend's
measured constants. These are the same lines, so a program that plans a queue gets the
figure that the page shows.
"""

from dataclasses import dataclass

from studio.l1_entities.estimate_stages import Stage, split
from studio.l1_entities.music_capabilities import MusicEstimate
from studio.l1_entities.voice_capabilities import ModeSpec
from studio.l1_entities.voice_job import SpeechJob

EXCLUDES = ("weight download", "model load", "queue wait")


@dataclass(frozen=True)
class AudioEstimate:
    """The seconds that one voice clip or one song costs.

    `basis` is "constants" when the backend declares the constants, and "unavailable" when it
    does not or when the figure has nothing to read, such as a voice mode with no length. The
    seconds are then None. `audio_seconds` is the length of speech a voice figure reads, and
    None for music, whose engine picks the length. `setup_seconds` is the fixed part and
    `per_item_seconds` the rest. The other fields mean what they mean on an image estimate;
    the computed stage is "generation".
    """

    basis: str
    reference_count: int
    audio_seconds: float | None = None
    per_item_seconds: float | None = None
    setup_seconds: float | None = None
    total_seconds: float | None = None
    excludes: tuple[str, ...] = EXCLUDES
    stages: tuple[Stage, ...] = ()
    load_seconds: float | None = None
    resident: bool | None = None
    with_load_seconds: float | None = None
    may_add: tuple[Stage, ...] = ()


def estimate_speech(mode: ModeSpec, job: SpeechJob) -> AudioEstimate:
    """voice-studio.js `estimateText`: the overhead and the real-time factor times the audio
    length. A mode with a length setting reads it. A mode without one reads the length that
    its script produces, when the backend measured the seconds per character."""
    estimate = mode.estimate
    has_seconds = any(param.id == "seconds" for param in mode.params)
    seconds = float(job.options.get("seconds") or 0)
    if not seconds and estimate is not None and estimate.seconds_per_character and not has_seconds:
        seconds = len(job.text) * estimate.seconds_per_character
    if estimate is None or not seconds:
        return AudioEstimate("unavailable", len(job.references))
    total = round(estimate.overhead + estimate.rtf * seconds, 1)
    return _constants(len(job.references), round(seconds, 1), estimate.fixed_parts, estimate.overhead, total)


def estimate_song(estimate: MusicEstimate | None, mode: str, lyrics: str, instrumental: bool) -> AudioEstimate:
    """music-studio.js `estimateText`, through `MusicEstimate.seconds`. Only Generate has a
    fixed part; the other modes have one measured figure each."""
    references = 1 if mode in ("cover", "transcribe") else 0
    figure = estimate.seconds(mode, len(lyrics), instrumental) if estimate is not None else None
    if estimate is None or figure is None:
        return AudioEstimate("unavailable", references)
    generate = mode == "generate"
    fixed = estimate.generate_base_seconds if generate else 0.0
    return _constants(references, None, estimate.fixed_parts if generate else (), fixed, round(figure, 1))


def _constants(
    references: int, audio_seconds: float | None, parts: tuple[Stage, ...], fixed: float, total: float
) -> AudioEstimate:
    setup = round(fixed, 1)
    return AudioEstimate(
        "constants",
        references,
        audio_seconds,
        round(total - setup, 1),
        setup,
        total,
        stages=split(parts, fixed, setup, "generation", total),
    )
