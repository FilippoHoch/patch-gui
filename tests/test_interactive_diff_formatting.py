"""Tests for line-number formatting in the interactive diff preview."""

from __future__ import annotations

from unidiff import PatchSet

from patch_gui.diff_formatting import format_diff_with_line_numbers
from patch_gui.interactive_diff_model import (
    FileDiffEntry,
    enrich_entry_with_ai_note,
    set_diff_note_client,
)


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


class _DummyNoteClient:
    def __init__(self, *, note: str | None = None, raise_error: bool = False) -> None:
        self.note = note
        self.raise_error = raise_error
        self.calls: list[tuple[str, str]] = []

    def generate_diff_note(self, file_label: str, diff_text: str) -> str | None:
        self.calls.append((file_label, diff_text))
        if self.raise_error:
            raise RuntimeError("boom")
        return self.note


def test_enrich_entry_with_ai_note_populates_note() -> None:
    entry = FileDiffEntry(
        file_label="foo.py",
        diff_text="-old\n+new\n",
        annotated_diff_text="annotated",
        additions=1,
        deletions=1,
    )
    client = _DummyNoteClient(note="Rilevati cambiamenti nel modulo foo.")
    set_diff_note_client(client)
    try:
        enriched = enrich_entry_with_ai_note(entry, enabled=True)
    finally:
        set_diff_note_client(None)

    assert enriched is not entry
    assert enriched.ai_note == "Rilevati cambiamenti nel modulo foo."
    assert client.calls == [("foo.py", "-old\n+new\n")]


def test_enrich_entry_with_ai_note_handles_disabled_or_errors() -> None:
    entry = FileDiffEntry(
        file_label="bar.txt",
        diff_text="-a\n+b\n",
        annotated_diff_text="annotated",
        additions=1,
        deletions=1,
    )

    disabled_client = _DummyNoteClient(note="ignored")
    set_diff_note_client(disabled_client)
    try:
        untouched = enrich_entry_with_ai_note(entry, enabled=False)
    finally:
        set_diff_note_client(None)

    assert untouched is entry
    assert disabled_client.calls == []

    failing_client = _DummyNoteClient(raise_error=True)
    set_diff_note_client(failing_client)
    try:
        fallback = enrich_entry_with_ai_note(entry, enabled=True)
    finally:
        set_diff_note_client(None)

    assert fallback is entry
    assert failing_client.calls == [("bar.txt", "-a\n+b\n")]
