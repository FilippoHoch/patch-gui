from __future__ import annotations

import patch_gui.utils as utils


def test_preprocess_patch_text_normalizes_newlines_without_wrapper() -> None:
    raw = """--- a/file.txt\r\n+++ b/file.txt\r\n-old\r\n+new\r\n"""
    expected = """--- a/file.txt\n+++ b/file.txt\n-old\n+new\n"""
    assert utils.preprocess_patch_text(raw) == expected


def test_decode_bytes_returns_flag(monkeypatch) -> None:
    monkeypatch.setattr(utils, "detect_encoding", lambda data: ("utf-8", False))

    text, encoding, used_fallback = utils.decode_bytes(b"ciao")

    assert text == "ciao"
    assert encoding == "utf-8"
    assert used_fallback is False


def test_decode_bytes_uses_replace_on_fallback(monkeypatch) -> None:
    def fake_detect(data: bytes) -> tuple[str, bool]:
        return "utf-8", True

    monkeypatch.setattr(utils, "detect_encoding", fake_detect)

    text, encoding, used_fallback = utils.decode_bytes(b"caf\xff")

    assert text.endswith("\ufffd")
    assert encoding == "utf-8"
    assert used_fallback is True


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
    assert utils.preprocess_patch_text(raw) == expected
