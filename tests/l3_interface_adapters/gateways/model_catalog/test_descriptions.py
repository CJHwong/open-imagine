"""Picker descriptions explain each built-in model without changing its controls."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from studio.l3_interface_adapters.controllers.music_controller import MusicController
from studio.l3_interface_adapters.controllers.voice_controller import VoiceController
from studio.l3_interface_adapters.gateways.image.flux2.capabilities import flux2_capabilities
from studio.l3_interface_adapters.gateways.image.flux3.capabilities import flux3_capabilities
from studio.l3_interface_adapters.gateways.image.krea2.capabilities import krea2_capabilities
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.capabilities import minimax_h3_image_capabilities
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.capabilities import (
    minimax_h3_image_cuda_capabilities,
)
from studio.l3_interface_adapters.gateways.image.qwen21.capabilities import qwen21_capabilities
from studio.l3_interface_adapters.gateways.image.qwen21_cuda.capabilities import qwen21_cuda_capabilities
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.capabilities import qwen21_turbo_capabilities
from studio.l3_interface_adapters.gateways.image.viggle_turbo.capabilities import viggle_turbo_capabilities
from studio.l3_interface_adapters.gateways.model_catalog.registry import BUILTIN_PROVIDERS
from studio.l3_interface_adapters.gateways.music.yue2.capabilities import yue2_capabilities
from studio.l3_interface_adapters.gateways.music.yue2_cuda.capabilities import yue2_cuda_capabilities
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.capabilities import ltx25_cuda_capabilities
from studio.l3_interface_adapters.gateways.video.minimax_h3.capabilities import (
    CAPABILITIES as minimax_capabilities,
)
from studio.l3_interface_adapters.gateways.video.minimax_h3.capabilities import (
    FLASH_CAPABILITIES as minimax_h3_flash_capabilities,
)
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.capabilities import minimax_h3_cuda_capabilities
from studio.l3_interface_adapters.gateways.video.shared.capabilities import (
    ltx23_mlx_capabilities,
    ltx25_mlx_capabilities,
)
from studio.l3_interface_adapters.gateways.voice.auk_runtime.capabilities import auk_capabilities
from studio.l3_interface_adapters.gateways.voice.drama3.capabilities import drama_capabilities
from studio.l3_interface_adapters.gateways.voice.drama3_cuda.capabilities import drama_cuda_capabilities

I18N = Path(__file__).parents[4] / "studio/l4_frameworks_and_drivers/web/i18n"
ENGINE_NAMES = {"mlx": "MLX", "cuda": "CUDA"}
ENDINGS = {"en": "Runs on {}.", "zh-TW": "以 {} 執行。"}


def translations(language):
    return json.loads((I18N / (language + ".json")).read_text())


# The page shows a description from the locale table by backend id, and the server's English
# is its fallback, so the English table is the one reference for every description.
DESCRIPTIONS = {
    key.removeprefix("label.backend."): text
    for key, text in translations("en").items()
    if key.startswith("label.backend.")
}


def all_capabilities():
    return (
        qwen21_capabilities("bf16"),
        qwen21_turbo_capabilities(),
        flux2_capabilities("bf16"),
        flux3_capabilities("int8"),
        krea2_capabilities(),
        viggle_turbo_capabilities("bf16"),
        minimax_h3_image_capabilities(),
        ltx25_mlx_capabilities(),
        ltx23_mlx_capabilities(),
        minimax_capabilities,
        minimax_h3_flash_capabilities,
        drama_capabilities(),
        auk_capabilities("base"),
        auk_capabilities("flash"),
        yue2_capabilities(),
        qwen21_cuda_capabilities("bf16"),
        minimax_h3_image_cuda_capabilities(),
        ltx25_cuda_capabilities(),
        minimax_h3_cuda_capabilities(),
        drama_cuda_capabilities(),
        yue2_cuda_capabilities(),
        yue2_cuda_capabilities("yue2_cuda_nvfp4", "YuE2 NVFP4", "nvfp4"),
    )


@pytest.mark.parametrize("capabilities", all_capabilities(), ids=lambda capabilities: capabilities.backend_id)
def test_every_builtin_model_has_its_specialty_description(capabilities):
    assert capabilities.description == DESCRIPTIONS[capabilities.backend_id]


@pytest.mark.parametrize("capabilities", [drama_capabilities(), auk_capabilities("base"), auk_capabilities("flash")])
def test_voice_picker_records_keep_the_name_and_include_the_description(capabilities):
    controller = VoiceController(Mock(), capabilities)

    assert controller.backends() == [
        {"id": capabilities.backend_id, "name": capabilities.name, "description": DESCRIPTIONS[capabilities.backend_id]}
    ]
    assert controller.capabilities()["description"] == DESCRIPTIONS[capabilities.backend_id]


def test_music_picker_record_keeps_the_name_and_includes_the_description():
    capabilities = yue2_capabilities()
    catalog = Mock()
    catalog.visible_ids.return_value = ("yue2",)
    catalog.get.return_value.capabilities.return_value = capabilities
    controller = MusicController(Mock(), catalog, Mock())

    assert controller.backends() == [{"id": "yue2", "name": "YuE2", "description": DESCRIPTIONS["yue2"]}]


@pytest.mark.parametrize("language", ["en", "zh-TW"])
def test_every_builtin_model_has_a_description_that_names_its_engine(language):
    """A model left out of a table shows the server's English, and only in English."""
    table = translations(language)

    for provider in BUILTIN_PROVIDERS:
        text = table.get("label.backend." + provider.backend_id)
        assert text, f"{provider.backend_id} has no {language} description"
        assert text.endswith(ENDINGS[language].format(ENGINE_NAMES[provider.engine])), provider.backend_id


@pytest.mark.parametrize("language", ["en", "zh-TW"])
def test_no_two_models_share_a_description(language):
    texts = [translations(language)["label.backend." + provider.backend_id] for provider in BUILTIN_PROVIDERS]

    assert len(set(texts)) == len(texts)


def test_every_builtin_model_is_checked_against_its_description():
    assert {capabilities.backend_id for capabilities in all_capabilities()} == {
        provider.backend_id for provider in BUILTIN_PROVIDERS
    }


def test_no_name_says_which_engine_runs_it():
    """The description names the engine, so the picker's name stays the model's own."""
    assert not [c.name for c in all_capabilities() if "CUDA" in c.name or "MLX" in c.name]
