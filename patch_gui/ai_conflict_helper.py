"""Utilities for generating AI-style suggestions when a hunk cannot be applied."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Sequence

from patch_gui.localization import gettext as _


@dataclass
class AISuggestion:
    """Container for textual hints and optional patch snippets."""

    summary: str
    context_excerpt: str | None = None
    patch: str | None = None

    def as_text(self) -> str:
        """Return a human friendly string that merges all the available hints."""

        parts: list[str] = []
        summary = self.summary.strip()
        if summary:
            parts.append(summary)
        if self.context_excerpt:
            parts.append("")
            parts.append(_("Contesto individuato nel file:"))
            parts.append(self.context_excerpt.rstrip("\n"))
        if self.patch:
            parts.append("")
            parts.append(_("Patch suggerita:"))
            parts.append(self.patch.rstrip("\n"))
        return "\n".join(parts).strip()


def _best_context_excerpt(
    file_context: Sequence[str],
    reference_lines: Sequence[str],
    *,
    padding: int = 3,
    fallback_window: int = 20,
) -> str | None:
    """Return a slice of ``file_context`` that best matches ``reference_lines``."""

    if not file_context:
        return None

    if not reference_lines:
        excerpt = file_context[-min(len(file_context), fallback_window) :]
        return "".join(excerpt)

    window = len(reference_lines)
    if window == 0:
        return None

    reference_text = "".join(reference_lines)
    best_score = 0.0
    best_index: int | None = None

    max_start = max(0, len(file_context) - window)
    for start in range(0, max_start + 1):
        candidate_text = "".join(file_context[start : start + window])
        score = SequenceMatcher(None, candidate_text, reference_text).ratio()
        if score > best_score:
            best_score = score
            best_index = start

    if best_index is None:
        excerpt = file_context[-min(len(file_context), fallback_window) :]
        return "".join(excerpt)

    start = max(0, best_index - padding)
    end = min(len(file_context), best_index + window + padding)
    excerpt = file_context[start:end]
    return "".join(excerpt)


def _format_diff(
    header: str | None,
    before_lines: Sequence[str],
    after_lines: Sequence[str],
    *,
    diff_text: str | None = None,
) -> str | None:
    """Return a unified-diff style patch snippet for the provided hunk."""

    if diff_text:
        return diff_text

    lines: list[str] = []
    if header:
        header_line = header if header.endswith("\n") else f"{header}\n"
        lines.append(header_line)
    for line in before_lines:
        prefix = "-"
        lines.append(f"{prefix}{line}" if line.endswith("\n") else f"{prefix}{line}\n")
    for line in after_lines:
        prefix = "+"
        lines.append(f"{prefix}{line}" if line.endswith("\n") else f"{prefix}{line}\n")
    if not lines:
        return None
    return "".join(lines)


def build_conflict_suggestion(
    file_context: Sequence[str],
    *,
    failure_reason: str,
    before_lines: Sequence[str] | None = None,
    after_lines: Sequence[str] | None = None,
    header: str | None = None,
    diff_text: str | None = None,
    extra_notes: Iterable[str] | None = None,
) -> AISuggestion:
    """Generate an ``AISuggestion`` describing how to resolve a hunk conflict."""

    before_lines = list(before_lines or [])
    after_lines = list(after_lines or [])

    summary_lines: list[str] = []
    reason = failure_reason.strip() or _("Motivo non disponibile")
    summary_lines.append(
        _("Motivo del fallimento: {reason}").format(reason=reason)
    )

    if after_lines:
        summary_lines.append(
            _(
                "Applica manualmente le righe proposte oppure incolla la patch suggerita "
                "nel file."
            )
        )
    else:
        summary_lines.append(
            _(
                "Rivedi il contesto per adattare manualmente il contenuto del file."
            )
        )

    if extra_notes:
        for note in extra_notes:
            cleaned = note.strip()
            if cleaned:
                summary_lines.append(f"- {cleaned}")

    excerpt = _best_context_excerpt(file_context, before_lines or after_lines)
    patch = _format_diff(header, before_lines, after_lines, diff_text=diff_text)

    return AISuggestion(
        summary="\n".join(summary_lines),
        context_excerpt=excerpt,
        patch=patch,
    )
