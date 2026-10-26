"""Reword an error that names a private file or folder, so the page and the API see a name.

A path in a settings file can carry a name that its owner keeps private. An engine error that
quotes it would reach the operation record, so a gateway rewords it to a public name. The
original error stays chained, so the server's traceback keeps the path.

Three kinds of name can be private, and each one is replaced:

- the folder or file that the settings name, and each tail of it;
- each file inside that folder, because the owner names those files too;
- the real path behind a link, because a part of a folder can link to another private folder.

A message that still quotes a path after that is replaced as a whole, so a path that this
module could not list does not reach the caller either.
"""

import os
import re
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from studio.l1_entities.errors import StudioError

# A folder can hold many files. Past this count the list stops, and the whole-message
# replacement covers the rest.
MAX_FILES = 200
# An absolute path of two or more parts, or a weight file named anywhere. A URL is not a
# path: its slashes follow a colon or another slash.
PATH = re.compile(
    r"(?<![\w.~:/\\])(?:~|[A-Za-z]:)?[/\\](?:[^\s/\\'\"]+[/\\])+[^\s'\"]*"
    r"|(?<![\w.~\\-])[\w.-]+\.(?:safetensors|gguf|ckpt|pth?|bin|npz)(?![\w.-])"
)


def hide(text: str, paths: Iterable[tuple[str, str]]) -> str:
    """The text with each private name replaced by its public name.

    An engine can quote a path cut at the front, and MLX drops the home folder, so each
    tail of a path is replaced too, longest first, down to its last part alone. The text
    is read once: a name that holds the folder's last part is not replaced a second time.
    """
    names: dict[str, str] = {}
    for path, name in paths:
        for private, public in _private_names(path, name):
            last = Path(private).name
            for start in range(len(private) - len(last) + 1):
                names.setdefault(private[start:], public)
    names.pop("", None)
    if not names:
        return text
    tails = sorted(names, key=len, reverse=True)
    return re.sub("|".join(map(re.escape, tails)), lambda match: names[match.group(0)], text)


@contextmanager
def hidden(paths: Iterable[tuple[str, str]]) -> Iterator[None]:
    """Reword an error that names one of the paths. Leave any other error as it is.

    If the reworded message still quotes a path, the caller gets a message that names only
    the first public name, and the server log gets the original. A public name followed by a
    slash counts as a path too. It is a file that the list does not hold, such as one past
    the file limit, or a shard that a weight index names and the folder lacks. The owner can
    name those files as well, so their names are not let through. Only the outermost block
    does this: a LoRA's block runs inside a checkpoint's, and the checkpoint's block still
    has its own folder to reword.
    """
    paths = tuple(paths)
    depth = _depth.set(_depth.get() + 1)
    try:
        yield
    except Exception as error:
        text = hide(str(error), paths)
        if _depth.get() == 1 and paths and (PATH.search(text) or _below(text, paths)):
            original = _root(error)
            print(f"[hidden] {type(original).__name__}: {original}", file=sys.stderr, flush=True)
            text = f"The run stopped on an error that names a file of {paths[0][1]}. The server log has the error."
        if text == str(error):
            raise
        raise (type(error) if isinstance(error, StudioError) else StudioError)(text) from error
    finally:
        _depth.reset(depth)


_depth: ContextVar[int] = ContextVar("hidden_depth", default=0)


def _below(text: str, paths: tuple[tuple[str, str], ...]) -> bool:
    """Whether the text names a path inside one of the public names."""
    return any(re.search(re.escape(name) + r"[/\\]", text) for _, name in paths)


def _root(error: BaseException) -> BaseException:
    while error.__cause__ is not None:
        error = error.__cause__
    return error


def _private_names(path: str, name: str) -> list[tuple[str, str]]:
    """The path, the real path behind it, and each file below it with its real path."""
    if not path:
        return []
    found = [(path, name), (os.path.realpath(path), name)]
    if not os.path.isdir(path):
        return found
    file_name = f"a file of {name}"
    count = 0
    seen: set[str] = set()
    for folder, folders, files in os.walk(path, followlinks=True, onerror=lambda _: None):
        # A link back up the tree would walk forever, so each real folder is read once.
        seen.add(os.path.realpath(folder))
        folders[:] = [each for each in folders if os.path.realpath(os.path.join(folder, each)) not in seen]
        for each in files:
            if count == MAX_FILES:
                return found
            count += 1
            inside = os.path.join(folder, each)
            found.extend(((inside, file_name), (os.path.realpath(inside), file_name)))
    return found
