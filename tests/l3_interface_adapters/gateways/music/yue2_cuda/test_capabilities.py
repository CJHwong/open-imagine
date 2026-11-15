import pytest

from studio.l3_interface_adapters.gateways.music.yue2_cuda.capabilities import (
    MAX_LYRICS_CHARACTERS,
    yue2_cuda_capabilities,
)


def test_the_cuda_engine_offers_generate_and_plan_only():
    capabilities = yue2_cuda_capabilities()

    assert capabilities.backend_id == "yue2_cuda"
    assert capabilities.modes == ("generate", "plan", "transcribe", "cover")
    assert capabilities.estimate is not None
    assert capabilities.sample_rate == 48000 and capabilities.channels == 2


def test_the_badge_names_the_build_that_runs():
    assert yue2_cuda_capabilities("yue2_cuda_nvfp4", "YuE2 (CUDA, NVFP4)", "nvfp4").badge == "nvfp4"
    assert yue2_cuda_capabilities().badge == "bf16"


def test_the_form_refuses_the_lyric_the_engine_would_refuse():
    capabilities = yue2_cuda_capabilities()

    assert capabilities.max_lyrics_characters == MAX_LYRICS_CHARACTERS == 600


def test_the_packed_entry_reads_the_pack_s_sweep():
    estimate = yue2_cuda_capabilities("yue2_cuda_nvfp4", "YuE2 (CUDA, NVFP4)", "nvfp4").estimate
    assert estimate is not None

    # 483 characters sang 164.5 s, and the line through the four pack runs reads 136.9 s.
    assert estimate.seconds("generate", lyrics_characters=483) == pytest.approx(136.9, abs=0.5)
    assert estimate.seconds("plan") == 9.0


def test_the_bf16_entry_reads_its_own_sweep():
    estimate = yue2_cuda_capabilities().estimate
    assert estimate is not None

    # 535 characters sang 202.6 s, and the bf16 line reads 254.2 s.
    assert estimate.seconds("generate", lyrics_characters=535) == pytest.approx(254.2, abs=0.5)
    assert estimate.seconds("cover") == 126.3
