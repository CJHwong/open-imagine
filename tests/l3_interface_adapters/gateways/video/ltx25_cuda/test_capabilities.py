from studio.l3_interface_adapters.gateways.video.ltx25_cuda.capabilities import ltx25_cuda_capabilities


def test_the_cuda_record_offers_only_implemented_controls():
    capabilities = ltx25_cuda_capabilities()

    assert [mode.id for mode in capabilities.modes] == ["generate"]
    assert not capabilities.mode("generate").accepts_audio
    assert capabilities.adapters == ()
    assert capabilities.fast_mode is False


def test_the_cuda_record_keeps_the_models_form_and_names_itself():
    capabilities = ltx25_cuda_capabilities()

    assert capabilities.backend_id == "ltx25_cuda"
    assert capabilities.name == "LTX-2.5 (CUDA)"
    assert capabilities.precision == "bf16"
    assert capabilities.shapes and capabilities.frame_rate == 24
