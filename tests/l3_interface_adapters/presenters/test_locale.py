"""The locale registry, its negotiation, and the keys the page and the tables share."""

import json
import re
from pathlib import Path

import pytest

from studio.l3_interface_adapters.presenters.locale import (
    COOKIE_NAME,
    LocaleCatalog,
    accepted_languages,
    cookie_value,
)

WEB = Path(__file__).parents[3] / "studio" / "l4_frameworks_and_drivers" / "web"
I18N = WEB / "i18n"


@pytest.fixture(scope="module")
def catalog():
    return LocaleCatalog(I18N)


def test_every_table_is_a_locale_with_its_own_name(catalog):
    assert catalog.codes() == ("en", "zh-TW")
    labels = {locale.code: locale.label for locale in catalog.locales}
    assert labels == {"en": "English", "zh-TW": "繁體中文"}


def test_the_requested_locale_wins_then_the_cookie_then_the_header(catalog):
    assert catalog.negotiate("zh-TW", "studio-locale=en", "en-US") == "zh-TW"
    assert catalog.negotiate(None, f"{COOKIE_NAME}=zh-TW", "en-US") == "zh-TW"
    assert catalog.negotiate(None, None, "zh-TW,en;q=0.5") == "zh-TW"


def test_the_header_is_read_in_its_own_order(catalog):
    assert catalog.negotiate(None, None, "en;q=0.4, zh-TW;q=0.9") == "zh-TW"
    assert catalog.negotiate(None, None, "fr-FR, en;q=0.3") == "en"


def test_a_language_matches_its_region(catalog):
    """A browser that asks for zh-Hant reads the Traditional table, the only Chinese one."""
    assert catalog.negotiate(None, None, "zh-Hant-TW") == "zh-TW"
    assert catalog.negotiate("zh-tw", None, None) == "zh-TW"


def test_an_unknown_locale_falls_back_to_english(catalog):
    assert catalog.negotiate("de-DE", "studio-locale=fr", "ja-JP") == "en"
    assert catalog.strings("de-DE") is catalog.strings("en")


def test_a_refused_tag_is_not_a_wish(catalog):
    assert accepted_languages("zh-TW;q=0, en;q=0.8") == ["en"]
    assert accepted_languages("") == []
    assert accepted_languages(None) == []


def test_a_bad_quality_value_refuses_only_its_own_tag():
    assert accepted_languages("en;q=oops, zh-TW") == ["zh-TW"]


def test_a_cookie_value_is_read_and_decoded():
    assert cookie_value("a=1; studio-locale=zh-TW; b=2", COOKIE_NAME) == "zh-TW"
    assert cookie_value("studio-locale=zh%2DTW", COOKIE_NAME) == "zh-TW"
    assert cookie_value("a=1", COOKIE_NAME) is None
    assert cookie_value(None, COOKIE_NAME) is None


def test_a_table_that_is_not_flat_stops_the_boot(tmp_path):
    (tmp_path / "en.json").write_text(json.dumps({"ok": "yes"}))
    (tmp_path / "bad.json").write_text(json.dumps({"title": ["not", "a", "string"]}))
    with pytest.raises(ValueError, match="must map strings to strings"):
        LocaleCatalog(tmp_path)


def test_a_table_that_is_not_an_object_stops_the_boot(tmp_path):
    (tmp_path / "en.json").write_text(json.dumps({"ok": "yes"}))
    (tmp_path / "listy.json").write_text(json.dumps(["not", "a", "table"]))
    with pytest.raises(ValueError, match="must map strings to strings"):
        LocaleCatalog(tmp_path)


def test_a_directory_without_english_stops_the_boot(tmp_path):
    (tmp_path / "fr.json").write_text(json.dumps({"_label": "Français"}))
    with pytest.raises(ValueError, match="en locale table is missing"):
        LocaleCatalog(tmp_path)


def _page_keys() -> set[str]:
    text = (WEB / "page.html").read_text(encoding="utf-8")
    keys = set(re.findall(r'data-i18n="([^"]+)"', text))
    for group in re.findall(r"data-i18n-attr='([^']*)'", text):
        keys.update(json.loads(group).values())
    return keys


def test_the_page_asks_only_for_keys_the_tables_hold(catalog):
    keys = _page_keys()
    assert keys, "the page marks no copy for translation"
    english = catalog.strings("en")
    missing = sorted(key for key in keys if key not in english)
    assert not missing, f"page keys with no English string: {missing}"


def test_every_locale_carries_every_key(catalog):
    english = {key for key in catalog.strings("en") if not key.startswith("_")}
    for code in catalog.codes():
        table = catalog.strings(code)
        missing = sorted(english - set(table))
        assert not missing, f"{code} is missing: {missing}"
        assert all(table[key].strip() for key in english), f"{code} carries an empty string"
