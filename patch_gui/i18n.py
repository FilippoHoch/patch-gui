"""Utility helpers to manage Qt translations for the application."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

try:  # pragma: no cover - optional dependency may be missing in CLI-only installations
    from PySide6 import QtCore
except ImportError:  # pragma: no cover - executed when PySide6 is not installed
    QtCore = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

LANG_ENV_VAR = "PATCH_GUI_LANG"
TRANSLATION_PREFIX = "patch_gui_"
TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"


def install_translators(
    app: QtCore.QCoreApplication, locale: str | QtCore.QLocale | None = None
) -> List[QtCore.QTranslator]:
    """Compile and install translations for ``app``.

    The target locale is determined by ``locale`` or ``PATCH_GUI_LANG``; when both are
    ``None`` the system locale is used. Compiled ``.qm`` files are stored in the Qt cache
    directory (or ``tempfile.gettempdir()`` as a fallback).
    """

    if QtCore is None:
        raise RuntimeError(
            "PySide6 non è installato: le traduzioni della GUI richiedono l'extra 'gui'."
        )

    sources = _translation_sources()
    if not sources:
        logger.debug("No translation sources found in %s", TRANSLATIONS_DIR)
        return []

    requested_locale = _resolve_locale(locale)
    translators: List[QtCore.QTranslator] = []

    cache_dir = _compiled_dir(app)
    candidates = _candidate_codes(requested_locale)

    for code in candidates:
        ts_path = _pick_source(sources, code)
        if ts_path is None:
            continue

        qm_path = _ensure_compiled(ts_path, cache_dir)
        if qm_path is None:
            continue

        translator = QtCore.QTranslator()
        if translator.load(str(qm_path)):
            app.installTranslator(translator)
            translators.append(translator)
            break

    qt_translator = _load_qt_base_translation(app, requested_locale)
    if qt_translator is not None:
        translators.append(qt_translator)

    return translators


def _resolve_locale(locale: str | QtCore.QLocale | None) -> QtCore.QLocale:
    if locale:
        return QtCore.QLocale(locale)

    env_locale = os.getenv(LANG_ENV_VAR)
    if env_locale:
        return QtCore.QLocale(env_locale)

    return QtCore.QLocale.system()


def _translation_sources() -> Dict[str, Path]:
    sources: Dict[str, Path] = {}
    if not TRANSLATIONS_DIR.exists():
        return sources

    for ts_file in TRANSLATIONS_DIR.glob("*.ts"):
        stem = ts_file.stem
        if not stem.startswith(TRANSLATION_PREFIX):
            continue
        locale_code = stem[len(TRANSLATION_PREFIX) :]
        if not locale_code:
            continue
        sources[locale_code.lower()] = ts_file

    return sources


def _candidate_codes(locale: QtCore.QLocale) -> List[str]:
    name = locale.name().replace("-", "_")
    language_code = QtCore.QLocale.languageToCode(locale.language()).lower()

    candidates = []
    if name:
        candidates.append(name.lower())
    if language_code and language_code not in candidates:
        candidates.append(language_code)
    if "en" not in candidates:
        candidates.append("en")
    return candidates


def _pick_source(sources: Dict[str, Path], code: str) -> Optional[Path]:
    code = code.lower()
    if code in sources:
        return sources[code]
    if "_" in code:
        base = code.split("_", 1)[0]
        return sources.get(base)
    return None


def _compiled_dir(app: QtCore.QCoreApplication) -> Path:
    location = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.CacheLocation)
    if not location:
        location = os.path.join(tempfile.gettempdir(), app.applicationName() or "patch_gui")
    path = Path(location) / "translations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_compiled(ts_path: Path, target_dir: Path) -> Optional[Path]:
    packaged_qm = ts_path.with_suffix(".qm")
    if packaged_qm.exists():
        try:
            if packaged_qm.stat().st_mtime >= ts_path.stat().st_mtime:
                logger.debug("Using bundled translation %s", packaged_qm.name)
                return packaged_qm
            logger.debug(
                "Bundled translation %s is older than source %s; recompiling",
                packaged_qm.name,
                ts_path.name,
            )
        except OSError:
            logger.debug("Unable to compare timestamps for %s; using bundled file", packaged_qm)
            return packaged_qm

        compiled = _compile_with_lrelease(ts_path, target_dir)
        if compiled is not None:
            return compiled

        logger.warning(
            "Falling back to bundled translation %s because compilation failed",
            packaged_qm.name,
        )
        return packaged_qm

    return _compile_with_lrelease(ts_path, target_dir)


def _compile_with_lrelease(ts_path: Path, target_dir: Path) -> Optional[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    qm_path = target_dir / f"{ts_path.stem}.qm"
    try:
        if qm_path.exists() and ts_path.stat().st_mtime <= qm_path.stat().st_mtime:
            return qm_path
    except OSError:
        # Rebuild when we cannot compare timestamps (e.g. packaged resources).
        pass

    executable = _find_lrelease()
    if executable is None:
        logger.warning("Cannot find 'lrelease' executable. Skipping compilation of %s", ts_path)
        return None

    result = subprocess.run(
        [str(executable), str(ts_path), "-qm", str(qm_path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        logger.warning(
            "lrelease failed for %s (exit code %s): %s%s",
            ts_path.name,
            result.returncode,
            result.stdout,
            result.stderr,
        )
        return None

    return qm_path if qm_path.exists() else None


def _find_lrelease() -> Optional[Path]:
    for candidate in ("pyside6-lrelease", "lrelease-qt6", "lrelease"):
        path = shutil.which(candidate)
        if path:
            return Path(path)
    return None


def _load_qt_base_translation(
    app: QtCore.QCoreApplication, locale: QtCore.QLocale
) -> Optional[QtCore.QTranslator]:
    translations_path = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.TranslationsPath)
    if not translations_path:
        return None

    qt_translator = QtCore.QTranslator()
    for code in _candidate_codes(locale):
        if qt_translator.load(f"qtbase_{code}", translations_path):
            app.installTranslator(qt_translator)
            return qt_translator

    return None


__all__ = ["install_translators", "LANG_ENV_VAR"]
