"""Utilities to enrich diff previews with additional metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from unidiff.patch import Hunk, Line as UnidiffLine, PatchedFile


@dataclass(frozen=True, slots=True)
class RenderedHunk:
    """Container for the rendered representation of a diff hunk."""

    header: str
    raw_text: str
    annotated_text: str


@dataclass(frozen=True, slots=True)
class RenderedDiff:
    """Split representation of a ``PatchedFile`` ready for display/export."""

    header_text: str
    annotated_header_text: str
    hunks: Tuple[RenderedHunk, ...]


def render_diff_segments(patched_file: PatchedFile) -> RenderedDiff:
    """Return header and hunk segments for ``patched_file``.

    The returned object contains both the raw diff data and the annotated
    representation enriched with line numbers. Callers can combine the pieces to
    generate a full diff string or render hunks individually.
    """

    patch_info = getattr(patched_file, "patch_info", "")
    header_lines = []
    if patch_info:
        header_lines.extend(str(patch_info).splitlines())

    source_file = getattr(patched_file, "source_file", None) or "-"
    target_file = getattr(patched_file, "target_file", None) or "-"
    header_lines.append(f"--- {source_file}")
    header_lines.append(f"+++ {target_file}")

    header_text = "\n".join(header_lines) + "\n"

    hunks: list[RenderedHunk] = []
    for hunk in patched_file:
        header = _format_hunk_header(hunk)
        annotated_lines = [header]
        for diff_line in hunk:
            annotated_lines.append(_format_numbered_line(diff_line))
        annotated_text = "\n".join(annotated_lines) + "\n"
        raw_text = str(hunk)
        hunks.append(
            RenderedHunk(
                header=header,
                raw_text=raw_text,
                annotated_text=annotated_text,
            )
        )

    return RenderedDiff(
        header_text=header_text,
        annotated_header_text=header_text,
        hunks=tuple(hunks),
    )


def format_diff_with_line_numbers(patched_file: PatchedFile, fallback_text: str) -> str:
    """Decorate a diff with source/target line numbers when possible."""

    if getattr(patched_file, "is_binary_file", False):
        return fallback_text

    if len(patched_file) == 0:
        return fallback_text

    try:
        rendered = render_diff_segments(patched_file)
        if not rendered.hunks:
            return fallback_text
        parts = [rendered.annotated_header_text]
        parts.extend(h.annotated_text for h in rendered.hunks)
        return "".join(parts)
    except Exception:  # pragma: no cover - defensive, falls back to raw diff text
        return fallback_text


def _format_hunk_header(hunk: Hunk) -> str:
    """Render the unified diff header for ``hunk``."""

    return "@@ -{source} +{target} @@{section}".format(
        source=_format_hunk_range(hunk.source_start, hunk.source_length),
        target=_format_hunk_range(hunk.target_start, hunk.target_length),
        section=f" {hunk.section_header}" if hunk.section_header else "",
    )


def _format_hunk_range(start: int, length: int) -> str:
    if length == 1:
        return str(start)
    return f"{start},{length}"


def _format_numbered_line(line: UnidiffLine) -> str:
    left = _format_line_number(line.source_line_no)
    right = _format_line_number(line.target_line_no)
    content = str(line).rstrip("\n")
    return f"{left} │ {right} │ {content}"


def _format_line_number(value: int | None) -> str:
    return f"{value:>6}" if value is not None else " " * 6
