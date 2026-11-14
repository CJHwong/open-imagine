from studio.l3_interface_adapters.gateways.image.qwen21_cuda.capabilities import qwen21_cuda_capabilities


def test_the_cuda_backend_offers_generate_only_and_no_borrowed_time():
    capabilities = qwen21_cuda_capabilities("nvfp4")

    assert capabilities.backend_id == "qwen21_turbo_cuda"
    assert capabilities.badge == "nvfp4"
    assert [mode.id for mode in capabilities.modes] == ["generate"]
    assert capabilities.modes[0].estimate is None
    assert capabilities.private_operations is True


def test_the_size_choice_has_no_match_option_without_a_reference():
    mode = qwen21_cuda_capabilities("bf16").mode("generate")
    size = next(param for param in mode.params if param.id == "size")

    assert all(choice.value != "match" for choice in size.choices)
    assert size.default == "512x512"


def test_the_step_control_opens_on_the_turbo_schedule():
    mode = qwen21_cuda_capabilities("nvfp4").mode("generate")
    steps = next(param for param in mode.params if param.id == "steps")

    assert (steps.default, steps.minimum, steps.maximum) == (8, 1, 50)
