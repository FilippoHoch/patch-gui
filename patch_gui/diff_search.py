"""Search helper for highlighting matches inside diff editors."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets


@dataclass(slots=True)
class _Match:
    """Representation of a located match in a text document."""

    start: int
    end: int


class DiffSearchHelper(QtCore.QObject):
    """Drive ``QPlainTextEdit`` search highlighting via ``QTextCursor``."""

    matchChanged = QtCore.Signal(int, int, int, int)
    """Signal emitted when the current match changes.

    It exposes the current match index (0-based), total match count, and the
    ``start``/``end`` positions within the underlying document. ``index`` is
    ``-1`` when there is no active match.
    """

    patternChanged = QtCore.Signal(str)
    """Signal emitted whenever the search pattern is updated."""

    def __init__(
        self,
        editor: QtWidgets.QPlainTextEdit,
        *,
        case_sensitive: bool = False,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._editor = editor
        self._document = editor.document()
        self._case_sensitive = case_sensitive
        self._pattern: str = ""
        self._matches: list[_Match] = []
        self._current_index: int = -1
        self._document_dirty = False

        self._highlight_brush = QtGui.QBrush(
            editor.palette().color(QtGui.QPalette.ColorRole.Highlight).lighter(160)
        )
        self._current_match_brush = QtGui.QBrush(
            editor.palette().color(QtGui.QPalette.ColorRole.Highlight).lighter(120)
        )

        self._document.contentsChange.connect(self._on_contents_change)

    @property
    def pattern(self) -> str:
        """Return the currently active search pattern."""

        return self._pattern

    @property
    def match_count(self) -> int:
        """Return the number of matches for the current pattern."""

        return len(self._matches)

    @property
    def current_index(self) -> int:
        """Return the index of the current match or ``-1`` if unavailable."""

        return self._current_index

    def set_case_sensitive(self, enabled: bool) -> None:
        """Toggle case sensitivity for subsequent searches."""

        if self._case_sensitive == enabled:
            return
        self._case_sensitive = enabled
        if self._pattern:
            self.set_pattern(self._pattern, restart=False)

    def clear(self) -> None:
        """Clear the current search pattern and highlighting."""

        self._pattern = ""
        self._matches.clear()
        self._current_index = -1
        self._apply_highlight()
        self.matchChanged.emit(-1, 0, -1, -1)

    def set_pattern(self, pattern: str, *, restart: bool = True) -> None:
        """Update the search pattern and highlight matches in the editor."""

        normalized = pattern or ""
        needs_rebuild = (
            restart
            or self._document_dirty
            or normalized != self._pattern
        )
        self._pattern = normalized
        if not normalized:
            self.clear()
            return

        if needs_rebuild:
            self._rebuild_matches()

        if not self._matches:
            self._current_index = -1
            self._apply_highlight()
            self.matchChanged.emit(-1, 0, -1, -1)
            return

        if restart or self._current_index == -1:
            self._current_index = self._closest_match_index()
        else:
            self._current_index = min(self._current_index, len(self._matches) - 1)

        self._select_current_match()
        self.patternChanged.emit(self._pattern)

    def find_next(self) -> bool:
        """Advance to the next match, wrapping around if needed."""

        if not self._matches:
            if self._pattern:
                self.set_pattern(self._pattern, restart=False)
            return False

        next_index = (self._current_index + 1) % len(self._matches)
        if next_index == self._current_index and len(self._matches) == 1:
            self._select_current_match()
            return True

        self._current_index = next_index
        self._select_current_match()
        return True

    def find_previous(self) -> bool:
        """Move to the previous match, wrapping around if needed."""

        if not self._matches:
            if self._pattern:
                self.set_pattern(self._pattern, restart=False)
            return False

        previous_index = (self._current_index - 1) % len(self._matches)
        if previous_index == self._current_index and len(self._matches) == 1:
            self._select_current_match()
            return True

        self._current_index = previous_index
        self._select_current_match()
        return True

    def _closest_match_index(self) -> int:
        cursor = self._editor.textCursor()
        current_pos = cursor.selectionStart()
        for idx, match in enumerate(self._matches):
            if match.start >= current_pos:
                return idx
        return 0

    def _select_current_match(self) -> None:
        if not self._matches:
            self.matchChanged.emit(-1, 0, -1, -1)
            return

        match = self._matches[self._current_index]
        cursor = QtGui.QTextCursor(self._document)
        cursor.setPosition(match.start)
        cursor.setPosition(match.end, QtGui.QTextCursor.MoveMode.KeepAnchor)
        self._editor.setTextCursor(cursor)
        self._editor.centerCursor()
        self._apply_highlight()
        self.matchChanged.emit(
            self._current_index,
            len(self._matches),
            match.start,
            match.end,
        )

    def _apply_highlight(self) -> None:
        selections: list[QtWidgets.QTextEdit.ExtraSelection] = []
        for idx, match in enumerate(self._matches):
            cursor = QtGui.QTextCursor(self._document)
            cursor.setPosition(match.start)
            cursor.setPosition(match.end, QtGui.QTextCursor.MoveMode.KeepAnchor)
            selection = QtWidgets.QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setBackground(
                self._current_match_brush
                if idx == self._current_index
                else self._highlight_brush
            )
            selections.append(selection)
        self._editor.setExtraSelections(selections)

    def _on_contents_change(self, _position: int, _removed: int, _added: int) -> None:
        self._document_dirty = True

    def _rebuild_matches(self) -> None:
        self._document_dirty = False
        self._matches.clear()
        self._current_index = -1

        cursor = QtGui.QTextCursor(self._document)
        cursor.beginEditBlock()
        cursor.setPosition(0)
        cursor.endEditBlock()

        flags = QtGui.QTextDocument.FindFlag(0)
        if self._case_sensitive:
            flags |= QtGui.QTextDocument.FindFlag.FindCaseSensitively

        pos_cursor = QtGui.QTextCursor(self._document)
        pos_cursor.setPosition(0)
        while True:
            found = self._document.find(self._pattern, pos_cursor, flags)
            if found.isNull():
                break
            start = found.selectionStart()
            end = found.selectionEnd()
            self._matches.append(_Match(start=start, end=end))
            pos_cursor.setPosition(end)

        self._apply_highlight()
