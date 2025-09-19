"""Utility helpers to provide guidance when a hunk cannot be applied automatically."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
from typing import Sequence


@dataclass
class ConflictSuggestion:
    """Structured response describing how to resolve a failed hunk."""

    message: str
    patch: str | None = None
    source: str = "heuristic"
    confidence: float | None = None


def _build_patch(
    before_lines: Sequence[str], after_lines: Sequence[str], header: str
) -> str | None:
    """Return a minimal diff that the user can copy to apply manually."""

    diff_lines = list(
        unified_diff(
            before_lines,
            after_lines,
            fromfile="original",
            tofile="suggested",
            lineterm="",
        )
    )
    if not diff_lines and not header:
        return None
    result: list[str] = []
    if header:
        result.append(header)
    result.extend(diff_lines)
    return "\n".join(result).strip() or None


def _extract_context(
    file_context: str, before_text: str, window: int = 120
) -> str | None:
    if not file_context or not before_text:
        return None
    idx = file_context.find(before_text)
    if idx == -1:
        return None
    start = max(0, idx - window)
    end = min(len(file_context), idx + len(before_text) + window)
    snippet = file_context[start:end]
    return snippet.strip() or None


def generate_conflict_suggestion(
    *,
    file_context: str,
    hunk_header: str,
    before_lines: Sequence[str],
    after_lines: Sequence[str],
    failure_reason: str,
    original_diff: str,
) -> ConflictSuggestion | None:
    """Return textual guidance and a patch snippet to resolve a failed hunk.

    The implementation relies on lightweight heuristics so that the feature works
    without network access.  The generated message explains why the assistant was
    triggered and offers a compact diff that can be copied into the target file
    manually.
    """

    before_text = "".join(before_lines)
    after_text = "".join(after_lines)

    if not (before_text or after_text or original_diff.strip()):
        return None

    failure_reason = failure_reason.strip()

    message_lines: list[str] = []
    intro = "Suggerimento assistente: analizza il blocco seguente e applica le modifiche manualmente."
    message_lines.append(intro)
    if failure_reason:
        message_lines.append(f"Motivo del fallimento: {failure_reason}.")

    if before_text and after_text:
        message_lines.append(
            "Sostituisci il blocco corrente con la versione proposta mantenendo eventuali adattamenti necessari."
        )
    elif after_text:
        message_lines.append(
            "Inserisci il nuovo blocco nel punto corretto del file, verificando l'indentazione e il contesto."
        )
    else:
        message_lines.append(
            "Rimuovi manualmente le righe indicate e conferma che il contesto rimanente sia coerente."
        )

    context_excerpt = _extract_context(file_context, before_text)
    if context_excerpt:
        message_lines.append("Contesto trovato nel file:")
        message_lines.append(context_excerpt)

    patch_text = (original_diff.strip() or None) or _build_patch(
        before_lines, after_lines, hunk_header
    )
    if patch_text:
        message_lines.append(
            "È possibile copiare il diff suggerito per applicarlo manualmente."
        )

    message = "\n".join(message_lines)

    return ConflictSuggestion(message=message, patch=patch_text)
