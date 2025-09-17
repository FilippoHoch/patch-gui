from __future__ import annotations

from pathlib import Path, PureWindowsPath

import pytest
from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from patch_gui.utils import (
    decode_bytes,
    display_path,
    display_relative_path,
    preprocess_patch_text,
)


def test_decode_bytes_reports_encoding_without_fallback() -> None:
    data = "ciao".encode("utf-16")
    text, encoding, used_fallback = decode_bytes(data)
    assert text == "ciao"
    normalized = encoding.lower().replace("_", "-")
    assert normalized == "utf-16"
    assert used_fallback is False


def test_decode_bytes_uses_replace_when_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_preprocess_patch_text_rewrites_triple_asterisk_headers() -> None:
    raw = (
        "*** a/js/eventReview.js\n"
        "--- b/js/eventReview.js\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    processed = preprocess_patch_text(raw)
    lines = processed.splitlines()
    assert lines[0] == "--- a/js/eventReview.js"
    assert lines[1] == "+++ b/js/eventReview.js"

    patch = PatchSet(processed)
    assert len(patch) == 1
    assert patch[0].path == "js/eventReview.js"


def test_preprocess_patch_text_rewrites_triple_asterisk_headers_without_prefixes() -> None:
    raw = (
        "*** js/eventReview.js\n"
        "--- js/eventReview.js\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    processed = preprocess_patch_text(raw)
    lines = processed.splitlines()
    assert lines[0] == "--- a/js/eventReview.js"
    assert lines[1] == "+++ b/js/eventReview.js"

    patch = PatchSet(processed)
    assert len(patch) == 1
    assert patch[0].path == "js/eventReview.js"


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
        "--- a/sample.txt\n"
        "+++ b/sample.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "\\ No newline at end of file\n"
        "+new\n"
        "\\ No newline at end of file\n"
    )

    processed = preprocess_patch_text(raw)
    patch = PatchSet(processed)

    header_line = processed.splitlines()[2]
    assert header_line == "@@ -1 +1 @@"
    hunk = patch[0][0]
    assert hunk.source_length == 1
    assert hunk.target_length == 1


def test_preprocess_patch_text_allows_empty_hunks() -> None:
    raw = "--- a/empty.txt\n" "+++ b/empty.txt\n" "@@ -0,0 +0,0 @@\n"

    processed = preprocess_patch_text(raw)
    assert processed == raw


def test_preprocess_patch_text_infers_missing_counts() -> None:
    raw = (
        "--- a/config.ini\n"
        "+++ b/config.ini\n"
        "@@ -1 +1 @@\n"
        "-foo=1\n"
        "-bar=2\n"
        "+foo=10\n"
        "+bar=20\n"
    )

    processed = preprocess_patch_text(raw)
    header_line = processed.splitlines()[2]
    assert header_line == "@@ -1,2 +1,2 @@"


def test_display_path_normalizes_windows_separators() -> None:
    win_path = Path(PureWindowsPath(r"C:\\projects\\demo\\file.txt"))
    assert display_path(win_path) == "C:/projects/demo/file.txt"


def test_display_relative_path_handles_windows_paths() -> None:
    root = Path(PureWindowsPath(r"C:\\projects"))
    path = Path(PureWindowsPath(r"C:\\projects\\demo\\file.txt"))
    assert display_relative_path(path, root) == "demo/file.txt"


def test_display_relative_path_returns_absolute_when_outside_root() -> None:
    root = Path("/projects/root")
    path = Path("/other/location/file.txt")
    assert display_relative_path(path, root) == path.as_posix()
