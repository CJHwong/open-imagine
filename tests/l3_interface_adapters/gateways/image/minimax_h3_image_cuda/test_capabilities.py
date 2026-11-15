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


def test_the_estimate_holds_the_canvas_not_the_request():
    capabilities = minimax_h3_image_cuda_capabilities("fp8")
    generate = capabilities.mode("generate").estimate
    edit = capabilities.mode("edit").estimate
    assert generate is not None and edit is not None

    # Every size this form offers lands on the engine's 4.2 MP canvas, so the figure does
    # not grow with the request, and six steps add nothing to it.
    assert (generate.step_cost, generate.exponent, generate.overhead) == (0.0, 1.0, 57.3)
    assert (edit.step_cost, edit.exponent, edit.overhead) == (0.0, 1.0, 70.5)


def test_the_nvfp4_entry_reads_its_own_runs():
    capabilities = minimax_h3_image_cuda_capabilities(
        "minimax_h3_image_cuda_nvfp4", "MiniMax H3-Image (CUDA, NVFP4)", "nvfp4"
    )
    generate = capabilities.mode("generate").estimate
    edit = capabilities.mode("edit").estimate
    assert generate is not None and edit is not None

    # 34.3 s and 63.7 s on the pack, against 57.4 and 70.5 on fp8.
    assert generate.overhead == 34.3
    assert edit.overhead == 63.7


def test_the_sizes_are_the_models_own_grid():
    mode = minimax_h3_image_cuda_capabilities("bf16").mode("generate")
    size = next(param for param in mode.params if param.id == "size")

    assert size.default == "1024x1024"
    assert "2048x2048" in {choice.value for choice in size.choices}
    assert all(int(side) % 32 == 0 for choice in size.choices for side in choice.value.split("x"))


def test_edit_takes_up_to_four_references_at_about_four_megapixels():
    mode = minimax_h3_image_cuda_capabilities("fp8").mode("edit")

    assert (mode.min_references, mode.max_references) == (1, 4)
    size = next(param for param in mode.params if param.id == "size")
    assert size.default == "match"
    sizes = [choice.value for choice in size.choices if choice.value != "match"]
    assert sizes and all(
        int(width) * int(height) >= 3_600_000 for width, height in (value.split("x") for value in sizes)
    )
    assert "<Picture 1>" in mode.prompt_hint
