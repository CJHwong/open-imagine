"""How an estimate splits into named stages, and what a cold model adds to it.

Every workspace's estimate has a fixed part and a part that grows with the request. A backend
may name the pieces of its fixed part; the rest is computed. A backend may also declare how
long its model takes to load, and what a first run of a new shape may add. The plan answers
with the figure, its stages, and the figure with the load when the studio does not hold the
model now.
"""

from dataclasses import dataclass, replace
from typing import Any, ClassVar, Protocol, TypeVar

MODEL_LOAD = "model load"
FIXED = "fixed"


@dataclass(frozen=True)
class Stage:
    name: str
    seconds: float


def check_parts(parts: tuple[Stage, ...], fixed_seconds: float, owner: str) -> None:
    """Refuse declared parts that do not add up to the fixed cost they split. A refit of the
    fixed cost must refit its parts too, or the stages would no longer add up."""
    if parts and abs(sum(part.seconds for part in parts) - fixed_seconds) > 0.05:
        total = sum(part.seconds for part in parts)
        raise ValueError(f"{owner} parts add up to {total:g} s, not the {fixed_seconds:g} s they split")


def split(
    parts: tuple[Stage, ...], fixed_raw: float, fixed_seconds: float, computed: str, total_seconds: float
) -> tuple[Stage, ...]:
    """The stages of one figure: the fixed part, by its declared parts or as one "fixed" stage,
    then the computed stage.

    `fixed_seconds` and `total_seconds` are the rounded figures that the estimate reports.
    The declared parts split `fixed_raw`, so each is scaled by `fixed_seconds / fixed_raw` and
    rounded to 0.1 s, and the largest part takes what the rounding left. The computed stage is
    `total_seconds - fixed_seconds`. The stages therefore add up to `total_seconds` exactly.
    """
    named = parts or (Stage(FIXED, fixed_raw),)
    scale = fixed_seconds / fixed_raw if fixed_raw else 0.0
    fixed = [Stage(part.name, round(part.seconds * scale, 1)) for part in named]
    largest = max(range(len(fixed)), key=lambda index: fixed[index].seconds)
    rest = sum(part.seconds for index, part in enumerate(fixed) if index != largest)
    fixed[largest] = Stage(fixed[largest].name, round(fixed_seconds - rest, 1))
    return (*fixed, Stage(computed, round(total_seconds - fixed_seconds, 1)))


class Figure(Protocol):
    """What `with_residency` reads: any workspace's estimate, which is a dataclass."""

    __dataclass_fields__: ClassVar[dict[str, Any]]

    @property
    def total_seconds(self) -> float | None: ...

    @property
    def excludes(self) -> tuple[str, ...]: ...

    @property
    def load_seconds(self) -> float | None: ...


EstimateT = TypeVar("EstimateT", bound=Figure)


def with_residency(estimate: EstimateT, resident: bool | None) -> EstimateT:
    """The estimate with `resident` and `with_load_seconds` filled in.

    The load counts only when the figure excludes it: a figure whose fixed part already holds
    a load, such as a clip's, adds nothing. A held model adds nothing either. The load stays
    unknown when the model is not held and the backend declares no load time, so
    `with_load_seconds` is then None rather than a figure that is too low. When the load is
    counted, "model load" leaves `excludes`. `resident` None means the studio does not say.
    """
    total, excludes, load = estimate.total_seconds, estimate.excludes, estimate.load_seconds
    with_load = None
    if total is not None and resident is not None:
        if resident or MODEL_LOAD not in excludes:
            with_load = total
        elif load is not None:
            with_load = round(total + load, 1)
            excludes = tuple(name for name in excludes if name != MODEL_LOAD)
    return replace(estimate, resident=resident, with_load_seconds=with_load, excludes=excludes)
