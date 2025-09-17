"""Utility helpers for patch processing and shared configuration."""

from __future__ import annotations

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
        body_index = body_start
        old_count = 0
        new_count = 0

        while body_index < total:
            body_line = lines[body_index]
            if body_line.startswith("@@"):
                break
            if body_line.startswith("+++ ") or body_line.startswith("--- "):
                break
            if not body_line:
                break

            prefix = body_line[0]
            if prefix not in {" ", "+", "-", "\\"}:
                break
            if prefix in {" ", "-"}:
                old_count += 1
            if prefix in {" ", "+"}:
                new_count += 1

            body_index += 1

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


def preprocess_patch_text(raw_text: str) -> str:
    """Accept either unified diff or "*** Begin Patch" formats and return diff text."""

    text = normalize_newlines(raw_text)

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


__all__ = [
    "APP_NAME",
    "BACKUP_DIR",
    "REPORT_JSON",
    "REPORT_TXT",
    "decode_bytes",
    "detect_encoding",
    "normalize_newlines",
    "preprocess_patch_text",
    "write_text_preserving_encoding",
]
