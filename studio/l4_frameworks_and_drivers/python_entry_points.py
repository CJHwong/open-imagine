"""Host distribution metadata, kept outside registration policy."""

from importlib import metadata


def entry_points(*, group: str):
    return metadata.entry_points(group=group)
