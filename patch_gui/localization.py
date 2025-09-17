"""Helpers to manage gettext-based translations for CLI components."""

from __future__ import annotations

import gettext as _gettext
import locale
import os
from pathlib import Path
from typing import Dict, List, Tuple

from .i18n import LANG_ENV_VAR

DOMAIN = "patch_gui"
LOCALE_DIR = Path(__file__).resolve().parent / "locale"

_CACHE: Dict[Tuple[str, ...], _gettext.NullTranslations] = {}

__all__ = ["get_translator", "gettext", "ngettext", "clear_translation_cache"]


def _system_language() -> str | None:
    """Return the system locale in ``LL`` or ``LL_CC`` form when available."""

    for getter_name in ("getlocale", "getdefaultlocale"):
        getter = getattr(locale, getter_name, None)
        if getter is None:
            continue
        try:
            value = getter()
        except ValueError:
            continue
        if not value:
            continue
        lang = value[0] if isinstance(value, (tuple, list)) else value
        if lang:
            return str(lang)
    return None


def _append_candidate(value: str | None, seen: set[str], candidates: List[str]) -> None:
    if not value:
        return
    normalized = value.replace("-", "_").strip()
    if not normalized:
        return
    normalized = normalized.lower()
    if normalized not in seen:
        candidates.append(normalized)
        seen.add(normalized)
    if "_" in normalized:
        base = normalized.split("_", 1)[0]
        if base and base not in seen:
            candidates.append(base)
            seen.add(base)


def _candidate_languages(preferred: str | None) -> List[str]:
    candidates: List[str] = []
    seen: set[str] = set()

    _append_candidate(preferred, seen, candidates)
    _append_candidate(os.getenv(LANG_ENV_VAR), seen, candidates)
    _append_candidate(_system_language(), seen, candidates)

    if "en" not in seen:
        candidates.append("en")

    return candidates


def get_translator(locale_code: str | None = None) -> _gettext.NullTranslations:
    """Return (and cache) the gettext translator for ``locale_code``."""

    languages = tuple(_candidate_languages(locale_code))
    translation = _CACHE.get(languages)
    if translation is None:
        translation = _gettext.translation(
            DOMAIN,
            localedir=str(LOCALE_DIR),
            languages=list(languages),
            fallback=True,
        )
        _CACHE[languages] = translation
    return translation


def gettext(message: str, locale_code: str | None = None) -> str:
    """Translate ``message`` using the active translator."""

    return get_translator(locale_code).gettext(message)


def ngettext(singular: str, plural: str, n: int, locale_code: str | None = None) -> str:
    """Return the singular or plural form based on ``n`` using the active translator."""

    return get_translator(locale_code).ngettext(singular, plural, n)


def clear_translation_cache() -> None:
    """Remove cached gettext translators (useful in tests)."""

    _CACHE.clear()
