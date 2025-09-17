import gettext
from typing import Any, cast

import pytest

from patch_gui import localization

MODULE_LOCALIZATION = cast(Any, localization)


def test_get_translator_uses_english_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    localization.clear_translation_cache()

    captured: dict[str, Any] = {}

    def fake_translation(
        domain: str,
        localedir: str,
        languages: list[str],
        fallback: bool,
    ) -> gettext.NullTranslations:
        captured["domain"] = domain
        captured["localedir"] = localedir
        captured["languages"] = list(languages)
        captured["fallback"] = fallback
        return gettext.NullTranslations()

    monkeypatch.setattr(MODULE_LOCALIZATION._gettext, "translation", fake_translation)

    translator = localization.get_translator()
    assert captured
    assert captured["domain"] == localization.DOMAIN
    assert captured["fallback"] is True
    languages = cast(list[str], captured["languages"])
    assert "en" in languages
    assert translator.gettext("Sample message") == "Sample message"

    localization.clear_translation_cache()
