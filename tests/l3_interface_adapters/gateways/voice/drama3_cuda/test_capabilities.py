import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l3_interface_adapters.controllers.voice_controller import voice_job
from studio.l3_interface_adapters.gateways.voice.drama3_cuda.capabilities import drama_cuda_capabilities


def test_the_cuda_backend_offers_the_same_two_modes():
    capabilities = drama_cuda_capabilities()

    assert capabilities.backend_id == "drama3_cuda"
    assert capabilities.badge == "FP8 W8A8"
    assert [mode.id for mode in capabilities.modes] == ["generate", "clone"]
    assert all(mode.estimate is not None for mode in capabilities.modes)


def test_the_estimate_reads_this_machine_s_three_runs():
    capabilities = drama_cuda_capabilities()
    generate = capabilities.mode("generate").estimate
    clone = capabilities.mode("clone").estimate
    assert generate is not None and clone is not None

    # 451 characters sang 34.6 s of audio in 48.1 s.
    audio = 0.077 * 451
    assert round(generate.overhead + generate.rtf * audio, 1) == pytest.approx(48.1, abs=0.5)
    # One clone run: 52 characters sang 5.39 s of audio in 9.1 s.
    assert round(clone.overhead + clone.rtf * (0.104 * 52), 1) == 9.1


def test_it_names_its_own_weights_and_keeps_the_reference_contract():
    capabilities = drama_cuda_capabilities()

    assert capabilities.loading.repository == "fishaudio/drama-3"
    assert capabilities.reference_sample_rate == 44100
    assert capabilities.max_reference_seconds == 15


@pytest.mark.parametrize("temperature", [0.1, 1.0])
def test_cuda_sampling_accepts_the_pinned_engine_temperature_bounds(temperature):
    job = voice_job({"text": "Hello.", "temperature": temperature}, drama_cuda_capabilities())

    assert job.options["temperature"] == temperature


def test_cuda_sampling_refuses_temperatures_above_the_pinned_engine_limit():
    capabilities = drama_cuda_capabilities()

    with pytest.raises(InvalidJob):
        voice_job({"text": "Hello.", "temperature": 1.05}, capabilities)

    assert next(param for param in capabilities.mode("generate").params if param.id == "temperature").maximum == 1.0
