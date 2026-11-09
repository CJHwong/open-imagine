"""A provider's policy for Studio LoRA tables, independent of weight-file formats.

A model can use this common schema, narrow its options, or implement a different
configuration reader in its own package. Weight decoding stays with its runtime.
"""

from dataclasses import dataclass

OPTION_FIELDS = frozenset(
    {
        "strength",
        "min_strength",
        "max_strength",
        "strength_step",
        "recommended",
        "trigger",
        "hint",
    }
)


@dataclass(frozen=True)
class LoraTablePolicy:
    mode_scoped: bool
    supported_options: frozenset[str] = OPTION_FIELDS
