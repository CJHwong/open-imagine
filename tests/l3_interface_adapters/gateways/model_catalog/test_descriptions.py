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
from studio.l3_interface_adapters.gateways.image.qwen21.capabilities import qwen21_capabilities
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.capabilities import qwen21_turbo_capabilities
from studio.l3_interface_adapters.gateways.image.viggle_turbo.capabilities import viggle_turbo_capabilities
from studio.l3_interface_adapters.gateways.music.yue2.capabilities import yue2_capabilities
from studio.l3_interface_adapters.gateways.video.minimax_h3.capabilities import CAPABILITIES as minimax_capabilities
from studio.l3_interface_adapters.gateways.video.shared.capabilities import (
    ltx23_mlx_capabilities,
    ltx25_mlx_capabilities,
)
from studio.l3_interface_adapters.gateways.voice.auk_runtime.capabilities import auk_capabilities
from studio.l3_interface_adapters.gateways.voice.drama3.capabilities import drama_capabilities

DESCRIPTIONS = {
    "qwen21": "Precise image edits and readable text with multiple references.",
    "qwen21_turbo": "Fast image generation and editing in eight steps.",
    "flux2": "Diverse image generation and editing with multiple references.",
    "flux3": "Fast instruction edits and image composition from multiple references.",
    "krea2": "Polished images with varied styles for creative exploration.",
    "viggle_turbo": "Image generation and editing in six steps for quick experiments.",
    "minimax_h3_image": "Six-step image generation up to 4 MP, and edits with multiple references.",
    "ltx25_mlx": "Connected video shots with synchronized sound and image or audio guidance.",
    "ltx23_mlx": "Continuous video shots with synchronized sound and image or audio guidance.",
    "minimax_h3": "Experimental short videos with synchronized sound, guided by keyframes or audio.",
    "drama3": "Expressive speech and voice cloning with delivery cues inside the script.",
    "auk_base": "Voice design, cloning, and recording edits, with a focus on quality.",
    "auk": "Fast voice design, cloning, and recording edits in four steps.",
    "yue2": "Complete songs from style and lyrics, with editable melody and chords.",
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
        drama_capabilities(),
        auk_capabilities("base"),
        auk_capabilities("flash"),
        yue2_capabilities(),
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
def test_every_builtin_description_has_a_locale_override(language):
    path = Path(__file__).parents[4] / "studio/l4_frameworks_and_drivers/web/i18n" / (language + ".json")
    translations = json.loads(path.read_text())

    for backend_id, english in DESCRIPTIONS.items():
        translated = translations["label.backend." + backend_id]
        assert translated and translated.endswith("." if language == "en" else "。")
        if language == "en":
            assert translated == english
