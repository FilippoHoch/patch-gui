"""Diff syntax highlighter for the Patch GUI application."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtGui

from .theme import PaletteColors, theme_manager

if TYPE_CHECKING:
    # ``PySide6`` exposes ``QSyntaxHighlighter`` as ``Any`` to type checkers.
    # Providing a lightweight stub in the ``TYPE_CHECKING`` branch gives mypy a
    # stable type to work with while keeping the runtime behaviour intact.

    class _QSyntaxHighlighter(object):
        """Stub ``QSyntaxHighlighter`` for static analysis."""

        def __init__(self, document: QtGui.QTextDocument) -> None: ...

        def setFormat(
            self, start: int, count: int, format: QtGui.QTextCharFormat
        ) -> None: ...

else:
    _QSyntaxHighlighter = QtGui.QSyntaxHighlighter


class DiffHighlighter(_QSyntaxHighlighter):
    """Highlight diff-like text blocks."""

    def __init__(self, document: QtGui.QTextDocument) -> None:
        super().__init__(document)
        self._addition_format = QtGui.QTextCharFormat()
        self._removal_format = QtGui.QTextCharFormat()
        self._context_format = QtGui.QTextCharFormat()
        self._header_format = QtGui.QTextCharFormat()
        self._header_format.setFontWeight(QtGui.QFont.Weight.Bold)

        self._meta_format = QtGui.QTextCharFormat()
        self._theme_manager = theme_manager
        self._apply_palette(self._theme_manager.colors)
        self._theme_manager.paletteChanged.connect(self._on_theme_changed)

    def _apply_palette(self, colors: PaletteColors) -> None:
        self._addition_format.setBackground(colors.diff_add_bg)
        self._addition_format.setForeground(colors.diff_add_fg)

        self._removal_format.setBackground(colors.diff_remove_bg)
        self._removal_format.setForeground(colors.diff_remove_fg)

        self._context_format.setBackground(colors.diff_context_bg)
        self._context_format.setForeground(colors.diff_context_fg)

        self._header_format.setBackground(colors.diff_header_bg)
        self._header_format.setForeground(colors.diff_header_fg)

        self._meta_format.setForeground(colors.diff_meta_fg)

    def _on_theme_changed(self, _: str) -> None:
        self._apply_palette(self._theme_manager.colors)
        self.rehighlight()
        self._meta_format.setFontItalic(True)

    def highlightBlock(self, text: str) -> None:  # noqa: N802 (Qt signature)
        if not text:
            return

        marker_text = _extract_marker_text(text)
        first = marker_text[0] if marker_text else text[0]
        fmt: QtGui.QTextCharFormat | None

        if (
            text.startswith("@@")
            or text.startswith("diff ")
            or text.startswith("index ")
        ):
            fmt = self._header_format
        elif text.startswith("---") or text.startswith("+++"):
            fmt = self._header_format
        elif marker_text.startswith("\\ No newline"):
            fmt = self._meta_format
        elif first == "+":
            fmt = self._addition_format
        elif first == "-":
            fmt = self._removal_format
        elif first == " " or first == "\t":
            fmt = self._context_format
        else:
            fmt = None

        if fmt is not None:
            self.setFormat(0, len(text), fmt)


def _extract_marker_text(text: str) -> str:
    """Return the portion of ``text`` containing the diff marker."""

    if "│" in text:
        parts = text.split("│", 2)
        if len(parts) == 3:
            candidate = parts[2]
            stripped_candidate = candidate.lstrip()
            if stripped_candidate:
                return stripped_candidate
            if candidate:
                return candidate
    stripped = text.lstrip()
    if stripped:
        return stripped
    return text
