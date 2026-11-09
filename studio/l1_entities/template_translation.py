"""Localized prompt content, with stable field identifiers for clients."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateFieldTranslation:
    id: str
    label: str
    default: str | None = None
    choices: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TemplateTranslation:
    locale: str
    name: str
    hint: str
    text: str
    placeholders: tuple[tuple[str, str], ...] = ()
    fields: tuple[TemplateFieldTranslation, ...] = ()
