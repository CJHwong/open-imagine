"""CPU-only installation checks for the isolated YuE2 workflow helpers."""

import importlib.util
import io
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "setup_yue2_workflows", Path(__file__).parents[2] / "scripts/setup_yue2_workflows.py"
)
assert SPEC and SPEC.loader
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


def test_upstream_blob_is_verified_before_it_can_be_installed(monkeypatch):
    monkeypatch.setattr(setup.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b"test content\n"))
    assert setup.fetch_source("common.py", "d670460b4b4aece5915caf5c68d12f560a9fe3e4") == b"test content\n"
    with pytest.raises(ValueError, match="integrity mismatch"):
        setup.fetch_source("common.py", "0" * 40)


def test_helpers_are_namespaced_and_preserve_native_runtime_files(tmp_path, monkeypatch):
    native = tmp_path / "lyra/music_tools"
    native.mkdir(parents=True)
    original = native / "common.py"
    original.write_text("native helper remains unchanged")
    source = (
        b"from abc_tools import parse_abc\nfrom common import write_json\nfrom compile_score import compile_events\n"
    )
    monkeypatch.setattr(setup, "fetch_source", lambda *args: source)
    monkeypatch.setattr(setup.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b"Apache License 2.0\n"))
    destination = setup.install_helpers(tmp_path)
    installed = (destination / "instrumentalize.py").read_text()
    assert "from .abc_tools import parse_abc" in installed
    assert "from .common import write_json" in installed
    assert "from .compile_score import compile_events" in installed
    assert original.read_text() == "native helper remains unchanged"
    provenance = json.loads((destination / "SOURCES.json").read_text())
    assert provenance["revision"] == setup.SOURCE_REVISION
    assert set(provenance["files"]) == set(setup.SOURCE_FILES)
    assert (destination / "LICENSE").read_text() == "Apache License 2.0\n"


def test_source_failure_leaves_no_partial_helper_namespace(tmp_path, monkeypatch):
    def corrupt(name, expected):
        raise ValueError("corrupt upstream helper")

    monkeypatch.setattr(setup, "fetch_source", corrupt)
    with pytest.raises(ValueError, match="corrupt upstream"):
        setup.install_helpers(tmp_path)
    assert not (tmp_path / "lyra").exists()
