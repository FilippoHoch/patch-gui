"""Shared data structures for the interactive diff widget."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
from typing import Protocol

from .localization import gettext as _


logger = logging.getLogger(__name__)


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


class DiffAiNoteClient(Protocol):
    """Protocol for services that can summarise diff entries."""

    def note_for_diff(self, entry: FileDiffEntry) -> str | None:
        """Return a short note for ``entry`` or ``None`` if not available."""


_AI_NOTE_CLIENT: DiffAiNoteClient | None = None


def set_diff_ai_note_client(client: DiffAiNoteClient | None) -> None:
    """Register ``client`` as the shared provider for AI notes."""

    global _AI_NOTE_CLIENT
    _AI_NOTE_CLIENT = client


def get_diff_ai_note_client() -> DiffAiNoteClient | None:
    """Return the configured AI note provider, if any."""

    return _AI_NOTE_CLIENT


def populate_ai_note(entry: FileDiffEntry) -> FileDiffEntry:
    """Return ``entry`` enriched with an AI note when possible."""

    client = get_diff_ai_note_client()
    if client is None:
        return entry

    try:
        raw_note = client.note_for_diff(entry)
    except Exception:  # pragma: no cover - best effort logging
        logger.debug("AI note client failed", exc_info=True)
        raw_note = None

    note = (str(raw_note).strip() if raw_note is not None else None) or None
    if note == entry.ai_note:
        return entry
    if note is None and entry.ai_note is None:
        return entry
    return replace(entry, ai_note=note)


__all__ = [
    "DiffAiNoteClient",
    "FileDiffEntry",
    "get_diff_ai_note_client",
    "populate_ai_note",
    "set_diff_ai_note_client",
]
