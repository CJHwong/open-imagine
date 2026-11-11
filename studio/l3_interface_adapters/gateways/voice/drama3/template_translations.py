# ruff: noqa: RUF001 -- Traditional Chinese punctuation is intentional.
"""Localized spoken examples; the engine's delivery tags retain their exact spelling."""

from studio.l1_entities.template_translation import TemplateFieldTranslation as F
from studio.l3_interface_adapters.gateways.template_translations import TemplateTranslationSource

TRANSLATIONS: dict[str, TemplateTranslationSource] = {
    "Whisper": {
        "name": "耳語",
        "hint": "以輕聲說話，不把語氣指示唸出來。",
        "text": "[whispers] {script}",
        "fields": (F("script", "朗讀內容", "小聲一點，有人在聽。"),),
    },
    "Excited": {
        "name": "興奮",
        "hint": "以充滿熱情的語氣說話。",
        "text": "[excited] {script}",
        "fields": (F("script", "朗讀內容", "我們終於做到了！真是太棒了！"),),
    },
}
