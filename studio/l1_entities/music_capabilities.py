"""Music has composition inputs and stereo output, separate from speech."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MusicCapabilities:
    backend_id: str
    name: str
    badge: str
    modes: tuple[str, ...] = ("generate", "plan", "transcribe", "cover")
    synthesis_steps: tuple[int, ...] = (8, 16, 32)
    default_steps: int = 32
    max_reference_bytes: int = 32 * 1024 * 1024
    transcription_tasks: tuple[str, ...] = ("full", "melody-full", "melody-vocal")
    planning_modes: tuple[str, ...] = ("full", "melody", "off")
    default_planning: str = "full"
    sample_rate: int = 48000
    channels: int = 2
    max_style_characters: int = 4000
    max_lyrics_characters: int = 20000
    max_score_characters: int = 100000
    max_batch: int = 16
    description: str = "Songs from style and sectioned lyrics, with optional ABC composition."
    loading_note: str = "Install the pinned YuE environment and weights before generating."
