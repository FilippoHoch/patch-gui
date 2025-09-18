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
    assert captured["fallback"] is False
    languages = cast(list[str], captured["languages"])
    assert languages == ["en"]
    assert translator.gettext("Sample message") == "Sample message"

    localization.clear_translation_cache()


def test_ui_messages_default_to_english() -> None:
    localization.clear_translation_cache()
    translator = localization.get_translator("en")
    samples = [
        "Selezione obbligatoria",
        "Applicazione diff in corso…",
        "Ripristinare i file dalla sessione {name}?\n\nI file correnti saranno sovrascritti.",
    ]
    try:
        for message in samples:
            assert translator.gettext(message) == message
    finally:
        localization.clear_translation_cache()
