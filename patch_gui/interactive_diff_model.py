"""Shared data structures and helpers for the interactive diff widget."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from .localization import gettext as _

__all__ = [
    "FileDiffEntry",
    "enrich_entry_with_ai_note",
    "set_diff_note_client",
]


@dataclass(frozen=True, slots=True)
class FileDiffEntry:
    """Store information about a file diff block."""

    file_label: str
    diff_text: str
    annotated_diff_text: str
    additions: int
    deletions: int
    ai_note: str | None = None

    @property
    def display_text(self) -> str:
        additions = _("+{count}").format(count=self.additions)
        deletions = _("-{count}").format(count=self.deletions)
        return _("{name} · {additions} / {deletions}").format(
            name=self.file_label,
            additions=additions,
            deletions=deletions,
        )


class _DiffNoteClient(Protocol):
    """Protocol describing the minimal AI client for diff notes."""

    def generate_diff_note(self, file_label: str, diff_text: str) -> str | None:
        """Return a short note for the provided ``diff_text``."""


_ai_note_client: _DiffNoteClient | None = None


def set_diff_note_client(client: _DiffNoteClient | None) -> None:
    """Register the shared AI client used to enrich diff entries."""

    global _ai_note_client
    _ai_note_client = client


def enrich_entry_with_ai_note(entry: FileDiffEntry, *, enabled: bool) -> FileDiffEntry:
    """Populate ``entry`` with an AI-generated note when possible."""

    if not enabled or _ai_note_client is None:
        return entry

    if entry.ai_note is not None:
        return entry

    try:
        note = _ai_note_client.generate_diff_note(entry.file_label, entry.diff_text)
    except Exception:  # pragma: no cover - defensive guard
        note = None

    if not note:
        return entry

    return replace(entry, ai_note=note)
