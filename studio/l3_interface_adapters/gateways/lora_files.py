"""The LoRAs a backend offers, and the file behind each one.

A capability record names a LoRA by id and never by file, so a path does not reach
the page, the API or an operation record. This table is the other half: the gateway
keeps it, offers its LoRAs on the record, and turns a job's picks into the files
and strengths its engine loads.

A file that is not on disk is refused by its id, and the server log names its path. It is
never fetched: an engine that reads a missing path as a Hugging Face id would start a
download nobody asked for. An engine error that names a file is reworded by `hidden`, so
the operation record keeps the id in place of the path.
"""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from studio.l1_entities.capabilities import Capabilities
from studio.l1_entities.errors import StudioError
from studio.l1_entities.lora import Lora, LoraUse, check_offer, with_triggers
from studio.l1_entities.video_capabilities import VideoCapabilities


@dataclass(frozen=True)
class LoraFile:
    """One LoRA, the file that holds it, and the image modes it applies to.

    `modes` is empty for every mode. A video model has one set for all its modes.
    """

    lora: Lora
    path: str
    modes: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoraFiles:
    files: tuple[LoraFile, ...] = ()
    max_loras: int = 0

    def __post_init__(self) -> None:
        check_offer(tuple(item.lora for item in self.files), self.max_loras, "the LoRA table")

    def offered(self, mode: str | None = None) -> tuple[Lora, ...]:
        return tuple(item.lora for item in self.files if mode is None or not item.modes or mode in item.modes)

    def offer_image(self, capabilities: Capabilities) -> Capabilities:
        """The record with each mode's LoRAs. A mode that none applies to offers none."""
        if not self.files:
            return capabilities
        unknown = {mode for item in self.files for mode in item.modes} - {mode.id for mode in capabilities.modes}
        if unknown:
            raise StudioError(
                f"A LoRA names a mode that {capabilities.name} does not have: {', '.join(sorted(unknown))}"
            )
        modes = []
        for mode in capabilities.modes:
            loras = self.offered(mode.id)
            modes.append(replace(mode, loras=loras, max_loras=self.max_loras if loras else 0))
        return replace(capabilities, modes=tuple(modes))

    def offer_video(self, capabilities: VideoCapabilities) -> VideoCapabilities:
        if not self.files:
            return capabilities
        return replace(capabilities, loras=self.offered(), max_loras=self.max_loras)

    def paths(self, picks: tuple[LoraUse, ...]) -> tuple[tuple[str, float], ...]:
        """Each pick as the file and strength its engine loads, in the order picked."""
        by_id = {item.lora.id: item for item in self.files}
        loaded = []
        for pick in picks:
            item = by_id.get(pick.id)
            if item is None:
                raise StudioError(f"This model has no LoRA called {pick.id}.")
            if not Path(item.path).is_file():
                print(f"[LoRA {pick.id}] no file at {item.path}", file=sys.stderr, flush=True)
                raise StudioError(f"The weights of LoRA {pick.id} are not on disk. The server log names the path.")
            loaded.append((item.path, pick.strength))
        return tuple(loaded)

    def hide(self, text: str) -> str:
        """The text with each file path replaced by its LoRA's id.

        An engine can quote a path cut at the front, and MLX drops the home folder, so each
        tail of the path is replaced too, longest first, down to the file name alone.
        """
        for item in self.files:
            name = Path(item.path).name
            for start in range(len(item.path) - len(name) + 1):
                text = text.replace(item.path[start:], f"LoRA {item.lora.id}")
        return text

    @contextmanager
    def hidden(self) -> Iterator[None]:
        """Reword an error that names a LoRA file, so the page and the API see only the id.

        The original error stays chained, so the server's traceback keeps the path.
        """
        try:
            yield
        except Exception as error:
            text = self.hide(str(error))
            if text == str(error):
                raise
            raise (type(error) if isinstance(error, StudioError) else StudioError)(text) from error

    def with_triggers(self, prompt: str, picks: tuple[LoraUse, ...]) -> str:
        return with_triggers(prompt, picks, self.offered())

    def triggers(self, picks: tuple[LoraUse, ...]) -> tuple[str, ...]:
        """The trigger words of the picks, each once, in the order picked."""
        by_id = {lora.id: lora for lora in self.offered()}
        words: list[str] = []
        for pick in picks:
            trigger = by_id[pick.id].trigger.strip() if pick.id in by_id else ""
            if trigger and trigger not in words:
                words.append(trigger)
        return tuple(words)
