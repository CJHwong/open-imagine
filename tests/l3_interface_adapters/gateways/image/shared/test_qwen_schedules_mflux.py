"""The two schedules against the pinned mflux itself, on the CPU, with no weights.

`test_qwen_schedules.py` stands numpy in for mlx and fakes the registry, so an mflux
upgrade that renames the registry, builds the scheduler in another way or moves
`Config` would leave it green. Here the real `Config` builds each schedule by name,
on the base model's config, which turns the resolution shift on.
"""

import pytest

mx = pytest.importorskip("mlx.core")
pytest.importorskip("mflux")

from mflux.models.common.config.config import Config  # noqa: E402

from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import base_model_config  # noqa: E402
from studio.l3_interface_adapters.gateways.image.shared.qwen_schedules import (  # noqa: E402
    EULER_ANCESTRAL,
    LINEAR_QUADRATIC,
    AncestralSeedHook,
    edit_schedule,
    register_schedules,
    sigma_nodes,
)


@pytest.fixture(autouse=True)
def cpu():
    device = mx.default_device()
    mx.set_default_device(mx.cpu)
    register_schedules()
    yield
    mx.set_default_device(device)


def config(scheduler, steps=12):
    return Config(base_model_config(), num_inference_steps=steps, height=512, width=512, scheduler=scheduler)


@pytest.mark.parametrize("name", [LINEAR_QUADRATIC, EULER_ANCESTRAL])
def test_mflux_builds_each_schedule_by_name_and_keeps_its_nodes_unshifted(name):
    built = config(name)

    assert base_model_config().requires_sigma_shift
    assert [round(float(sigma), 6) for sigma in built.scheduler.sigmas] == [round(node, 6) for node in sigma_nodes(12)]


def test_the_seed_hook_makes_an_ancestral_step_repeat_for_its_seed():
    built = config(EULER_ANCESTRAL)
    latents = mx.ones((1, 4, 8), dtype=mx.bfloat16)
    velocity = mx.full((1, 4, 8), 0.5, dtype=mx.bfloat16)
    hook = AncestralSeedHook()

    def step(seed):
        hook.call_before_loop(seed=seed, config=built)
        return built.scheduler.step(velocity, 4, latents)

    first = step(7)
    assert first.dtype == mx.bfloat16
    assert mx.array_equal(first, step(7)).item()
    assert not mx.array_equal(first, step(8)).item()


def test_an_edit_config_built_inside_the_patch_takes_the_named_schedule():
    with edit_schedule(LINEAR_QUADRATIC):
        patched = Config(base_model_config())
    plain = Config(base_model_config())

    assert patched.scheduler.__class__.__name__ == "LinearQuadratic"
    assert plain.scheduler.__class__.__name__ == "LinearScheduler"
