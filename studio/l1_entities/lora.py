"""The LoRAs a model offers, and the ones a request picks.

A model declares each LoRA by id, with the strength it starts at and the range it
takes. The declaration names no file: the gateway that owns the weights resolves
the id itself, so a path never reaches the page or the API. A request names LoRAs
by id, each with a strength, and the same rules check it at every door.
"""

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

from studio.l1_entities.errors import InvalidJob

LORA_ID = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True)
class Lora:
    """One LoRA that a model offers.

    `trigger` holds the words that the LoRA was trained to answer to. The host adds
    them after the prompt when the prompt does not already hold them, so a person
    who picks the LoRA does not also have to know its words. `recommended` is the
    range that its author suggests, which the page shows inside the wider range
    that the model accepts. The range reaches 0, because the page shows every LoRA as a
    slider and a slider at 0 is a LoRA that is off.
    """

    id: str
    label: str
    strength: float = 1.0
    min_strength: float = 0.0
    max_strength: float = 2.0
    strength_step: float = 0.05
    recommended: tuple[float, float] | None = None
    trigger: str = ""
    hint: str = ""

    def __post_init__(self) -> None:
        if not LORA_ID.fullmatch(self.id):
            raise ValueError(f"LoRA id {self.id!r} must use lowercase letters, digits and underscores")
        if not self.min_strength <= 0 < self.max_strength:
            raise ValueError(f"LoRA {self.id!r} needs a strength range from 0 or below to above 0")
        if not self.min_strength <= self.strength <= self.max_strength:
            raise ValueError(f"LoRA {self.id!r} starts outside its own strength range")
        if self.strength_step <= 0:
            raise ValueError(f"LoRA {self.id!r} needs a strength step above 0")
        if self.recommended is not None:
            low, high = self.recommended
            if not self.min_strength <= low <= high <= self.max_strength:
                raise ValueError(f"LoRA {self.id!r} recommends a range outside its strength range")


@dataclass(frozen=True)
class LoraUse:
    """One LoRA that a request picks, and its strength."""

    id: str
    strength: float


def check_offer(loras: tuple[Lora, ...], max_loras: int, owner: str) -> None:
    """A model that offers LoRAs has to take at least one, and each id once."""
    ids = [lora.id for lora in loras]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{owner} offers a LoRA id twice")
    if loras and max_loras < 1:
        raise ValueError(f"{owner} offers LoRAs, so max_loras must be at least 1")
    if max_loras < 0:
        raise ValueError(f"{owner} needs a max_loras of 0 or more")


def parse_loras(raw: object, offered: tuple[Lora, ...], max_loras: int) -> tuple[LoraUse, ...]:
    """The picks of a request, checked against what the model offers.

    `raw` is a list of {"id", "strength"} objects, as the JSON API sends it, or the
    same list as one JSON string, as a form field carries it. Blank means no LoRA.
    A pick without a strength takes the LoRA's own starting strength.
    """
    items = _items(raw)
    if not items:
        return ()
    if not offered:
        raise InvalidJob("This model offers no LoRAs.")
    if len(items) > max_loras:
        raise InvalidJob(f"This model takes at most {max_loras} LoRA{'' if max_loras == 1 else 's'}.")
    by_id = {lora.id: lora for lora in offered}
    picks: list[LoraUse] = []
    for item in items:
        pick = _pick(item, by_id)
        if any(chosen.id == pick.id for chosen in picks):
            raise InvalidJob(f"LoRA {pick.id} is picked twice.")
        picks.append(pick)
    return tuple(picks)


def with_triggers(prompt: str, picks: tuple[LoraUse, ...], offered: tuple[Lora, ...]) -> str:
    """The prompt with each picked LoRA's trigger words added, unless it holds them already."""
    by_id = {lora.id: lora for lora in offered}
    missing = []
    for pick in picks:
        trigger = by_id[pick.id].trigger.strip()
        if trigger and trigger.casefold() not in prompt.casefold() and trigger not in missing:
            missing.append(trigger)
    if not missing:
        return prompt
    return ", ".join([prompt.rstrip(), *missing]) if prompt.strip() else ", ".join(missing)


def _items(raw: object) -> list:
    if raw is None:
        return []
    if isinstance(raw, str):
        if not raw.strip():
            return []
        try:
            raw = json.loads(raw)
        except ValueError:
            raise InvalidJob("loras must be a JSON list of {id, strength} objects") from None
    if not isinstance(raw, list):
        raise InvalidJob("loras must be a list of {id, strength} objects")
    return raw


def _pick(item: object, by_id: Mapping[str, Lora]) -> LoraUse:
    if not isinstance(item, Mapping):
        raise InvalidJob("Each LoRA must be an object with an id and a strength")
    lora_id = item.get("id")
    if not isinstance(lora_id, str) or lora_id not in by_id:
        raise InvalidJob(f"LoRA must be one of {', '.join(by_id)}")
    lora = by_id[lora_id]
    raw = item.get("strength", lora.strength)
    try:
        strength = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else math.nan
    except OverflowError:
        strength = math.nan
    if not math.isfinite(strength):
        raise InvalidJob(f"The strength of LoRA {lora_id} must be a number")
    if not lora.min_strength <= strength <= lora.max_strength:
        raise InvalidJob(
            f"The strength of LoRA {lora_id} must be between {lora.min_strength:g} and {lora.max_strength:g}"
        )
    return LoraUse(lora_id, strength)
