"""Resolve the engine executable named by adapter configuration."""

import shutil
from collections.abc import Mapping
from pathlib import Path

from studio.l1_entities.errors import StudioError


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


def engine_executable(settings: Mapping) -> str:
    """The engine entrypoint: the configured one, or the wrapper that ships with the studio.

    The wrapper declares the engine's dependencies, so `uv` builds its environment on the
    first run and no engine checkout is needed.
    """
    return str(settings.get("cli_path") or Path(__file__).resolve().parents[1] / "ltx_runtime" / "ltx_engine.py")


def child_command(engine: str, script: str | Path, *arguments: str) -> list[str]:
    """Run one of the studio's child scripts inside the engine's environment.

    An engine checkout has a `python` beside its CLI, and the child runs under it. The
    wrapper has no such sibling: it runs the child itself, through `--studio-child`, in
    the environment it built.
    """
    sibling = Path(engine).parent / "python"
    if sibling.is_file():
        return [str(sibling), str(script), *arguments]
    return [engine, "--studio-child", str(script), *arguments]
