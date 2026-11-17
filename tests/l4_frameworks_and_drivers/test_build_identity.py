"""Which code the studio says it runs.

The harness reads its own checkout, and the studio may be running another one. These tests
pin the facts the state document reports, including the case where git cannot answer.
"""

from unittest.mock import Mock

import pytest

from studio.l4_frameworks_and_drivers import build_identity as module
from studio.l4_frameworks_and_drivers.build_identity import build_identity


@pytest.fixture(autouse=True)
def forget_the_cached_answer():
    build_identity.cache_clear()
    yield
    build_identity.cache_clear()


def test_the_identity_names_the_commit_and_the_state_of_the_studio_files(monkeypatch):
    calls = []

    def git(arguments, **_):
        calls.append(arguments)
        answer = "abc123\n" if "rev-parse" in arguments else " M studio/x.py\n"
        return Mock(stdout=answer)

    monkeypatch.setattr(module.subprocess, "run", git)

    assert build_identity() == {"commit": "abc123", "dirty": True}
    assert build_identity() == {"commit": "abc123", "dirty": True}
    assert len(calls) == 2, "the answer is read once per process"


def test_a_clean_studio_tree_is_not_dirty(monkeypatch):
    def git(arguments, **_):
        return Mock(stdout="def456\n" if "rev-parse" in arguments else "")

    monkeypatch.setattr(module.subprocess, "run", git)

    assert build_identity() == {"commit": "def456", "dirty": False}


def test_a_machine_without_git_reports_an_unknown_build(monkeypatch):
    monkeypatch.setattr(module.subprocess, "run", Mock(side_effect=OSError("no git")))

    assert build_identity() == {"commit": "unknown", "dirty": None}
