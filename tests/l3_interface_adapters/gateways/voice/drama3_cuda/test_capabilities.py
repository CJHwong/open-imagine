from studio.l3_interface_adapters.gateways.voice.drama3_cuda.capabilities import drama_cuda_capabilities


def test_the_cuda_backend_offers_the_same_two_modes():
    capabilities = drama_cuda_capabilities()

    assert capabilities.backend_id == "drama3_cuda"
    assert capabilities.badge == "FP8 W8A8"
    assert [mode.id for mode in capabilities.modes] == ["generate", "clone"]
    assert all(mode.estimate is None for mode in capabilities.modes)


def test_it_names_its_own_weights_and_keeps_the_reference_contract():
    capabilities = drama_cuda_capabilities()

    assert capabilities.loading.repository == "fishaudio/drama-3"
    assert capabilities.reference_sample_rate == 44100
    assert capabilities.max_reference_seconds == 15
