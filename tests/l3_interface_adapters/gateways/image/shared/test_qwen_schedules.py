"""The two ComfyUI schedules a Qwen checkpoint record can name, and the edit-path patch.

Nothing here imports mflux or mlx for real. numpy stands in for mlx, which the deferred
imports in the module make possible. The edit-path tripwire is the one in
`test_viggle_schedule.py`: it covers this patch too.
"""

from itertools import pairwise
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from studio.l3_interface_adapters.gateways.image.shared.qwen_schedules import (
    EULER_ANCESTRAL,
    LINEAR,
    LINEAR_QUADRATIC,
    AncestralSeedHook,
    edit_schedule,
    edit_scheduler,
    generate_scheduler,
    register_schedules,
    sigma_nodes,
)
from tests.support.heavy import heavy_modules


class LinearScheduler:
    """mflux's LinearScheduler, keeping only the constructor that the subclasses use."""

    def __init__(self, config):
        self.config = config
        self._sigmas = self._get_sigmas()

    def _get_sigmas(self):
        raise NotImplementedError("each schedule supplies its own nodes")


class FakeConfig:
    def __init__(self, scheduler="linear", **rest):
        self.scheduler = scheduler
        self.rest = rest


@pytest.fixture
def registered():
    """Both schedules, registered against numpy, with a random module that records its keys."""
    names = {}
    random = SimpleNamespace(
        key=Mock(side_effect=lambda seed: seed),
        split=Mock(side_effect=lambda key: (key + 1, key + 2)),
        normal=Mock(side_effect=lambda shape, **kwargs: np.full(shape, kwargs["key"] / 100, dtype=np.float32)),
    )
    with heavy_modules(
        {
            "mlx.core": {"array": np.array, "float32": np.float32, "random": random},
            "mflux.models.common.schedulers": {"register_contrib": lambda cls, name: names.update({name: cls})},
            "mflux.models.common.schedulers.linear_scheduler": {"LinearScheduler": LinearScheduler},
        }
    ):
        register_schedules()
        yield names, random


@pytest.mark.parametrize("steps", [1, 8, 9, 12, 40])
def test_the_nodes_fall_from_pure_noise_to_zero(steps):
    nodes = sigma_nodes(steps)

    assert len(nodes) == steps + 1 and (nodes[0], nodes[-1]) == (1, 0)
    assert all(a > b for a, b in pairwise(nodes))


def test_the_nodes_match_comfyui_s_twelve_step_linear_quadratic_schedule():
    np.testing.assert_allclose(
        sigma_nodes(12),
        [
            1,
            0.9958333333,
            0.9916666667,
            0.9875,
            0.9833333333,
            0.9791666667,
            0.975,
            0.9444444444,
            0.8611111111,
            0.725,
            0.5361111111,
            0.2944444444,
            0,
        ],
        atol=1e-9,
    )


@pytest.mark.parametrize(
    ("schedule", "sampler", "generate", "edit"),
    [
        ("linear", "euler", LINEAR, LINEAR),
        ("linear_quadratic", "euler", LINEAR_QUADRATIC, LINEAR_QUADRATIC),
        ("linear_quadratic", "euler_ancestral", EULER_ANCESTRAL, LINEAR_QUADRATIC),
    ],
)
def test_each_record_names_one_scheduler_per_mode_and_an_edit_stays_euler(schedule, sampler, generate, edit):
    assert generate_scheduler(schedule, sampler) == generate
    assert edit_scheduler(schedule) == edit


def test_both_schedules_take_the_final_nodes_with_no_resolution_shift(registered):
    names, _ = registered
    config = SimpleNamespace(num_inference_steps=12)

    assert set(names) == {LINEAR_QUADRATIC, EULER_ANCESTRAL}
    for name in names:
        np.testing.assert_allclose(names[name](config)._sigmas, sigma_nodes(12), atol=1e-7)


def test_euler_ancestral_refuses_to_step_before_the_seed_hook(registered):
    names, _ = registered
    engine = names[EULER_ANCESTRAL](SimpleNamespace(num_inference_steps=12))

    with pytest.raises(RuntimeError, match="seed hook"):
        engine.step(np.ones(2), 0, np.zeros(2))


def test_euler_ancestral_matches_the_rf_update_and_restarts_its_noise_at_each_seed(registered):
    names, random = registered
    engine = names[EULER_ANCESTRAL](SimpleNamespace(num_inference_steps=12))
    x = np.array([1, -1], dtype=np.float32)
    velocity = np.array([0.25, -0.5], dtype=np.float32)
    hook = AncestralSeedHook()
    config = SimpleNamespace(scheduler=engine)

    hook.call_before_loop(seed=19, config=config, latents=x)
    actual = engine.step(velocity, 4, x)

    a, b = map(float, engine._sigmas[4:6])
    down = b * b / a
    scale = (1 - b) / (1 - down)
    variance = b * b - (down * scale) ** 2
    expected = scale * (x + (down - a) * velocity) + variance**0.5 * 0.21
    np.testing.assert_allclose(actual, expected, atol=1e-7)
    random.normal.assert_called_once_with((2,), dtype=np.float32, key=21)
    hook.call_before_loop(seed=19, config=config)
    np.testing.assert_array_equal(actual, engine.step(velocity, 4, x))
    hook.call_before_loop(seed=20, config=config)
    assert not np.array_equal(actual, engine.step(velocity, 4, x))
    assert actual.dtype == x.dtype


def test_the_last_ancestral_step_is_plain_euler_and_draws_no_noise(registered):
    names, random = registered
    engine = names[EULER_ANCESTRAL](SimpleNamespace(num_inference_steps=12))
    engine.reset_noise(2)
    x = np.array([0.2, -0.8], dtype=np.float16)
    velocity = np.array([0.5, -0.5], dtype=np.float16)

    actual = engine.step(velocity, 11, x)

    expected = (x.astype(np.float32) - float(engine._sigmas[11]) * velocity.astype(np.float32)).astype(x.dtype)
    np.testing.assert_array_equal(actual, expected)
    random.normal.assert_not_called()
    random.split.assert_not_called()


def test_an_edit_on_the_linear_schedule_needs_no_patch():
    # A stub with no Config: an import of it would fail here.
    with heavy_modules({"mflux.models.common.config.config": {}}), edit_schedule(LINEAR):
        pass


def test_an_edit_gets_the_named_schedule_as_config_s_default_for_the_block_only():
    with heavy_modules({"mflux.models.common.config.config": {"Config": FakeConfig}}):
        original = FakeConfig.__init__
        with edit_schedule(LINEAR_QUADRATIC):
            assert FakeConfig().scheduler == LINEAR_QUADRATIC
            assert FakeConfig(scheduler="linear").scheduler == "linear"
        assert FakeConfig.__init__ is original
        assert FakeConfig().scheduler == "linear"


def test_the_patch_comes_off_when_the_edit_raises():
    with heavy_modules({"mflux.models.common.config.config": {"Config": FakeConfig}}):
        original = FakeConfig.__init__
        with pytest.raises(ValueError, match="engine"), edit_schedule(LINEAR_QUADRATIC):
            raise ValueError("engine")
        assert FakeConfig.__init__ is original
