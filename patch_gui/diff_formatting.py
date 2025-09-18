"""Utilities to enrich diff previews with additional metadata."""

from __future__ import annotations

from unidiff.patch import Hunk, Line as UnidiffLine, PatchedFile


def format_diff_with_line_numbers(patched_file: PatchedFile, fallback_text: str) -> str:
    """Decorate a diff with source/target line numbers when possible."""

    if getattr(patched_file, "is_binary_file", False):
        return fallback_text

    if len(patched_file) == 0:
        return fallback_text

    try:
        lines: list[str] = []

        patch_info = getattr(patched_file, "patch_info", "")
        if patch_info:
            for info_line in str(patch_info).splitlines():
                lines.append(info_line)

        source_file = getattr(patched_file, "source_file", None) or "-"
        target_file = getattr(patched_file, "target_file", None) or "-"
        lines.append(f"--- {source_file}")
        lines.append(f"+++ {target_file}")

        for hunk in patched_file:
            lines.append(_format_hunk_header(hunk))
            for diff_line in hunk:
                lines.append(_format_numbered_line(diff_line))

        return "\n".join(lines) + "\n"
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
