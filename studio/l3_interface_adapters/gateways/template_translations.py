"""Attach a family's localized text without moving its canonical template IDs."""

import re
from dataclasses import replace
from typing import NotRequired, TypedDict

from studio.l1_entities.template_translation import TemplateFieldTranslation, TemplateTranslation


class TemplateTranslationSource(TypedDict):
    name: str
    hint: str
    text: str
    fields: NotRequired[tuple[TemplateFieldTranslation, ...]]
    placeholder_order: NotRequired[tuple[int, ...]]


def translate_templates(templates, translations: dict[str, TemplateTranslationSource], *, locale: str):
    result = []
    for template in templates:
        entry = translations.get(template.name)
        if entry is None:
            result.append(template)
            continue
        original = re.findall(r"\[([^\]\n]+)\]", template.text)
        localized = re.findall(r"\[([^\]\n]+)\]", entry["text"])
        if len(original) != len(localized):
            raise ValueError(f"{template.name}: translated template must preserve its placeholders")
        order = entry.get("placeholder_order", tuple(range(len(original))))
        if sorted(order) != list(range(len(original))):
            raise ValueError(f"{template.name}: placeholder_order must preserve every field")
        pairs = tuple((original[index], label) for index, label in zip(order, localized, strict=True))
        fields = iter(pairs)
        canonical_text = re.sub(r"\[([^\]\n]+)\]", lambda _, fields=fields: "[" + next(fields)[0] + "]", entry["text"])
        result.append(
            replace(
                template,
                translations=(
                    *template.translations,
                    TemplateTranslation(
                        locale=locale,
                        name=entry["name"],
                        hint=entry["hint"],
                        text=canonical_text,
                        placeholders=pairs,
                        fields=entry.get("fields", ()),
                    ),
                ),
            )
        )
    return tuple(result)
