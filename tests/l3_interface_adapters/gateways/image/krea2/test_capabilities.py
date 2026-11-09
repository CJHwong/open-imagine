import pytest

from studio.l3_interface_adapters.gateways.image.krea2.capabilities import MAX_BATCH, SCHEDULE_STEPS, krea2_capabilities


@pytest.fixture
def caps():
    return krea2_capabilities("int8")


def test_the_page_sees_the_backend_and_its_one_mode(caps):
    # Krea 2 has no edit variant. img2img is a generate run from one reference.
    assert (caps.backend_id, caps.name, caps.badge, caps.max_batch) == ("krea2", "Krea 2 Turbo", "int8", MAX_BATCH)
    assert [mode.id for mode in caps.modes] == ["generate"]
    assert (caps.mode("generate").min_references, caps.mode("generate").max_references) == (0, 1)


def test_the_page_sees_no_guidance_and_no_negative_prompt(caps):
    # Turbo runs without CFG at guidance 1.0. Any other value makes mflux run two
    # passes per step, and the estimate counts one.
    assert [param.id for param in caps.mode("generate").params] == ["size", "steps", "strength"]
    assert not caps.mode("generate").estimate.two_pass


def test_the_steps_stay_on_the_distilled_schedule(caps):
    steps = next(param for param in caps.mode("generate").params if param.id == "steps")
    assert (steps.default, steps.minimum, steps.maximum) == (SCHEDULE_STEPS, 8, 8)


def test_the_strength_never_reaches_a_run_with_no_steps(caps):
    # mflux runs range(max(1, int(8 * strength)), 8). At 1.0 that is empty, and
    # the output is only the reference after a VAE round trip.
    strength = next(param for param in caps.mode("generate").params if param.id == "strength")
    assert int(SCHEDULE_STEPS * strength.maximum) < SCHEDULE_STEPS
    assert (strength.default, strength.minimum) == (0.4, 0.05)


def test_a_reference_run_is_estimated_on_the_steps_it_runs(caps):
    assert caps.mode("generate").reference_estimate.strength_scales_steps


def test_a_reference_can_keep_its_own_shape(caps):
    size = next(param for param in caps.mode("generate").params if param.id == "size")
    assert size.default == "1024x1024"
    assert "match" in [choice.value for choice in size.choices]


def test_no_prompt_aid_is_offered_before_it_is_tested(caps):
    # AGENTS.md backend flow step 5: Looks and templates wait for their own test.
    assert caps.mode("generate").looks == ()
    assert caps.mode("generate").templates == ()
