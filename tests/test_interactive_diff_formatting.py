"""Tests for line-number formatting in the interactive diff preview."""

from __future__ import annotations

from unidiff import PatchSet

from patch_gui.diff_formatting import format_diff_with_line_numbers


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
