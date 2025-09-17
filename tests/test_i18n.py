import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from patch_gui import i18n


class DummyLocale:
    def __init__(self, name: str, language: str) -> None:
        self._name = name
        self._language = language

    def name(self) -> str:
        return self._name

    def language(self) -> str:
        return self._language


class DummyQLocale:
    language_map = {
        "Italian": "it",
        "Portuguese": "pt",
        "English": "en",
    }

    @staticmethod
    def languageToCode(language: str) -> str:
        return DummyQLocale.language_map[language]


@pytest.fixture
def dummy_qtcore(monkeypatch):
    monkeypatch.setattr(i18n, "QtCore", SimpleNamespace(QLocale=DummyQLocale))


def test_candidate_codes_orders_locale_language_and_english(dummy_qtcore):
    locale = DummyLocale("pt-BR", "Portuguese")
    assert i18n._candidate_codes(locale) == ["pt_br", "pt", "en"]


def test_candidate_codes_handles_missing_specific_code(dummy_qtcore):
    locale = DummyLocale("", "Italian")
    assert i18n._candidate_codes(locale) == ["it", "en"]


def test_ensure_compiled_prefers_up_to_date_packaged(monkeypatch, tmp_path):
    ts_path = tmp_path / "patch_gui_es.ts"
    ts_path.write_text("source")
    packaged = ts_path.with_suffix(".qm")
    packaged.write_text("packaged")

    called = False

    def fake_compile(ts_file: Path, target: Path):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(i18n, "_compile_with_lrelease", fake_compile)

    result = i18n._ensure_compiled(ts_path, tmp_path / "compiled")

    assert result == packaged
    assert called is False


def test_ensure_compiled_recompiles_outdated_packaged(monkeypatch, tmp_path):
    packaged = tmp_path / "patch_gui_it.qm"
    packaged.write_text("old")
    ts_path = tmp_path / "patch_gui_it.ts"
    ts_path.write_text("new")

    older = max(0, ts_path.stat().st_mtime - 100)
    os.utime(packaged, (older, older))

    compiled_dir = tmp_path / "cache"

    def fake_which(command: str):
        return f"/usr/bin/{command}" if command == "pyside6-lrelease" else None

    def fake_run(cmd, check, stdout, stderr, text):
        qm_output = Path(cmd[-1])
        qm_output.write_text("compiled")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(i18n.shutil, "which", fake_which)
    monkeypatch.setattr(i18n.subprocess, "run", fake_run)

    result = i18n._ensure_compiled(ts_path, compiled_dir)
    expected = compiled_dir / f"{ts_path.stem}.qm"

    assert result == expected
    assert expected.exists()


def test_ensure_compiled_falls_back_when_compilation_fails(monkeypatch, tmp_path):
    packaged = tmp_path / "patch_gui_fr.qm"
    packaged.write_text("old")
    ts_path = tmp_path / "patch_gui_fr.ts"
    ts_path.write_text("new")

    older = max(0, ts_path.stat().st_mtime - 100)
    os.utime(packaged, (older, older))

    compiled_dir = tmp_path / "compiled"

    def fake_which(command: str):
        return f"/usr/bin/{command}" if command == "pyside6-lrelease" else None

    def fake_run(cmd, check, stdout, stderr, text):
        return SimpleNamespace(returncode=1, stdout="", stderr="error")

    monkeypatch.setattr(i18n.shutil, "which", fake_which)
    monkeypatch.setattr(i18n.subprocess, "run", fake_run)

    result = i18n._ensure_compiled(ts_path, compiled_dir)

    assert result == packaged


def test_find_lrelease_returns_first_available(monkeypatch):
    calls = []

    def fake_which(command: str):
        calls.append(command)
        if command == "lrelease-qt6":
            return "/opt/qt/bin/lrelease-qt6"
        return None

    monkeypatch.setattr(i18n.shutil, "which", fake_which)

    result = i18n._find_lrelease()

    assert result == Path("/opt/qt/bin/lrelease-qt6")
    assert calls == ["pyside6-lrelease", "lrelease-qt6"]


def test_find_lrelease_returns_none_when_not_found(monkeypatch):
    monkeypatch.setattr(i18n.shutil, "which", lambda command: None)

    assert i18n._find_lrelease() is None
