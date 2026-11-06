"""Read system memory headroom from the host operating system."""

import os
import re
import subprocess
import sys

from studio.l1_entities.errors import StudioError

_TOTAL = re.compile(r"The system has (\d+)")
_FREE_PERCENT = re.compile(r"System-wide memory free percentage:\s*(\d+)%")


def memory_headroom() -> tuple[int, int]:
    """Return total bytes and currently free bytes, including reclaimable macOS memory."""
    if sys.platform == "darwin":
        return _macos_memory_headroom()
    return _sysconf_memory_headroom()


def _macos_memory_headroom() -> tuple[int, int]:
    try:
        result = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True, check=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        raise StudioError("The studio could not read macOS memory pressure.") from None
    total = _TOTAL.search(result.stdout)
    free_percent = _FREE_PERCENT.search(result.stdout)
    if total is None or free_percent is None:
        raise StudioError("macOS returned no system memory estimate.")
    total_bytes = int(total.group(1))
    free_bytes = total_bytes * int(free_percent.group(1)) // 100
    return total_bytes, free_bytes


def _sysconf_memory_headroom() -> tuple[int, int]:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        total_pages = os.sysconf("SC_PHYS_PAGES")
        free_pages = os.sysconf("SC_AVPHYS_PAGES")
    except (OSError, ValueError):
        raise StudioError("The studio could not read system memory headroom.") from None
    return total_pages * page_size, free_pages * page_size
