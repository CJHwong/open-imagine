"""Isolated app settings for embedded Studio instances and stub servers."""

from studio.l2_use_cases.boundaries.studio_settings_gateway import StudioSettingsGateway


class InMemoryStudioSettingsGateway(StudioSettingsGateway):
    def __init__(self, require_memory_estimate: bool = True):
        self._required = require_memory_estimate

    def require_memory_estimate(self) -> bool:
        return self._required

    def set_require_memory_estimate(self, required: bool) -> None:
        self._required = required
