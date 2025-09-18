"""Tests for line-number formatting in the interactive diff preview."""

from __future__ import annotations

import pytest
from unidiff import PatchSet

from patch_gui.diff_formatting import format_diff_with_line_numbers

try:  # pragma: no cover - optional dependency for GUI-only features
    from patch_gui.interactive_diff import (
        FileDiffEntry,
        InteractiveDiffWidget,
        with_ai_note,
    )
except ImportError:  # pragma: no cover - gracefully skip when PySide6 is missing
    InteractiveDiffWidget = None  # type: ignore[assignment]
    FileDiffEntry = None  # type: ignore[assignment]
    with_ai_note = None  # type: ignore[assignment]
    _HAS_QT = False
else:  # pragma: no cover - exercised when PySide6 is available
    from PySide6 import QtCore, QtWidgets

    _HAS_QT = True


def test_format_diff_with_line_numbers_includes_real_positions() -> None:
    diff_text = """diff --git a/foo.txt b/foo.txt\nindex 1234567..89abcde 100644\n--- a/foo.txt\n+++ b/foo.txt\n@@ -1,2 +1,3 @@\n line1\n-line2\n+line2 changed\n+line3\n"""

    patch = PatchSet(diff_text)
    patched_file = patch[0]

    formatted = format_diff_with_line_numbers(patched_file, diff_text)

    expected_lines = [
        "diff --git a/foo.txt b/foo.txt",
        "index 1234567..89abcde 100644",
        "--- a/foo.txt",
        "+++ b/foo.txt",
        "@@ -1,2 +1,3 @@",
        "     1 │      1 │  line1",
        "     2 │        │ -line2",
        "       │      2 │ +line2 changed",
        "       │      3 │ +line3",
    ]

    assert formatted == "\n".join(expected_lines) + "\n"


def test_format_diff_with_line_numbers_returns_fallback_for_binary() -> None:
    diff_text = """diff --git a/image.png b/image.png\nindex 1234567..89abcde 100644\nBinary files a/image.png and b/image.png differ\n"""

    patch = PatchSet(diff_text)
    patched_file = patch[0]

    assert patched_file.is_binary_file is True

    formatted = format_diff_with_line_numbers(patched_file, diff_text)

    assert formatted == diff_text


def _ensure_qapplication() -> QtWidgets.QApplication:
    if not _HAS_QT or InteractiveDiffWidget is None:  # pragma: no cover - guard
        pytest.skip("PySide6 non disponibile nel test runner")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


class _RecordingProvider:
    def __init__(self, note: str | None, *, fail: bool = False) -> None:
        self.note = note
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def build_note(self, file_label: str, diff_text: str) -> str | None:
        self.calls.append((file_label, diff_text))
        if self.fail:
            raise RuntimeError("boom")
        return self.note


def _make_entry() -> FileDiffEntry:
    assert FileDiffEntry is not None
    return FileDiffEntry(
        file_label="foo.py",
        diff_text="--- a/foo.py\n+++ b/foo.py\n+print('hi')\n",
        annotated_diff_text="annotated",
        additions=1,
        deletions=0,
    )


@pytest.mark.skipif(not _HAS_QT, reason="PySide6 non disponibile nel test runner")
def test_with_ai_note_uses_provider_response() -> None:
    assert with_ai_note is not None
    entry = _make_entry()
    provider = _RecordingProvider("nota sintetica")

    enriched = with_ai_note(entry, provider)

    assert enriched.ai_note == "nota sintetica"
    assert provider.calls == [(entry.file_label, entry.diff_text)]
    assert entry.ai_note is None


@pytest.mark.skipif(not _HAS_QT, reason="PySide6 non disponibile nel test runner")
def test_with_ai_note_swallows_provider_errors() -> None:
    assert with_ai_note is not None
    entry = _make_entry()
    provider = _RecordingProvider(None, fail=True)

    enriched = with_ai_note(entry, provider)

    assert enriched.ai_note is None
    assert provider.calls == [(entry.file_label, entry.diff_text)]


@pytest.mark.skipif(not _HAS_QT, reason="PySide6 non disponibile nel test runner")
def test_interactive_diff_set_patch_populates_ai_notes() -> None:
    _ensure_qapplication()
    assert InteractiveDiffWidget is not None
    widget = InteractiveDiffWidget()
    provider = _RecordingProvider("nota sintetica")
    widget.set_ai_note_provider(provider)

    diff_text = """diff --git a/foo.py b/foo.py\nindex 1111111..2222222 100644\n--- a/foo.py\n+++ b/foo.py\n@@ -0,0 +1 @@\n+print('hi')\n"""
    patch = PatchSet(diff_text)

    widget.set_patch(patch)

    item = widget._list_widget.item(0)
    entry = item.data(QtCore.Qt.ItemDataRole.UserRole)

    assert isinstance(entry, FileDiffEntry)
    assert entry.ai_note == "nota sintetica"
    assert provider.calls
    widget.deleteLater()


@pytest.mark.skipif(not _HAS_QT, reason="PySide6 non disponibile nel test runner")
def test_interactive_diff_set_patch_handles_provider_failure() -> None:
    _ensure_qapplication()
    assert InteractiveDiffWidget is not None
    widget = InteractiveDiffWidget()
    provider = _RecordingProvider(None, fail=True)
    widget.set_ai_note_provider(provider)

    diff_text = """diff --git a/foo.py b/foo.py\nindex 1111111..2222222 100644\n--- a/foo.py\n+++ b/foo.py\n@@ -0,0 +1 @@\n+print('hi')\n"""
    patch = PatchSet(diff_text)

    widget.set_patch(patch)

    item = widget._list_widget.item(0)
    entry = item.data(QtCore.Qt.ItemDataRole.UserRole)

    assert isinstance(entry, FileDiffEntry)
    assert entry.ai_note is None
    widget.deleteLater()


@pytest.mark.skipif(not _HAS_QT, reason="PySide6 non disponibile nel test runner")
def test_interactive_diff_disabling_provider_clears_notes() -> None:
    _ensure_qapplication()
    assert InteractiveDiffWidget is not None
    widget = InteractiveDiffWidget()
    provider = _RecordingProvider("nota sintetica")
    widget.set_ai_note_provider(provider)

    diff_text = """diff --git a/foo.py b/foo.py\nindex 1111111..2222222 100644\n--- a/foo.py\n+++ b/foo.py\n@@ -0,0 +1 @@\n+print('hi')\n"""
    patch = PatchSet(diff_text)
    widget.set_patch(patch)

    widget.set_ai_note_provider(None)

    item = widget._list_widget.item(0)
    entry = item.data(QtCore.Qt.ItemDataRole.UserRole)

    assert isinstance(entry, FileDiffEntry)
    assert entry.ai_note is None
    widget.deleteLater()
