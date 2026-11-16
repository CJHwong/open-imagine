import pytest

from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.capabilities import (
    minimax_h3_image_cuda_capabilities,
)


def test_the_h3_backend_offers_generate_at_six_fixed_steps():
    capabilities = minimax_h3_image_cuda_capabilities(
        "minimax_h3_image_cuda_nvfp4", "MiniMax H3-Image (CUDA, NVFP4)", "nvfp4"
    )

    assert capabilities.backend_id == "minimax_h3_image_cuda_nvfp4"
    assert capabilities.badge == "nvfp4"
    assert [mode.id for mode in capabilities.modes] == ["generate", "edit"]
    steps = next(param for param in capabilities.modes[0].params if param.id == "steps")
    assert (steps.default, steps.minimum, steps.maximum) == (6, 6, 6)
    assert capabilities.modes[0].estimate is not None


def test_estimates_track_the_measured_sizes_and_reference_count():
    measurements = {
        "fp8": ((38.42, 41.21, 56.23), (50.54, 52.32, 68.38), 90.76),
        "nvfp4": ((19.36, 21.15, 34.30), (29.51, 31.26, 44.29), 64.79),
    }
    for badge, (generate_times, edit_times, four_references) in measurements.items():
        capabilities = minimax_h3_image_cuda_capabilities("h3", badge=badge)
        generate = capabilities.mode("generate").estimate
        edit = capabilities.mode("edit").estimate
        assert generate is not None and edit is not None
        for pixels, generate_time, edit_time in zip(
            (0.589824, 1.048576, 4.194304), generate_times, edit_times, strict=True
        ):
            assert generate.overhead + 6 * generate.step_cost * pixels == pytest.approx(generate_time, rel=0.04)
            assert edit.overhead + 6 * edit.step_cost * pixels == pytest.approx(edit_time, rel=0.04)
        four = edit.overhead + 6 * edit.step_cost * 1.048576 * (1 + 3 * edit.per_reference)
        assert four == pytest.approx(four_references, rel=0.04)


def test_the_sizes_are_the_models_own_grid():
    mode = minimax_h3_image_cuda_capabilities("bf16").mode("generate")
    size = next(param for param in mode.params if param.id == "size")

    assert size.default == "1024x1024"
    assert "2048x2048" in {choice.value for choice in size.choices}
    assert all(int(side) % 32 == 0 for choice in size.choices for side in choice.value.split("x"))


def test_edit_takes_up_to_four_references_at_all_generation_sizes():
    mode = minimax_h3_image_cuda_capabilities("fp8").mode("edit")

    assert (mode.min_references, mode.max_references) == (1, 4)
    size = next(param for param in mode.params if param.id == "size")
    assert size.default == "match"
    sizes = [choice.value for choice in size.choices if choice.value != "match"]
    assert "1024x576" in sizes
    assert "2048x2048" in sizes
    assert "<Picture 1>" in mode.prompt_hint
