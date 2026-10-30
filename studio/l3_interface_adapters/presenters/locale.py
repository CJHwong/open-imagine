"""The UI locales this studio can draw, and the one a request asks for.

One JSON file per locale under `web/i18n/` is the whole registry: the file name is the
locale code and `_label` is its name in its own language. Adding a language is adding a
file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

DEFAULT_LOCALE = "en"
LABEL_KEY = "_label"
COOKIE_NAME = "studio-locale"


@dataclass(frozen=True)
class Locale:
    code: str
    label: str


class LocaleCatalog:
    """Every table in one directory, read once, and the negotiation over them."""

    def __init__(self, directory: Path) -> None:
        self._tables: dict[str, dict[str, str]] = {}
        self._locales: list[Locale] = []
        for path in sorted(directory.glob("*.json")):
            table = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(table, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in table.items()
            ):
                raise ValueError(f"The locale table {path.name} must map strings to strings.")
            code = path.stem
            self._tables[code] = table
            self._locales.append(Locale(code, table.get(LABEL_KEY, code)))
        if DEFAULT_LOCALE not in self._tables:
            raise ValueError(f"The {DEFAULT_LOCALE} locale table is missing.")

    @property
    def locales(self) -> tuple[Locale, ...]:
        return tuple(self._locales)

    def codes(self) -> tuple[str, ...]:
        return tuple(locale.code for locale in self._locales)

    def strings(self, code: str) -> dict[str, str]:
        """The chosen table, or English. A code the registry does not know never wins."""
        return self._tables.get(code) or self._tables[DEFAULT_LOCALE]

    def negotiate(
        self,
        requested: str | None = None,
        cookie: str | None = None,
        accept_language: str | None = None,
    ) -> str:
        """A test's `?lang`, then the picker's cookie, then the browser's order, then English."""
        for candidate in (requested, cookie_value(cookie, COOKIE_NAME)):
            exact = self._exact(candidate)
            if exact:
                return exact
        for tag in accepted_languages(accept_language):
            exact = self._exact(tag)
            if exact:
                return exact
            prefix = tag.split("-")[0].lower()
            for code in self.codes():
                if code.split("-")[0].lower() == prefix:
                    return code
        return DEFAULT_LOCALE

    def _exact(self, value: str | None) -> str | None:
        wanted = (value or "").strip().lower()
        return next((code for code in self.codes() if code.lower() == wanted), None)


def cookie_value(header: str | None, name: str) -> str | None:
    """The named cookie from a raw Cookie header, decoded."""
    for part in (header or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return unquote(value)
    return None


def accepted_languages(header: str | None) -> list[str]:
    """The tags a browser accepts, best first. A `q=0` tag is a refusal, not a wish."""
    ranked: list[tuple[float, int, str]] = []
    for position, entry in enumerate((header or "").split(",")):
        tag, _, parameters = entry.strip().partition(";")
        quality = 1.0
        for parameter in parameters.split(";"):
            name, _, value = parameter.strip().partition("=")
            if name == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        if tag and quality > 0:
            ranked.append((quality, -position, tag))
    ranked.sort(reverse=True)
    return [tag for _, _, tag in ranked]
