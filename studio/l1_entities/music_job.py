"""A composition request and stereo recording, independent of its engine."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MusicJob:
    style: str
    lyrics: str
    seed: int
    cot: str = "full"
    abc: str = ""
    mode: str = "generate"
    instrumental: bool = False
    steps: int = 32
    cfg_scale: float = 1.0
    transcription_task: str = "melody-full"
    reference_audio: bytes = b""
    reference_name: str = ""
    sampling: dict[str, float | int] = field(default_factory=dict)
    """The engine's sampling overrides, and an empty map for the engine's own recipe.

    A field that is absent keeps that field's default for each stage. The engine has
    one sampling recipe for score planning and one for synthesis, so the same values
    reach both and each keeps its own default for whatever the map does not name."""


@dataclass(frozen=True)
class MusicResult:
    wav: bytes
    seconds: float
    sample_rate: int
    seed: int
    score: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    stub: bool = False
