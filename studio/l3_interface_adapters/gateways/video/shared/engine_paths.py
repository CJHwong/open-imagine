"""Resolve the engine executable and the argv that starts it."""

import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from studio.l1_entities.errors import StudioError

MISSING_ENGINE = "The bundled Video engine is missing. Reinstall the studio, or set cli_path under [mlx_video]."
WRAPPER = Path(__file__).resolve().parents[1] / "ltx_runtime" / "ltx_engine.py"


def checked_executable(value: str, message: str) -> str:
    if not value:
        raise StudioError(message)
    path = Path(value).expanduser()
    if path.is_file():
        return str(path.absolute())
    found = shutil.which(value)
    if found:
        return found
    raise StudioError(message)


def uv_launcher() -> str:
    """The uv binary that runs the studio, so the engine uses the same one.

    `UV` wins, because a process that started the studio with one uv should build
    the engine with that binary and its own cache.
    """
    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        raise StudioError("Put uv on PATH, or set UV to the uv executable that runs the studio.")
    return uv


def engine_command(settings: Mapping) -> list[str]:
    """The argv prefix that runs the engine.

    A configured `cli_path` runs as it is. Otherwise `uv run --script` runs the
    wrapper whose header declares the engine's environment.
    """
    configured = settings.get("cli_path")
    if configured:
        return [str(configured)]
    return [uv_launcher(), "run", "--script", str(WRAPPER)]


def checked_engine(engine: Sequence[str]) -> list[str]:
    """The engine command, with a missing executable refused before any work."""
    checked = [checked_executable(engine[0], MISSING_ENGINE), *engine[1:]]
    if len(checked) > 1 and not Path(checked[-1]).is_file():
        raise StudioError(MISSING_ENGINE)
    return checked


def child_command(engine: Sequence[str], script: str | Path, *arguments: str) -> list[str]:
    """Run one of the studio's child scripts inside the engine's environment.

    An engine checkout has a `python` beside its CLI, and the child runs under it.
    The wrapper has no such sibling: it runs the child itself, through
    `--studio-child`, in the environment it built.
    """
    if len(engine) == 1:
        sibling = Path(engine[0]).parent / "python"
        if sibling.is_file():
            return [str(sibling), str(script), *arguments]
    return [*engine, "--studio-child", str(script), *arguments]
