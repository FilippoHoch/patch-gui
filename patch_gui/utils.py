"""Utility helpers for patch processing and shared configuration."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

try:  # pragma: no cover - optional dependency imported at runtime
    from charset_normalizer import from_bytes as _cn_from_bytes
except ImportError:  # pragma: no cover - library not installed in runtime env
    _cn_from_bytes = None

APP_NAME = "Patch GUI – Diff Applier"
BACKUP_DIR = ".diff_backups"
REPORT_JSON = "apply-report.json"
REPORT_TXT = "apply-report.txt"

BEGIN_PATCH_RE = re.compile(r"^\*\*\* Begin Patch", re.MULTILINE)
END_PATCH_RE = re.compile(r"^\*\*\* End Patch", re.MULTILINE)
UPDATE_FILE_RE = re.compile(r"^\*\*\* Update File: (.+)$", re.MULTILINE)
HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@.*$")


_BOM_PREFIXES = [
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
]


def detect_encoding(data: bytes) -> Tuple[str, bool]:
    """Return the detected encoding for ``data`` and whether it was a fallback."""

    if _cn_from_bytes is not None:
        match = _cn_from_bytes(data).best()
        if match and match.encoding:
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
    """Decode ``data`` using the detected encoding with UTF-8 fallback.

    Returns the decoded text, the encoding used and a boolean indicating
    whether the fallback behaviour (``errors="replace"``) was required.
    """

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


def preprocess_patch_text(raw_text: str) -> str:
    """Accept either unified diff or "*** Begin Patch" formats and return diff text."""

    text = normalize_newlines(raw_text)

    if not BEGIN_PATCH_RE.search(text):
        return text

    parts = []
    pos = 0
    while True:
        m_begin = BEGIN_PATCH_RE.search(text, pos)
        if not m_begin:
            break
        m_end = END_PATCH_RE.search(text, m_begin.end())
        if not m_end:
            block = text[m_begin.end():]
            pos = len(text)
        else:
            block = text[m_begin.end(): m_end.start()]
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
                    removed = sum(1 for l in body if l.startswith((" ", "-")))
                    added = sum(1 for l in body if l.startswith((" ", "+")))
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

    return "".join(parts)


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
