"""Utilities to inspect file types from unified diff metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol


class _HunkLine(Protocol):
    line_type: str
    value: str


class _Hunk(Protocol):
    def __iter__(self) -> Iterator[_HunkLine]: ...


class _PatchLike(Protocol):
    path: str | None
    source_file: str | None
    target_file: str | None
    is_binary_file: bool | None

    def __iter__(self) -> Iterator[_Hunk]: ...


@dataclass(frozen=True)
class FileTypeInfo:
    """Describe the detected file type and preservation requirements."""

    name: str
    preserve_trailing_whitespace: bool = True
    preserve_final_newline: bool = True


_EXTENSION_MAP = {
    ".py": "python",
    ".pyi": "python",
    ".pyw": "python",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".md": "markdown",
    ".rst": "rst",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".xaml": "xml",
    ".xhtml": "xml",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".m": "objective-c",
    ".mm": "objective-c++",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".ps1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    ".scala": "scala",
    ".sql": "sql",
    ".po": "po",
    ".csv": "csv",
    ".tex": "tex",
    ".txt": "text",
}

_SPECIAL_FILENAMES = {
    "makefile": "makefile",
    "dockerfile": "dockerfile",
    "cmakelists.txt": "cmake",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "podfile": "ruby",
    "package.json": "json",
    "composer.json": "json",
    "poetry.lock": "toml",
    "pyproject.toml": "toml",
    "requirements.txt": "text",
    "license": "text",
    "readme": "markdown",
}


def inspect_file_type(patched_file: _PatchLike) -> FileTypeInfo:
    """Return a :class:`FileTypeInfo` describing ``patched_file``."""

    if getattr(patched_file, "is_binary_file", False):
        return FileTypeInfo(name="binary", preserve_trailing_whitespace=False)

    path = (
        (patched_file.path or patched_file.target_file or patched_file.source_file)
        or ""
    ).strip()
    lowered = path.lower()

    if lowered:
        suffix = Path(lowered).suffix
        if suffix in _EXTENSION_MAP:
            return FileTypeInfo(name=_EXTENSION_MAP[suffix])

        name = Path(lowered).name
        if name in _SPECIAL_FILENAMES:
            return FileTypeInfo(name=_SPECIAL_FILENAMES[name])

        stem = Path(lowered).stem
        if stem in _SPECIAL_FILENAMES:
            return FileTypeInfo(name=_SPECIAL_FILENAMES[stem])

    sample = _sample_content(patched_file)
    inferred = _infer_from_sample(sample)
    return FileTypeInfo(name=inferred)


def _sample_content(patched_file: _PatchLike, limit: int = 20) -> list[str]:
    lines: list[str] = []
    try:
        iterator = iter(patched_file)
    except TypeError:
        return lines

    for hunk in iterator:
        try:
            hunk_iter = iter(hunk)
        except TypeError:
            continue
        for line in hunk_iter:
            if getattr(line, "line_type", "") not in {" ", "+", "-"}:
                continue
            value = getattr(line, "value", "")
            stripped = value.strip()
            if stripped:
                lines.append(stripped)
            if len(lines) >= limit:
                return lines
    return lines


def _infer_from_sample(sample: list[str]) -> str:
    if not sample:
        return "text"

    joined = "\n".join(sample)
    first = sample[0]

    if first.startswith("{") or first.startswith("["):
        return "json"
    if first.startswith("<?xml") or first.startswith("<"):
        return "xml"
    if any(line.startswith("---") and ":" in line for line in sample):
        return "yaml"
    if any(line.startswith("#include") for line in sample):
        return "c"
    if any(line.startswith("def ") or line.startswith("class ") for line in sample):
        return "python"
    if any(
        line.startswith("function ") or line.startswith("const ") for line in sample
    ):
        return "javascript"
    if any(
        line.startswith("SELECT ") or line.startswith("CREATE TABLE") for line in sample
    ):
        return "sql"

    if joined.count("=") >= 2 and all("=" in line for line in sample[:5]):
        return "ini"
    if any(line.startswith("#!/") for line in sample):
        return "shell"

    return "text"


__all__ = ["FileTypeInfo", "inspect_file_type"]
