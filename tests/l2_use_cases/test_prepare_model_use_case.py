import threading
from typing import Any, cast

import pytest

from studio.l1_entities.errors import BackendBusy, Cancelled, UnknownBackend
from studio.l1_entities.model_readiness import MISSING, READY, ModelReadiness
from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway
from studio.l2_use_cases.boundaries.model_readiness_gateway import ModelReadinessGateway
from studio.l2_use_cases.prepare_model_use_case import ENGINE, REWRITER, PrepareModelUseCase


class Model(ModelLifecycleGateway):
    def __init__(self, log, failure=None):
        self._log = log
        self._failure = failure

    def load(self):
        self._log.append("load")
        if self._failure:
            raise self._failure

    def release(self):
        self._log.append("release")


class Rewriter:
    def __init__(self, log):
        self._log = log

    def prepare(self):
        self._log.append("rewriter")


class Residency:
    def __init__(self, log):
        self._log = log

    def claim(self, backend_id):
        self._log.append(f"claim {backend_id}")

    def release_active(self):
        self._log.append("release_active")


class Readiness(ModelReadinessGateway):
    def __init__(self, log):
        self._log = log
        self.ready = set()

    def readiness(self, backend_id):
        return ModelReadiness(backend_id, READY if backend_id in self.ready else MISSING, 7)

    def mark_prepared(self, backend_id):
        self._log.append(f"mark {backend_id}")
        self.ready.add(backend_id)


def build(log, model=None, rewriters=None, lock=None):
    return PrepareModelUseCase(
        lock or threading.Lock(),
        cast(Any, Residency(log)),
        {"qwen": model or Model(log)},
        cast(Any, {"qwen": Rewriter(log)} if rewriters is None else rewriters),
        Readiness(log),
    )


def test_the_engine_loads_and_goes_before_the_rewriter_and_the_model_is_recorded_ready():
    log, stages = [], []

    readiness = build(log).execute("qwen", stages.append)

    assert log == ["claim qwen", "load", "release_active", "rewriter", "mark qwen"]
    assert stages == [ENGINE, REWRITER]
    assert readiness == ModelReadiness("qwen", READY, 7)


def test_a_model_without_a_rewriter_is_recorded_after_its_engine():
    log = []

    build(log, rewriters={}).execute("qwen")

    assert log == ["claim qwen", "load", "release_active", "mark qwen"]


def test_a_failed_load_frees_the_engine_and_records_nothing():
    log = []

    with pytest.raises(RuntimeError, match="no network"):
        build(log, model=Model(log, RuntimeError("no network"))).execute("qwen")

    assert log == ["claim qwen", "load", "release_active"]


def test_a_stop_before_the_engine_loads_nothing():
    log = []

    with pytest.raises(Cancelled):
        build(log).execute("qwen", should_stop=lambda: True)

    assert log == []


def test_a_stop_after_the_engine_skips_the_rewriter_and_records_nothing():
    log = []
    asked = iter([False, True])

    with pytest.raises(Cancelled):
        build(log).execute("qwen", should_stop=lambda: next(asked))

    assert log == ["claim qwen", "load", "release_active"]


def test_an_unknown_model_is_refused():
    with pytest.raises(UnknownBackend, match="flux9"):
        build([]).execute("flux9")


def test_a_busy_engine_is_refused_and_its_lock_is_kept():
    lock = threading.Lock()
    lock.acquire()
    log = []

    with pytest.raises(BackendBusy):
        build(log, lock=lock).execute("qwen")

    assert log == []
    assert lock.locked()


def test_the_lock_is_given_back_after_a_failure():
    lock = threading.Lock()

    with pytest.raises(RuntimeError):
        build([], model=Model([], RuntimeError("x")), lock=lock).execute("qwen")

    assert not lock.locked()
