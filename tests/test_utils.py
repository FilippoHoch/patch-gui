from __future__ import annotations

import pytest
from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from patch_gui.utils import decode_bytes, preprocess_patch_text


def test_decode_bytes_reports_encoding_without_fallback() -> None:
    data = "ciao".encode("utf-16")
    text, encoding, used_fallback = decode_bytes(data)
    assert text == "ciao"
    normalized = encoding.lower().replace("_", "-")
    assert normalized == "utf-16"
    assert used_fallback is False


def test_decode_bytes_uses_replace_when_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_detect(data: bytes) -> tuple[str, bool]:
        return "utf-8", True

    monkeypatch.setattr("patch_gui.utils.detect_encoding", fake_detect)

    data = b"caf\xe9"
    text, encoding, used_fallback = decode_bytes(data)
    assert text == "caf\ufffd"
    assert encoding == "utf-8"
    assert used_fallback is True


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


def test_preprocess_patch_text_repairs_incorrect_hunk_lengths() -> None:
    raw = (
        "--- a/sample.js\n"
        "+++ b/sample.js\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "-old2\n"
        "+new\n"
        "+new2\n"
    )

    with pytest.raises(UnidiffParseError):
        PatchSet(raw)

    processed = preprocess_patch_text(raw)
    patch = PatchSet(processed)

    header_line = processed.splitlines()[2]
    assert header_line == "@@ -1,2 +1,2 @@"
    hunk = patch[0][0]
    assert hunk.source_length == 2
    assert hunk.target_length == 2


def test_preprocess_patch_text_handles_no_newline_marker() -> None:
    raw = (
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "-foo\n"
        "+bar\n"
        "\\ No newline at end of file\n"
        "@@ -10,1 +10,1 @@\n"
        "-baz\n"
        "+qux\n"
    )

    processed = preprocess_patch_text(raw)
    patch = PatchSet(processed)

    first_hunk, second_hunk = patch[0]
    assert first_hunk.source_length == 1
    assert first_hunk.target_length == 1
    assert second_hunk.source_length == 1
    assert second_hunk.target_length == 1


def test_preprocess_patch_text_updates_missing_counts_for_empty_hunk() -> None:
    raw = (
        "--- a/empty.txt\n"
        "+++ b/empty.txt\n"
        "@@ -3 +3 @@\n"
    )

    processed = preprocess_patch_text(raw)
    header = processed.splitlines()[2]
    assert header == "@@ -3,0 +3,0 @@"


def test_preprocess_patch_text_fixes_counts_without_body_lines() -> None:
    raw = (
        "--- a/marker.txt\n"
        "+++ b/marker.txt\n"
        "@@ -1,1 +1,1 @@\n"
        "\\ No newline at end of file\n"
    )

    processed = preprocess_patch_text(raw)
    header, marker = processed.splitlines()[2:4]
    assert header == "@@ -1,0 +1,0 @@"
    assert marker == "\\ No newline at end of file"
