"""Whether a model's files are on disk and proven to load, read without loading it."""

from dataclasses import dataclass

READY = "ready"
MISSING = "missing"
PREPARING = "preparing"


@dataclass(frozen=True)
class ModelReadiness:
    """One model's state for its selection: everything a generate, an edit and its prompt
    rewriter need. `bytes_on_disk` counts the declared downloads that are present, and
    `missing` names the declared ones that are not."""

    backend_id: str
    state: str
    bytes_on_disk: int = 0
    missing: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.state == READY
