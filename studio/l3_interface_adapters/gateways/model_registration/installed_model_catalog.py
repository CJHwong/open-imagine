"""Discover installed model entry points; load only selected registrations."""

import re
from collections.abc import Mapping

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.model_registration.registration_validation import validate_registration
from studio.plugins.registration import ModelRegistration

GROUPS = {
    "image": "open_imagine.models.image",
    "video": "open_imagine.models.video",
    "voice": "open_imagine.models.voice",
}
# API-v1 distributions registered Voice under audio; it remains a supported discovery alias.
LEGACY_GROUPS = {"voice": ("open_imagine.models.audio",)}


class InstalledModelCatalog:
    """Metadata catalog with lazy, validated registration loading."""

    def __init__(self, reserved: Mapping[str, Mapping], entry_points, validate=validate_registration):
        self._validate = validate
        self.entries = {kind: {} for kind in GROUPS}
        self.loaded = {}
        occupied = {name for registry in reserved.values() for name in registry}
        for kind, canonical in GROUPS.items():
            entries = [
                entry for group in (canonical, *LEGACY_GROUPS.get(kind, ())) for entry in entry_points(group=group)
            ]
            for entry in sorted(entries, key=lambda item: item.name):
                group = entry.group
                if not re.fullmatch(r"[a-z][a-z0-9_]*", entry.name):
                    raise ModelConfigurationError(
                        f"Plugin id {entry.name!r} must use lowercase letters, digits and underscores."
                    )
                if entry.name in occupied:
                    raise ModelConfigurationError(
                        f"Duplicate model id {entry.name!r} from {group}; registration ids cannot replace another model."
                    )
                occupied.add(entry.name)
                self.entries[kind][entry.name] = entry

    def ids(self, kind: str) -> tuple[str, ...]:
        return tuple(self.entries[kind])

    def declaration(self, kind: str, name: str) -> ModelRegistration:
        if name not in self.loaded:
            entry = self.entries[kind][name]
            try:
                registration = entry.load()
                self._validate(registration, kind, name)
                self.loaded[name] = registration
            except Exception as error:
                raise ModelConfigurationError(f"Cannot load model plugin {entry.group}/{name}: {error}") from error
        return self.loaded[name]
