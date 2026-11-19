import pytest

from studio.l3_interface_adapters.gateways.image.qwen21_cuda.capabilities import qwen21_cuda_capabilities


def test_the_cuda_backend_offers_generate_and_edit_and_no_borrowed_time():
    capabilities = qwen21_cuda_capabilities("nvfp4")

    assert capabilities.backend_id == "qwen21_turbo_cuda"
    assert capabilities.badge == "nvfp4"
    assert [mode.id for mode in capabilities.modes] == ["generate", "edit"]
    assert all(mode.estimate is not None for mode in capabilities.modes)
    assert capabilities.private_operations is True


def test_the_estimate_reads_this_machine_s_measurement():
    generate = qwen21_cuda_capabilities("bf16").mode("generate").estimate
    edit = qwen21_cuda_capabilities("bf16").mode("edit").estimate
    assert generate is not None and edit is not None

    # Eight compiled steps at a quarter megapixel took 2.3 s.
    assert 8 * generate.step_cost * 0.25**generate.exponent + generate.overhead == pytest.approx(2.3, abs=0.4)
    # 22.8 s at 1.8 MP, which the edit fit reads as its fixed cost plus eight steps.
    assert 8 * edit.step_cost * 1.8**edit.exponent + edit.overhead == pytest.approx(22.8, abs=0.5)


def test_one_estimate_serves_every_badge():
    bf16 = qwen21_cuda_capabilities("bf16").mode("generate").estimate

    assert qwen21_cuda_capabilities("nvfp4").mode("generate").estimate == bf16


def test_the_size_choice_has_no_match_option_without_a_reference():
    mode = qwen21_cuda_capabilities("bf16").mode("generate")
    size = next(param for param in mode.params if param.id == "size")

    assert all(choice.value != "match" for choice in size.choices)
    assert size.default == "512x512"


def test_the_step_control_opens_on_the_turbo_schedule():
    mode = qwen21_cuda_capabilities("nvfp4").mode("generate")
    steps = next(param for param in mode.params if param.id == "steps")

    assert (steps.default, steps.minimum, steps.maximum) == (8, 1, 50)


def test_edit_takes_references_on_the_turbo_schedule():
    mode = qwen21_cuda_capabilities("bf16").mode("edit")

    assert (mode.min_references, mode.max_references) == (1, 10)
    steps = next(param for param in mode.params if param.id == "steps")
    guidance = next(param for param in mode.params if param.id == "guidance")
    resolution = next(param for param in mode.params if param.id == "resolution")
    assert (steps.default, guidance.default) == (8, 1.0)
    assert resolution.default == "match"


def test_edit_offers_no_looks_until_they_are_sampled_on_this_engine():
    mode = qwen21_cuda_capabilities("nvfp4").mode("edit")

    assert mode.looks == ()
    assert mode.templates == ()
