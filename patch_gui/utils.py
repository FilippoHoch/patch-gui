"""Utility helpers for patch processing and shared configuration."""

from __future__ import annotations

from datetime import datetime
import re
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Tuple, cast


class _CharsetMatch(Protocol):
    encoding: Optional[str]


class _CharsetMatches(Protocol):
    def best(self) -> Optional[_CharsetMatch]:
        """Return the best match for the analysed bytes if available."""


_CNFromBytes = Callable[[bytes], _CharsetMatches]

try:  # pragma: no cover - optional dependency imported at runtime
    from charset_normalizer import from_bytes as _charset_from_bytes
except ImportError:  # pragma: no cover - library not installed in runtime env
    _cn_from_bytes: _CNFromBytes | None = None
else:
    _cn_from_bytes = cast(_CNFromBytes, _charset_from_bytes)

APP_NAME = "Patch GUI – Diff Applier"
BACKUP_DIR = ".diff_backups"
REPORT_JSON = "apply-report.json"
REPORT_TXT = "apply-report.txt"

_PACKAGE_ROOT = Path(__file__).resolve().parent
REPORTS_SUBDIR = "reports"
REPORT_RESULTS_SUBDIR = "results"
DEFAULT_REPORTS_DIR = _PACKAGE_ROOT / REPORTS_SUBDIR / REPORT_RESULTS_SUBDIR


def display_path(path: Path) -> str:
    """Return ``path`` using forward slashes, regardless of the platform."""

    path_text = str(Path(path))
    if "\\" in path_text:
        return path_text.replace("\\", "/")
    return path_text


def display_relative_path(path: Path, root: Path) -> str:
    """Return a relative path using forward slashes when ``path`` is under ``root``."""

    path_obj = Path(path)
    root_obj = Path(root)
    try:
        relative = path_obj.relative_to(root_obj)
    except ValueError:
        return display_path(path_obj)
    return relative.as_posix()


BEGIN_PATCH_RE = re.compile(r"^\*\*\* Begin Patch", re.MULTILINE)
END_PATCH_RE = re.compile(r"^\*\*\* End Patch", re.MULTILINE)
UPDATE_FILE_RE = re.compile(r"^\*\*\* Update File: (.+)$", re.MULTILINE)
HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@.*$")
HUNK_HEADER_DETAIL_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<suffix>.*)$"
)


_BOM_PREFIXES = [
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
]


def detect_encoding(data: bytes) -> Tuple[str, bool]:
    """Return the detected encoding for ``data`` and whether it was a fallback."""

    if _cn_from_bytes is not None:
        match = _cn_from_bytes(data).best()
        if match is not None and match.encoding:
            encoding = match.encoding
            try:
                data.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                pass
            else:
                return encoding, False

    for bom, encoding in _BOM_PREFIXES:
        if data.startswith(bom):
            try:
                data.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
            return encoding, False

    return "utf-8", True


def decode_bytes(data: bytes) -> Tuple[str, str, bool]:
    """Decode ``data`` and return the text, encoding, and fallback flag."""

    encoding, used_fallback = detect_encoding(data)
    if used_fallback:
        text = data.decode(encoding, errors="replace")
    else:
        text = data.decode(encoding)
    return text, encoding, used_fallback


def write_text_preserving_encoding(path: Path, text: str, encoding: str) -> None:
    """Write ``text`` using ``encoding`` and fall back to UTF-8 on failure."""

    try:
        path.write_text(text, encoding=encoding)
    except (LookupError, UnicodeEncodeError):
        path.write_text(text, encoding="utf-8")


def normalize_newlines(text: str) -> str:
    """Normalize different newline styles to ``"\n"``."""

    return text.replace("\r\n", "\n").replace("\r", "\n")


def _hunk_body_line_effect(line: str) -> Tuple[bool, int, int]:
    """Return whether ``line`` is part of the hunk body and its line counters."""

    if line.startswith("@@"):
        return False, 0, 0
    if line.startswith("+++ ") or line.startswith("--- "):
        return False, 0, 0
    if not line:
        return False, 0, 0

    prefix = line[0]
    if prefix not in {" ", "+", "-", "\\"}:
        return False, 0, 0

    old_increment = 1 if prefix in {" ", "-"} else 0
    new_increment = 1 if prefix in {" ", "+"} else 0
    return True, old_increment, new_increment


def _scan_hunk_body(lines: List[str], start: int) -> Tuple[int, int, int]:
    """Return the end index and counters for the hunk body starting at ``start``."""

    index = start
    old_count = 0
    new_count = 0
    total = len(lines)

    while index < total:
        continue_body, old_increment, new_increment = _hunk_body_line_effect(
            lines[index]
        )
        if not continue_body:
            break
        old_count += old_increment
        new_count += new_increment
        index += 1

    return index, old_count, new_count


def _normalize_hunk_line_counts(text: str) -> str:
    """Ensure hunk headers declare counts matching their body length."""

    lines = text.splitlines()
    if not lines:
        return text

    trailing_newline = text.endswith("\n")
    normalized: List[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        match = HUNK_HEADER_DETAIL_RE.match(line)
        if not match:
            normalized.append(line)
            index += 1
            continue

        body_start = index + 1
        body_index, old_count, new_count = _scan_hunk_body(lines, body_start)

        expected_old = (
            int(match.group("old_count")) if match.group("old_count") is not None else 1
        )
        expected_new = (
            int(match.group("new_count")) if match.group("new_count") is not None else 1
        )
        suffix = match.group("suffix") or ""

        if old_count == expected_old and new_count == expected_new:
            normalized.append(line)
        else:
            normalized.append(
                f"@@ -{match.group('old_start')},{old_count} +{match.group('new_start')},{new_count} @@{suffix}"
            )

        normalized.extend(lines[body_start:body_index])
        index = body_index

    result = "\n".join(normalized)
    if trailing_newline:
        result += "\n"
    return result


def _normalize_nonstandard_file_headers(text: str) -> str:
    """Rewrite non-standard ``***``/``---`` headers into unified diff headers.

    Some tools emit diffs whose file headers use ``***`` for the source file and
    ``---`` for the target file instead of the standard ``---``/``+++`` pair.
    The ``unidiff`` parser treats such patches as invalid and therefore returns
    an empty ``PatchSet``. To keep compatibility with these diffs we rewrite the
    header pair whenever both lines start with the expected ``a/`` or ``b/``
    prefixes.
    """

    lines = text.splitlines()
    if not lines:
        return text

    changed = False
    limit = len(lines) - 1
    for idx in range(limit):
        line = lines[idx]
        if not line.startswith("*** "):
            continue
        if " Begin Patch" in line or " End Patch" in line:
            continue
        source = line[4:]
        if not source.startswith(("a/", "b/")):
            continue
        target_line = lines[idx + 1]
        if not target_line.startswith("--- "):
            continue
        target = target_line[4:]
        if not target.startswith(("a/", "b/")):
            continue

        lines[idx] = f"--- {source}"
        lines[idx + 1] = f"+++ {target}"
        changed = True

    if not changed:
        return text

    normalized = "\n".join(lines)
    if text.endswith("\n"):
        normalized += "\n"
    return normalized


def preprocess_patch_text(raw_text: str) -> str:
    """Normalize ``raw_text`` and extract diff content from known patch formats.

    The helper accepts raw unified diff text or the "*** Begin Patch" wrapper
    used by GitHub suggestions. It normalizes newline styles, flattens wrapped
    patches into regular unified diffs, and repairs hunk headers whose line
    counts do not match their bodies (including hunks without explicit counts,
    empty hunks, or those containing ``"\\ No newline at end of file"`` markers).
    """

    text = normalize_newlines(raw_text)
    text = _normalize_nonstandard_file_headers(text)

    if not BEGIN_PATCH_RE.search(text):
        return _normalize_hunk_line_counts(text)

    parts = []
    pos = 0
    while True:
        m_begin = BEGIN_PATCH_RE.search(text, pos)
        if not m_begin:
            break
        m_end = END_PATCH_RE.search(text, m_begin.end())
        if not m_end:
            block = text[m_begin.end() :]
            pos = len(text)
        else:
            block = text[m_begin.end() : m_end.start()]
            pos = m_end.end()

        files = [m for m in UPDATE_FILE_RE.finditer(block)]
        for i, m_up in enumerate(files):
            start = m_up.end()
            end = files[i + 1].start() if i + 1 < len(files) else len(block)
            filename = m_up.group(1).strip()
            hunks = block[start:end].strip("\n")
            if not hunks:
                continue
            header = f"--- a/{filename}\n+++ b/{filename}\n"
            raw_lines = []
            for line in hunks.splitlines():
                if line.startswith("@@") or line.startswith(("+", "-", " ", "\\")):
                    raw_lines.append(line)
            if not raw_lines:
                continue

            def finalize_hunk(lines: List[str]) -> List[str]:
                if not lines:
                    return []
                header_line = lines[0]
                body = lines[1:]
                if not HUNK_HEADER_RE.match(header_line):
                    suffix = lines[0][2:].strip()
                    removed = sum(1 for line in body if line.startswith((" ", "-")))
                    added = sum(1 for line in body if line.startswith((" ", "+")))
                    old_start = 1 if removed > 0 else 0
                    new_start = 1 if added > 0 else 0
                    header_line = f"@@ -{old_start},{removed} +{new_start},{added} @@"
                    if suffix:
                        header_line += f" {suffix}"
                return [header_line, *body]

            normalized_lines: List[str] = []
            current_hunk: List[str] = []
            for line in raw_lines:
                if line.startswith("@@"):
                    if current_hunk:
                        normalized_lines.extend(finalize_hunk(current_hunk))
                    current_hunk = [line]
                else:
                    if not current_hunk:
                        continue
                    current_hunk.append(line)
            if current_hunk:
                normalized_lines.extend(finalize_hunk(current_hunk))

            if normalized_lines:
                parts.append(header + "\n".join(normalized_lines) + "\n")

    return _normalize_hunk_line_counts("".join(parts))


def format_session_timestamp(started_at: float) -> str:
    """Return a filesystem-friendly timestamp label for ``started_at``."""

    dt = datetime.fromtimestamp(started_at)
    fractional = int((started_at - int(started_at)) * 1000)
    return f"{dt.strftime('%Y%m%d-%H%M%S')}-{fractional:03d}"


def default_session_report_dir(started_at: float) -> Path:
    """Return the default directory where reports for ``started_at`` should be saved."""

    return DEFAULT_REPORTS_DIR / format_session_timestamp(started_at)


__all__ = [
    "APP_NAME",
    "BACKUP_DIR",
    "REPORT_JSON",
    "REPORT_TXT",
    "DEFAULT_REPORTS_DIR",
    "REPORT_RESULTS_SUBDIR",
    "REPORTS_SUBDIR",
    "default_session_report_dir",
    "format_session_timestamp",
    "decode_bytes",
    "detect_encoding",
    "display_path",
    "display_relative_path",
    "normalize_newlines",
    "preprocess_patch_text",
    "write_text_preserving_encoding",
]
