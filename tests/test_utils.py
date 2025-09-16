from __future__ import annotations

from patch_gui.utils import preprocess_patch_text


def test_preprocess_patch_text_normalizes_newlines_without_wrapper() -> None:
    raw = """--- a/file.txt\r\n+++ b/file.txt\r\n-old\r\n+new\r\n"""
    expected = """--- a/file.txt\n+++ b/file.txt\n-old\n+new\n"""
    assert preprocess_patch_text(raw) == expected


def test_preprocess_patch_text_extracts_begin_patch_blocks() -> None:
    raw = (
        "*** Begin Patch\n"
        "*** Update File: foo.txt\n"
        "@@\n"
        "-old line\n"
        "+new line\n"
        "*** Update File: bar/baz.txt\n"
        "@@ -1 +1 @@ suffix\n"
        "-foo\n"
        "+bar\n"
        "*** End Patch\n"
    )
    expected = (
        "--- a/foo.txt\n"
        "+++ b/foo.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-old line\n"
        "+new line\n"
        "--- a/bar/baz.txt\n"
        "+++ b/bar/baz.txt\n"
        "@@ -1 +1 @@ suffix\n"
        "-foo\n"
        "+bar\n"
    )
    assert preprocess_patch_text(raw) == expected
