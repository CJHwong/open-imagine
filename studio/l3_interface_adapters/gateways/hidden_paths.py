"""Reword an error that names a private file or folder, so the page and the API see a name.

A path in a settings file can carry a name that its owner keeps private. An engine error that
quotes it would reach the operation record, so a gateway rewords it to a public name. The
original error stays chained, so the server's traceback keeps the path.
"""

import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from studio.l1_entities.errors import StudioError


def hide(text: str, paths: Iterable[tuple[str, str]]) -> str:
    """The text with each path replaced by its public name.

    An engine can quote a path cut at the front, and MLX drops the home folder, so each
    tail of the path is replaced too, longest first, down to its last part alone. The text
    is read once: a name that holds the folder's last part is not replaced a second time.
    """
    names: dict[str, str] = {}
    for path, name in paths:
        last = Path(path).name
        for start in range(len(path) - len(last) + 1):
            names.setdefault(path[start:], name)
    if not names:
        return text
    tails = sorted(names, key=len, reverse=True)
    return re.sub("|".join(map(re.escape, tails)), lambda match: names[match.group(0)], text)


@contextmanager
def hidden(paths: Iterable[tuple[str, str]]) -> Iterator[None]:
    """Reword an error that names one of the paths. Leave any other error as it is."""
    paths = tuple(paths)
    try:
        yield
    except Exception as error:
        text = hide(str(error), paths)
        if text == str(error):
            raise
        raise (type(error) if isinstance(error, StudioError) else StudioError)(text) from error
