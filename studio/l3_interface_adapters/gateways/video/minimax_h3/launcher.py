"""The uv that runs this studio, shared by the H3 gateways.

`uv run --script` builds the worker's environment from its PEP 723 header. The launcher must
be the same uv binary that runs the studio, not whichever uv a child's PATH finds first.
"""

import os
import shutil
from pathlib import Path

from studio.l1_entities.errors import InvalidJob


def uv_launcher() -> str:
    """Return the absolute path of the uv that runs the studio."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise InvalidJob("Install uv and put it on PATH before generating an H3 clip. See the H3 setup guide.")
    path = Path(found).expanduser().absolute()
    if not path.is_file():
        raise InvalidJob(f"The uv at {path} is not a file. Install uv, or clear the UV variable.")
    return str(path)
