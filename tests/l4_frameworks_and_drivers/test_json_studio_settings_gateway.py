"""Persist only the app policy, and publish changes only after a successful save."""

import json
from pathlib import Path

import pytest

from studio.l1_entities.errors import StudioError
from studio.l4_frameworks_and_drivers.json_studio_settings_gateway import JsonStudioSettingsGateway


def test_settings_default_to_required_and_survive_restart(tmp_path):
    path = tmp_path / "config" / "settings.json"
    settings = JsonStudioSettingsGateway(path)
    assert settings.require_memory_estimate() is True
    settings.set_require_memory_estimate(False)
    assert settings.require_memory_estimate() is False
    assert json.loads(path.read_text()) == {"require_memory_estimate": False}
    assert JsonStudioSettingsGateway(path).require_memory_estimate() is False
    settings.set_require_memory_estimate(True)
    assert JsonStudioSettingsGateway(path, False).require_memory_estimate() is True
    assert not path.with_suffix(".json.tmp").exists()


def test_an_unset_preference_uses_the_config_default(tmp_path):
    assert JsonStudioSettingsGateway(tmp_path / "missing", False).require_memory_estimate() is False


@pytest.mark.parametrize("contents", ["broken", "[]", "{}", '{"require_memory_estimate": "false"}'])
def test_invalid_saved_preferences_fail_instead_of_disabling_the_policy(tmp_path, contents):
    path = tmp_path / "settings.json"
    path.write_text(contents)
    with pytest.raises(StudioError, match="Studio settings"):
        JsonStudioSettingsGateway(path)


def test_unreadable_preferences_are_explained(tmp_path):
    with pytest.raises(StudioError, match="Cannot read Studio settings"):
        JsonStudioSettingsGateway(tmp_path)


def test_a_failed_save_keeps_the_current_setting_and_cleans_up(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    settings = JsonStudioSettingsGateway(path)

    def fail(*args):
        raise OSError("read only")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(StudioError, match="Cannot save Studio settings"):
        settings.set_require_memory_estimate(False)
    assert settings.require_memory_estimate() is True
    assert not path.exists()
    assert not path.with_suffix(".json.tmp").exists()
