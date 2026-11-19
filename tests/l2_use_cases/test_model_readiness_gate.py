from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import ModelNotReady
from studio.l1_entities.model_readiness import MISSING, READY, ModelReadiness
from studio.l2_use_cases.boundaries.model_readiness_gateway import ModelReadinessGateway
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway
from studio.l2_use_cases.model_readiness_gate import ReadyModelResidency, ReadyPromptRewriter


class Readiness(ModelReadinessGateway):
    def __init__(self, ready=()):
        self.ready = set(ready)

    def readiness(self, backend_id):
        return ModelReadiness(backend_id, READY if backend_id in self.ready else MISSING)

    def mark_prepared(self, backend_id):
        self.ready.add(backend_id)


class Residency(ModelResidencyGateway):
    def __init__(self):
        self.calls = []

    def resident_gib(self, backend_id):
        self.calls.append(("resident_gib", backend_id))
        return 2.5

    def select(self, backend_id):
        self.calls.append(("select", backend_id))

    def claim(self, backend_id):
        self.calls.append(("claim", backend_id))
        return ("freed",)

    def release_active(self):
        self.calls.append(("release_active",))

    def release_idle(self):
        self.calls.append(("release_idle",))

    def release(self):
        self.calls.append(("release",))


def test_a_run_on_a_prepared_model_claims_it():
    inner = Residency()

    assert ReadyModelResidency(inner, Readiness({"qwen"})).claim("qwen") == ("freed",)
    assert inner.calls == [("claim", "qwen")]


def test_a_run_on_a_model_that_is_not_prepared_is_refused_before_anything_loads():
    inner = Residency()

    with pytest.raises(ModelNotReady, match=r"qwen is not downloaded yet.*\"kind\": \"prepare\".*--prepare"):
        ReadyModelResidency(inner, Readiness()).claim("qwen")

    assert inner.calls == []


def test_everything_else_passes_straight_through():
    inner = Residency()
    gated = ReadyModelResidency(inner, Readiness())

    assert gated.resident_gib("a") == 2.5
    gated.select("a")
    gated.release_active()
    gated.release_idle()
    gated.release()

    assert inner.calls == [("resident_gib", "a"), ("select", "a"), ("release_active",), ("release_idle",), ("release",)]


def test_a_rewrite_for_a_prepared_model_reaches_its_rewriter():
    inner = Mock()
    inner.rewrite.return_value = "longer"
    gated = ReadyPromptRewriter(inner, Readiness({"qwen"}), lambda: "qwen")

    assert gated.rewrite("a cat", "generate", (), "writing", "stop") == "longer"
    inner.rewrite.assert_called_once_with("a cat", "generate", (), "writing", "stop")


def test_a_rewrite_for_the_active_model_that_is_not_prepared_is_refused():
    inner = Mock()
    active = iter(["qwen", "h3"])
    gated = ReadyPromptRewriter(inner, Readiness({"qwen"}), lambda: next(active))

    gated.rewrite("a", "generate", (), None, None)
    with pytest.raises(ModelNotReady, match="h3"):
        gated.rewrite("a", "generate", (), None, None)

    assert inner.rewrite.call_count == 1


def test_the_rewriter_gate_passes_its_other_calls_through():
    inner = Mock()
    inner.modes.return_value = ("generate",)
    gated = ReadyPromptRewriter(inner, Readiness(), lambda: "qwen")

    assert gated.modes() == ("generate",)
    gated.release()
    gated.prepare()

    inner.release.assert_called_once_with()
    inner.prepare.assert_called_once_with()
