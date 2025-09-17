import gettext

import pytest

from patch_gui import localization


def test_get_translator_uses_english_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    localization.clear_translation_cache()

    captured: dict[str, object] = {}

    def fake_translation(domain: str, localedir: str, languages: list[str], fallback: bool):
        captured["domain"] = domain
        captured["localedir"] = localedir
        captured["languages"] = list(languages)
        captured["fallback"] = fallback
        return gettext.NullTranslations()

    monkeypatch.setattr(localization._gettext, "translation", fake_translation)

    translator = localization.get_translator()
    assert captured
    assert captured["domain"] == localization.DOMAIN
    assert captured["fallback"] is True
    assert "en" in captured["languages"]
    assert translator.gettext("Sample message") == "Sample message"

    localization.clear_translation_cache()
