import subprocess
from types import SimpleNamespace

import pytest

from studio.l1_entities.errors import StudioError
from studio.l4_frameworks_and_drivers import system_memory

TOTAL = 64 * 1024**3


def test_macos_memory_headroom_reads_total_and_free_percentage(monkeypatch):
    monkeypatch.setattr(system_memory.sys, "platform", "darwin")
    monkeypatch.setattr(
        system_memory.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=f"The system has {TOTAL} bytes\nSystem-wide memory free percentage: 92%\n"
        ),
    )

    assert system_memory.memory_headroom() == (TOTAL, TOTAL * 92 // 100)


@pytest.mark.parametrize(
    "report",
    (
        "System-wide memory free percentage: 92%\n",
        f"The system has {TOTAL} bytes\n",
    ),
)
def test_macos_memory_headroom_rejects_incomplete_reports(monkeypatch, report):
    monkeypatch.setattr(system_memory.sys, "platform", "darwin")
    monkeypatch.setattr(
        system_memory.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=report),
    )

    with pytest.raises(StudioError, match="no system memory estimate"):
        system_memory.memory_headroom()


@pytest.mark.parametrize(
    "failure",
    (OSError("missing command"), subprocess.TimeoutExpired("memory_pressure", 5)),
)
def test_macos_memory_headroom_reports_command_failures(monkeypatch, failure):
    monkeypatch.setattr(system_memory.sys, "platform", "darwin")
    monkeypatch.setattr(system_memory.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(failure))

    with pytest.raises(StudioError, match="could not read macOS memory pressure"):
        system_memory.memory_headroom()


def test_other_platforms_use_sysconf(monkeypatch):
    monkeypatch.setattr(system_memory.sys, "platform", "linux")
    values = {"SC_PAGE_SIZE": 4096, "SC_PHYS_PAGES": 100, "SC_AVPHYS_PAGES": 25}
    monkeypatch.setattr(system_memory.os, "sysconf", values.__getitem__)

    assert system_memory.memory_headroom() == (409_600, 102_400)


@pytest.mark.parametrize("failure", (OSError("unsupported"), ValueError("unknown name")))
def test_other_platforms_report_sysconf_failures(monkeypatch, failure):
    monkeypatch.setattr(system_memory.sys, "platform", "linux")
    monkeypatch.setattr(system_memory.os, "sysconf", lambda name: (_ for _ in ()).throw(failure))

    with pytest.raises(StudioError, match="could not read system memory headroom"):
        system_memory.memory_headroom()
