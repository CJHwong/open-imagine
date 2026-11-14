from studio.l3_interface_adapters.gateways.music.yue2_cuda.capabilities import yue2_cuda_capabilities


def test_the_cuda_engine_offers_generate_and_plan_only():
    capabilities = yue2_cuda_capabilities()

    assert capabilities.backend_id == "yue2_cuda"
    assert capabilities.modes == ("generate", "plan")
    assert capabilities.estimate is None
    assert capabilities.sample_rate == 48000 and capabilities.channels == 2
