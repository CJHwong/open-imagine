"""Which code this studio is running, for a caller that has to know.

A benchmark attributes a result to a commit. The harness reads its own checkout, and the
studio may be running another one: an older package, a second tree, or a copy started
before the last pull. The public capabilities can be identical in both and say nothing
about the code that produced the number.
"""

import subprocess
from functools import lru_cache
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]


def _git(*arguments: str) -> str | None:
    try:
        answer = subprocess.run(["git", *arguments], cwd=SOURCE, capture_output=True, text=True, check=True, timeout=10)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return answer.stdout.strip()


@lru_cache(maxsize=1)
def build_identity() -> dict:
    """The commit and the state of this studio's own files, read once per process.

    The dirty flag covers `studio/`, because that is the code the studio runs. A settings
    file decides which model loads, and the harness records the capabilities it serves,
    so the file's content reaches the campaign by its effect.
    """
    commit = _git("rev-parse", "HEAD")
    changes = _git("status", "--porcelain", "--", "studio")
    return {
        "commit": commit or "unknown",
        "dirty": None if changes is None else bool(changes),
    }
