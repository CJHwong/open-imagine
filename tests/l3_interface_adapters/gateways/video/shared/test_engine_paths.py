import shutil
import sys
from pathlib import Path

import pytest

from studio.l1_entities.errors import StudioError
from studio.l3_interface_adapters.gateways.video.shared.engine_paths import (
    WRAPPER,
    checked_engine,
    child_command,
    engine_command,
    uv_launcher,
)


def test_an_engine_checkout_runs_a_child_under_its_own_python(tmp_path):
    engine = tmp_path / "ltx-2-mlx"
    engine.touch()
    (tmp_path / "python").touch()

    assert child_command([str(engine)], "child.py", "arg") == [str(tmp_path / "python"), "child.py", "arg"]


def test_a_checkout_without_a_python_runs_the_child_through_the_cli(tmp_path):
    engine = tmp_path / "ltx-2-mlx"
    engine.touch()

    assert child_command([str(engine)], "child.py", "arg") == [str(engine), "--studio-child", "child.py", "arg"]


def test_the_wrapper_runs_a_child_itself(tmp_path):
    wrapper = tmp_path / "ltx_engine.py"
    wrapper.touch()

    assert child_command(["/chosen/uv", "run", "--script", str(wrapper)], "child.py", "arg") == [
        "/chosen/uv",
        "run",
        "--script",
        str(wrapper),
        "--studio-child",
        "child.py",
        "arg",
    ]


def test_an_empty_setting_starts_the_shipped_wrapper_with_the_studio_s_uv(monkeypatch):
    monkeypatch.setenv("UV", "/chosen/uv")

    command = engine_command({})

    assert command == ["/chosen/uv", "run", "--script", str(WRAPPER)]
    assert Path(command[-1]).is_file()


def test_a_configured_engine_runs_as_it_is():
    assert engine_command({"cli_path": "bin/ltx-2-mlx"}) == ["bin/ltx-2-mlx"]


def test_the_uv_setting_wins_over_path(monkeypatch):
    monkeypatch.setenv("UV", "/chosen/uv")
    monkeypatch.setattr(shutil, "which", lambda name: "/other/uv")

    assert uv_launcher() == "/chosen/uv"


def test_uv_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    assert uv_launcher() == "/usr/bin/uv"


def test_a_missing_uv_names_the_setting(monkeypatch):
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(StudioError, match="UV"):
        uv_launcher()


def test_a_missing_engine_is_refused_before_any_work(tmp_path):
    with pytest.raises(StudioError, match="cli_path"):
        checked_engine([str(tmp_path / "missing")])


def test_a_missing_wrapper_is_refused_before_any_work(tmp_path):
    with pytest.raises(StudioError, match="Reinstall the studio"):
        checked_engine([sys.executable, "run", "--script", str(tmp_path / "missing.py")])


def test_a_present_engine_is_returned_absolute(tmp_path):
    engine = tmp_path / "ltx-2-mlx"
    engine.touch()

    assert checked_engine([str(engine)]) == [str(engine)]
