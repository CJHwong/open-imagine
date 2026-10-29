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


@dataclass(frozen=True)
class MusicResult:
    wav: bytes
    seconds: float
    sample_rate: int
    seed: int
    score: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    stub: bool = False
