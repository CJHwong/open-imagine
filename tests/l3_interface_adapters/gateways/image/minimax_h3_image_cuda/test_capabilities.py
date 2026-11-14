from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.capabilities import (
    minimax_h3_image_cuda_capabilities,
)


def test_the_h3_backend_offers_generate_at_six_fixed_steps():
    capabilities = minimax_h3_image_cuda_capabilities("nvfp4")

    assert capabilities.backend_id == "minimax_h3_image_cuda"
    assert capabilities.badge == "nvfp4"
    assert [mode.id for mode in capabilities.modes] == ["generate"]
    steps = next(param for param in capabilities.modes[0].params if param.id == "steps")
    assert (steps.default, steps.minimum, steps.maximum) == (6, 6, 6)
    assert capabilities.modes[0].estimate is None


def test_the_sizes_are_the_models_own_grid():
    mode = minimax_h3_image_cuda_capabilities("bf16").mode("generate")
    size = next(param for param in mode.params if param.id == "size")

    assert size.default == "1024x1024"
    assert "2048x2048" in {choice.value for choice in size.choices}
    assert all(int(side) % 32 == 0 for choice in size.choices for side in choice.value.split("x"))
