from studio.l1_entities.model_readiness import MISSING, PREPARING, READY, ModelReadiness


def test_only_the_ready_state_is_ready():
    assert ModelReadiness("a", READY).ready
    assert not ModelReadiness("a", MISSING, missing=("Weights",)).ready
    assert not ModelReadiness("a", PREPARING).ready
