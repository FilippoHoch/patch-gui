"""Tests for line-number formatting in the interactive diff preview."""

from __future__ import annotations

import pytest
from unidiff import PatchSet

from patch_gui.diff_formatting import format_diff_with_line_numbers

try:
    from patch_gui.interactive_diff import (
        FileDiffEntry,
        enrich_entry_with_ai_note,
        set_diff_note_client,
    )
except ImportError as exc:  # pragma: no cover - optional dependency guard
    message = repr(exc)
    if "PySide6" in message or "libGL" in message:
        pytest.skip("PySide6 non disponibile", allow_module_level=True)
    raise


@pytest.fixture(autouse=True)
def _reset_diff_note_client() -> None:
    set_diff_note_client(None)
    yield
    set_diff_note_client(None)


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


def test_enrich_entry_with_ai_note_uses_client_and_strips_result() -> None:
    class _FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def generate_note(self, *, file_label: str, diff_text: str) -> str:
            self.calls.append((file_label, diff_text))
            return "  Nota sintetica  \n"

    client = _FakeClient()
    set_diff_note_client(client)
    entry = FileDiffEntry(
        file_label="foo.py",
        diff_text="-old\n+new\n",
        annotated_diff_text="annotated",
        additions=1,
        deletions=1,
    )

    enriched = enrich_entry_with_ai_note(entry, ai_notes_enabled=True)

    assert enriched.ai_note == "Nota sintetica"
    assert client.calls == [("foo.py", "-old\n+new\n")]


def test_enrich_entry_with_ai_note_returns_original_on_failure() -> None:
    class _FailingClient:
        def generate_note(self, *, file_label: str, diff_text: str) -> str:
            raise RuntimeError("boom")

    set_diff_note_client(_FailingClient())
    entry = FileDiffEntry(
        file_label="bar.txt",
        diff_text="diff\n",
        annotated_diff_text="annotated",
        additions=0,
        deletions=0,
    )

    result = enrich_entry_with_ai_note(entry, ai_notes_enabled=True)

    assert result is entry
    assert result.ai_note is None


def test_enrich_entry_with_ai_note_skips_when_disabled() -> None:
    class _CountingClient:
        def __init__(self) -> None:
            self.called = False

        def generate_note(self, *, file_label: str, diff_text: str) -> str:
            self.called = True
            return "ignored"

    client = _CountingClient()
    set_diff_note_client(client)
    entry = FileDiffEntry(
        file_label="baz.py",
        diff_text="diff\n",
        annotated_diff_text="annotated",
        additions=2,
        deletions=0,
    )

    result = enrich_entry_with_ai_note(entry, ai_notes_enabled=False)

    assert result is entry
    assert result.ai_note is None
    assert client.called is False
