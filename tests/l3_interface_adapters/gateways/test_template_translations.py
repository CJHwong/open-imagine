# ruff: noqa: RUF001 -- Traditional Chinese punctuation is intentional.
"""Localization preserves field identities, templates without translations and engine tags."""

import re
from collections import Counter
from dataclasses import asdict

import pytest

from studio.l1_entities.capabilities import Template
from studio.l3_interface_adapters.gateways.image.qwen_runtime.prompt_aids import EDIT_TEMPLATES, GENERATE_TEMPLATES
from studio.l3_interface_adapters.gateways.template_translations import translate_templates
from studio.l3_interface_adapters.gateways.video.ltx_runtime.prompt_aids import VIDEO_TEMPLATES
from studio.l3_interface_adapters.gateways.voice.auk_runtime.capabilities import DESIGN_TEMPLATES
from studio.l3_interface_adapters.gateways.voice.auk_runtime.capabilities import EDIT_TEMPLATES as VOICE_EDIT
from studio.l3_interface_adapters.gateways.voice.drama3.capabilities import TEMPLATES as DELIVERY


@pytest.mark.parametrize(
    ("name", "field", "expected"),
    [
        ("Product shot", "hint", "放在平面上的物品，旁邊留有文字空間。"),
        ("Poster with text", "hint", "以任何語言指定要顯示的文字。"),
        ("First frame", "hint", "從參考圖片開始。"),
        ("Last frame", "hint", "以參考圖片作為結尾。"),
        ("Multi-shot", "hint", "二到四個鏡頭，描述每次切換。"),
        ("Soundscape", "name", "環境音效"),
        ("Soundscape", "hint", "環境音搭配動作產生的音效。"),
        ("Product turn", "hint", "物件旋轉，標籤保持清晰。"),
    ],
)
def test_embedded_display_metadata_uses_the_reviewed_copy(name, field, expected):
    template = next(item for item in GENERATE_TEMPLATES + VIDEO_TEMPLATES if item.name == name)

    assert getattr(template.translations[0], field) == expected


@pytest.mark.parametrize("template", DELIVERY, ids=lambda template: template.name)
def test_drama_script_field_uses_the_visible_text_label(template):
    field = next(item for item in template.translations[0].fields if item.id == "script")

    assert field.label == "朗讀內容"


@pytest.mark.parametrize(
    "template",
    GENERATE_TEMPLATES + EDIT_TEMPLATES + VIDEO_TEMPLATES + DESIGN_TEMPLATES + VOICE_EDIT + DELIVERY,
    ids=lambda template: template.name,
)
def test_every_builtin_translation_retains_canonical_fields_and_has_real_copy(template):
    (translated,) = template.translations
    assert translated.locale == "zh-TW"
    assert translated.name.strip() and translated.hint.strip() and translated.text.strip()
    assert Counter(re.findall(r"\[([^\]\n]+)\]", template.text)) == Counter(
        re.findall(r"\[([^\]\n]+)\]", translated.text)
    )
    assert Counter(re.findall(r"\{([^}]+)\}", template.text)) == Counter(re.findall(r"\{([^}]+)\}", translated.text))
    assert {field.id for field in translated.fields} <= {field.id for field in getattr(template, "fields", ())}
    assert all(field.label.strip() for field in translated.fields)
    # The public record serializes localized content without changing its lookup name.
    assert asdict(template)["name"] == template.name


def test_untranslated_external_template_remains_the_same_record():
    template = Template("external", "hint", "[subject]")
    assert translate_templates((template,), {}, locale="zh-TW") == (template,)
    assert translate_templates((template,), {}, locale="zh-TW")[0] is template


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "translated", "hint": "hint", "text": "missing fields"},
        {"name": "translated", "hint": "hint", "text": "[one] [two]", "placeholder_order": (0, 0)},
    ],
)
def test_malformed_translation_is_refused_before_a_client_receives_it(entry):
    with pytest.raises(ValueError, match="preserve"):
        translate_templates((Template("sample", "hint", "[first] [second]"),), {"sample": entry}, locale="zh-TW")
