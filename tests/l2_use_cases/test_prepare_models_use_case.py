from typing import Any, cast

import pytest

from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway
from studio.l2_use_cases.prepare_models_use_case import PrepareModelsUseCase


class Model(ModelLifecycleGateway):
    def __init__(self, log, name, failure=None):
        self._log = log
        self._name = name
        self._failure = failure

    def load(self):
        self._log.append(f"load {self._name}")
        if self._failure is not None:
            raise self._failure

    def release(self):
        self._log.append(f"release {self._name}")


def test_each_model_loads_and_is_freed_before_the_next():
    log = []

    report = PrepareModelsUseCase().execute([("a", Model(log, "a"), None), ("b", Model(log, "b"), None)])

    assert log == ["load a", "release a", "load b", "release b"]
    assert [name for name, _ in report] == ["a", "b"]


def test_a_failed_load_still_frees_the_model():
    log = []

    with pytest.raises(RuntimeError, match="no weights"):
        PrepareModelsUseCase().execute([("a", Model(log, "a", RuntimeError("no weights")), None)])

    assert log == ["load a", "release a"]


def test_the_start_callback_names_each_model_before_it_loads():
    log = []
    seen = []

    PrepareModelsUseCase().execute([("a", Model(log, "a"), None)], on_start=seen.append)

    assert seen == ["a"]
    assert log[0] == "load a"


def test_nothing_to_prepare_reports_nothing():
    assert PrepareModelsUseCase().execute([]) == []


def test_a_failed_load_and_release_report_both_failures_and_stop():
    load_error = RuntimeError("no weights")
    release_error = RuntimeError("release failed")
    log = []

    class Broken(Model):
        def release(self):
            super().release()
            raise release_error

    with pytest.raises(ExceptionGroup, match=r"a.*load.*release") as failed:
        PrepareModelsUseCase().execute([("a", Broken(log, "a", load_error), None), ("b", Model(log, "b"), None)])

    assert failed.value.exceptions == (load_error, release_error)
    assert log == ["load a", "release a"]


def test_a_successful_load_with_a_failed_release_reports_the_release_error():
    log = []

    class Broken(Model):
        def release(self):
            super().release()
            raise RuntimeError("release failed")

    with pytest.raises(RuntimeError, match="release failed"):
        PrepareModelsUseCase().execute([("a", Broken(log, "a"), None)])

    assert log == ["load a", "release a"]


def test_an_interrupted_load_still_releases_the_model():
    log = []

    with pytest.raises(KeyboardInterrupt):
        PrepareModelsUseCase().execute([("a", Model(log, "a", KeyboardInterrupt()), None)])

    assert log == ["load a", "release a"]


class Rewriter:
    def __init__(self, log):
        self._log = log

    def prepare(self):
        self._log.append("prepare rewriter")


class Readiness:
    def __init__(self, log):
        self._log = log

    def mark_prepared(self, backend_id):
        self._log.append(f"mark {backend_id}")


def test_the_rewriter_loads_after_its_engine_is_freed_and_the_model_is_recorded_last():
    log = []

    PrepareModelsUseCase(cast(Any, Readiness(log))).execute([("a", Model(log, "a"), cast(Any, Rewriter(log)))])

    assert log == ["load a", "release a", "prepare rewriter", "mark a"]


def test_a_failed_load_records_nothing():
    log = []

    with pytest.raises(RuntimeError):
        PrepareModelsUseCase(cast(Any, Readiness(log))).execute(
            [("a", Model(log, "a", RuntimeError("x")), cast(Any, Rewriter(log)))]
        )

    assert log == ["load a", "release a"]
