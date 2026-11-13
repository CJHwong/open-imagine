"""Music has composition inputs and stereo output, separate from speech."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MusicEstimate:
    """Seconds for one request, from the measured rows.

    The engine chooses the song length, so the figure grows only with the lyrics sent,
    and an instrumental pays for the melody plan that it transfers.
    """

    generate_base_seconds: float
    generate_seconds_per_lyric_character: float
    instrumental_extra_seconds: float
    plan_seconds: float
    cover_seconds: float
    transcribe_seconds: float

    def seconds(self, mode: str, lyrics_characters: int = 0, instrumental: bool = False) -> float | None:
        """The measured figure for one request, or None for a mode this estimate does not hold."""
        if mode == "plan":
            return self.plan_seconds
        if mode == "cover":
            return self.cover_seconds
        if mode == "transcribe":
            return self.transcribe_seconds
        if mode != "generate":
            return None
        figure = self.generate_base_seconds + self.generate_seconds_per_lyric_character * max(0, lyrics_characters)
        return figure + self.instrumental_extra_seconds if instrumental else figure


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
    estimate: MusicEstimate | None = None
