"""Utilities for searching diff text inside Qt widgets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from PySide6 import QtCore, QtGui, QtWidgets

__all__ = [
    "DiffSearchHelper",
    "DiffSearchMatch",
]


@dataclass(frozen=True, slots=True)
class DiffSearchMatch:
    """Container describing a text match inside a diff document."""

    start: int
    end: int
    line: int
    column: int
    length: int
    text: str


class DiffSearchHelper(QtCore.QObject):
    """Search controller that highlights matches inside ``QPlainTextEdit`` widgets."""

    resultsChanged = QtCore.Signal(int)
    currentMatchChanged = QtCore.Signal(object, int, int)

    def __init__(
        self,
        editor: QtWidgets.QPlainTextEdit,
        *,
        case_sensitive: bool = False,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._editor = editor
        self._case_sensitive = case_sensitive
        self._query: str = ""
        self._matches: List[DiffSearchMatch] = []
        self._current_index: int = -1

        palette = editor.palette()
        highlight_color = palette.color(QtGui.QPalette.ColorRole.Highlight)
        current = QtGui.QColor(highlight_color)
        current.setAlpha(140)
        background = QtGui.QColor(highlight_color)
        background.setAlpha(70)

        self._match_format = QtGui.QTextCharFormat()
        self._match_format.setBackground(background)

        self._current_format = QtGui.QTextCharFormat()
        self._current_format.setBackground(current)

        editor.textChanged.connect(self._on_editor_text_changed)

    @property
    def case_sensitive(self) -> bool:
        """Return whether searches are case-sensitive."""

        return self._case_sensitive

    def set_case_sensitive(self, enabled: bool) -> None:
        """Toggle case-sensitive searches and refresh results."""

        if self._case_sensitive == enabled:
            return
        self._case_sensitive = enabled
        if self._query:
            self.search(self._query)

    @property
    def query(self) -> str:
        """Return the last search query."""

        return self._query

    @property
    def matches(self) -> Sequence[DiffSearchMatch]:
        """Return an immutable view of the current matches."""

        return tuple(self._matches)

    @property
    def current_index(self) -> int:
        """Return the index of the active match, or ``-1`` when unavailable."""

        return self._current_index

    @property
    def current_match(self) -> DiffSearchMatch | None:
        """Return the active match or ``None`` when no results exist."""

        if 0 <= self._current_index < len(self._matches):
            return self._matches[self._current_index]
        return None

    def clear(self) -> None:
        """Remove all highlights and reset the internal state."""

        self._query = ""
        self._matches.clear()
        self._current_index = -1
        self._apply_highlights()
        self.resultsChanged.emit(0)
        self.currentMatchChanged.emit(None, -1, 0)

    def search(self, query: str) -> None:
        """Search ``query`` inside the attached editor and highlight matches."""

        if not query:
            self.clear()
            return

        text = self._editor.toPlainText()
        if not text:
            self.clear()
            self._query = query
            return

        self._query = query
        target = query if self._case_sensitive else query.casefold()
        haystack = text if self._case_sensitive else text.casefold()

        matches: List[DiffSearchMatch] = []
        start = 0
        step = max(len(target), 1)
        while True:
            index = haystack.find(target, start)
            if index < 0:
                break
            end = index + len(query)
            block = self._editor.document().findBlock(index)
            line = block.blockNumber()
            column = index - block.position()
            matches.append(
                DiffSearchMatch(
                    start=index,
                    end=end,
                    line=line,
                    column=column,
                    length=len(query),
                    text=text[index:end],
                )
            )
            start = index + step

        self._matches = matches
        self._current_index = 0 if matches else -1
        self._apply_highlights()
        self.resultsChanged.emit(len(matches))
        self._emit_current_match()

    def find_next(self) -> None:
        """Advance to the next match, wrapping around when necessary."""

        if not self._matches:
            return
        self._current_index = (self._current_index + 1) % len(self._matches)
        self._apply_highlights()
        self._emit_current_match()

    def find_previous(self) -> None:
        """Move to the previous match, wrapping around when necessary."""

        if not self._matches:
            return
        self._current_index = (self._current_index - 1) % len(self._matches)
        self._apply_highlights()
        self._emit_current_match()

    def _on_editor_text_changed(self) -> None:  # pragma: no cover - UI integration
        if not self._query:
            return
        QtCore.QTimer.singleShot(0, self._refresh_matches)

    def _refresh_matches(self) -> None:
        if self._query:
            self.search(self._query)

    def _apply_highlights(self) -> None:
        selections: list[QtWidgets.QTextEdit.ExtraSelection] = []
        for idx, match in enumerate(self._matches):
            selection = QtWidgets.QTextEdit.ExtraSelection()
            cursor = QtGui.QTextCursor(self._editor.document())
            cursor.setPosition(match.start)
            cursor.setPosition(match.end, QtGui.QTextCursor.MoveMode.KeepAnchor)
            selection.cursor = cursor
            selection.format = (
                self._current_format
                if idx == self._current_index
                else self._match_format
            )
            selections.append(selection)

        self._editor.setExtraSelections(selections)

        if 0 <= self._current_index < len(self._matches):
            current = self._matches[self._current_index]
            cursor = QtGui.QTextCursor(self._editor.document())
            cursor.setPosition(current.start)
            cursor.setPosition(current.end, QtGui.QTextCursor.MoveMode.KeepAnchor)
            self._editor.setTextCursor(cursor)
            self._editor.centerCursor()

    def _emit_current_match(self) -> None:
        match = self.current_match
        total = len(self._matches)
        self.currentMatchChanged.emit(match, self._current_index, total)
