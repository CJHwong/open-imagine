"""The H3 tests run without ffmpeg or ffprobe. The live test is the one that runs the real tools."""

import shutil
import sys
from pathlib import Path

import pytest

FAKE_TOOLS = Path(__file__).parents[2] / "support" / "fake_media_tools.py"


@pytest.fixture
def media_tools(tmp_path_factory, monkeypatch):
    """Let `shutil.which` find only the stand-in tools. They live outside the test's tmp_path,
    so a test can still assert that its own directory stays empty."""
    folder = tmp_path_factory.mktemp("media-tools")
    tools = {}
    for name in ("ffmpeg", "ffprobe"):
        shim = folder / name
        shim.write_text(
            f"#!{sys.executable}\nimport runpy, sys\nsys.argv[1:1] = [{name!r}]\n"
            f"runpy.run_path({str(FAKE_TOOLS)!r}, run_name='__main__')\n"
        )
        shim.chmod(0o755)
        tools[name] = str(shim)
    monkeypatch.setattr(shutil, "which", tools.get)
    return tools
