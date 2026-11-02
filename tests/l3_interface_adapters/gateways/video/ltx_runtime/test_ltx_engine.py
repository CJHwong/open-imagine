import runpy
import sys
import types
from unittest.mock import Mock

import pytest

from studio.l3_interface_adapters.gateways.video.ltx_runtime import ltx_engine


def test_the_engine_cli_receives_every_argument(monkeypatch):
    engine = Mock()
    cli = types.ModuleType("ltx_pipelines_mlx.cli")
    cli.__dict__["main"] = engine
    monkeypatch.setitem(sys.modules, "ltx_pipelines_mlx", types.ModuleType("ltx_pipelines_mlx"))
    monkeypatch.setitem(sys.modules, "ltx_pipelines_mlx.cli", cli)
    monkeypatch.setattr(sys, "argv", ["ltx_engine.py", "generate", "-p", "a cat"])

    ltx_engine.main()

    engine.assert_called_once_with()
    assert sys.argv == ["ltx-2-mlx", "generate", "-p", "a cat"]


def test_a_child_script_runs_in_this_environment(tmp_path, monkeypatch):
    script = tmp_path / "child.py"
    result = tmp_path / "argv.txt"
    script.write_text("import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text('|'.join(sys.argv[2:]))\n")
    monkeypatch.setattr(sys, "argv", ["ltx_engine.py", "--studio-child", str(script), str(result), "a", "b"])

    ltx_engine.main()

    assert result.read_text() == "a|b"


def test_a_child_mode_without_a_script_is_refused(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ltx_engine.py", "--studio-child"])

    with pytest.raises(SystemExit, match="script path"):
        ltx_engine.main()


def test_the_file_runs_as_a_script(monkeypatch):
    engine = Mock()
    cli = types.ModuleType("ltx_pipelines_mlx.cli")
    cli.__dict__["main"] = engine
    monkeypatch.setitem(sys.modules, "ltx_pipelines_mlx", types.ModuleType("ltx_pipelines_mlx"))
    monkeypatch.setitem(sys.modules, "ltx_pipelines_mlx.cli", cli)
    monkeypatch.setattr(sys, "argv", ["ltx_engine.py", "generate"])

    runpy.run_path(ltx_engine.__file__, run_name="__main__")

    engine.assert_called_once_with()
