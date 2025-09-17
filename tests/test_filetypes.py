from __future__ import annotations

from typing import Iterable, Iterator

from unidiff import PatchSet
from unidiff.patch import PatchedFile

from patch_gui.filetypes import FileTypeInfo, inspect_file_type


def _first_file(diff: str) -> PatchedFile:
    patch = PatchSet(diff)
    return patch[0]


def test_inspect_python_file() -> None:
    diff = """--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-print('hi')\n+print('hello')\n"""
    info = inspect_file_type(_first_file(diff))
    assert info == FileTypeInfo(name="python")


def test_inspect_json_file() -> None:
    diff = """--- a/config.json\n+++ b/config.json\n@@ -1 +1 @@\n-{"a": 1}\n+{"a": 2}\n"""
    info = inspect_file_type(_first_file(diff))
    assert info.name == "json"
    assert info.preserve_final_newline is True


def test_inspect_special_filename() -> None:
    diff = """--- a/Makefile\n+++ b/Makefile\n@@ -1 +1 @@\n-old:\n+new:\n"""
    info = inspect_file_type(_first_file(diff))
    assert info.name == "makefile"


class _EmptyLine:
    line_type: str = ""
    value: str = ""


def test_inspect_binary_stub() -> None:
    class DummyBinary:
        path: str | None = "image.png"
        source_file: str | None = "image.png"
        target_file: str | None = "image.png"
        is_binary_file: bool | None = True

        def __iter__(self) -> Iterator[Iterable[_EmptyLine]]:  # pragma: no cover - protocol requirement
            return iter(())

    info = inspect_file_type(DummyBinary())
    assert info.name == "binary"
    assert info.preserve_trailing_whitespace is False


def test_inspect_unknown_defaults_to_text() -> None:
    diff = """--- a/notes\n+++ b/notes\n@@ -1 +1 @@\n-old\n+new\n"""
    info = inspect_file_type(_first_file(diff))
    assert info.name == "text"
