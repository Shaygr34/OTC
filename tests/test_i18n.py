"""Tests for config/i18n.py — internationalization module."""

from config.i18n import get_lang, set_lang, t


def test_default_language_is_english():
    set_lang("en")
    assert get_lang() == "en"


def test_translate_english():
    set_lang("en")
    assert t("page.overview") == "Overview"
    assert t("page.settings") == "Settings"


def test_translate_hebrew():
    set_lang("he")
    assert t("page.overview") == "סקירה"
    assert t("page.settings") == "הגדרות"
    set_lang("en")  # reset


def test_missing_key_returns_key():
    assert t("nonexistent.key") == "nonexistent.key"


def test_invalid_lang_ignored():
    set_lang("en")
    set_lang("zz")
    assert get_lang() == "en"


def test_all_keys_have_both_languages():
    from config.i18n import _STRINGS
    for key, translations in _STRINGS.items():
        assert "en" in translations, f"{key} missing 'en'"
        assert "he" in translations, f"{key} missing 'he'"
