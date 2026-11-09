"""Discovery accepts canonical and legacy Voice distributions, without importing them."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l4_frameworks_and_drivers.config import ConfigError
from studio.l4_frameworks_and_drivers.model_registration.installed_model_catalog import InstalledModelCatalog


@pytest.mark.parametrize("group", ("open_imagine.models.voice", "open_imagine.models.audio"))
def test_voice_entry_points_have_one_workspace_and_remain_lazy(monkeypatch, group):
    entry = SimpleNamespace(name="voice_model", group=group, load=Mock(return_value="registration"))
    monkeypatch.setattr(
        "studio.l4_frameworks_and_drivers.model_registration.installed_model_catalog.metadata.entry_points",
        lambda group: [entry] if group == entry.group else [],
    )
    validate = Mock()
    catalog = InstalledModelCatalog({}, validate=validate)
    assert catalog.ids("voice") == ("voice_model",)
    entry.load.assert_not_called()
    assert catalog.declaration("voice", "voice_model") == "registration"
    assert catalog.declaration("voice", "voice_model") == "registration"
    entry.load.assert_called_once()
    validate.assert_called_once_with("registration", "voice", "voice_model")


def test_voice_alias_cannot_create_two_backends_with_the_same_id(monkeypatch):
    entries = [
        SimpleNamespace(name="same", group=group)
        for group in ("open_imagine.models.voice", "open_imagine.models.audio")
    ]
    monkeypatch.setattr(
        "studio.l4_frameworks_and_drivers.model_registration.installed_model_catalog.metadata.entry_points",
        lambda group: [entry for entry in entries if entry.group == group],
    )
    with pytest.raises(ConfigError, match="Duplicate model id"):
        InstalledModelCatalog({})
