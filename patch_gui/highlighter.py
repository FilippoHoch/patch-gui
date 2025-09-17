"""Diff syntax highlighter for the Patch GUI application."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtGui

if TYPE_CHECKING:
    # ``PySide6`` exposes ``QSyntaxHighlighter`` as ``Any`` to type checkers.
    # Providing a concrete subclass in the ``TYPE_CHECKING`` branch gives mypy
    # a stable type to work with while keeping the runtime behaviour intact.

    class _QSyntaxHighlighter(QtGui.QSyntaxHighlighter):
        """Concrete ``QSyntaxHighlighter`` subclass for static analysis."""

else:
    _QSyntaxHighlighter = QtGui.QSyntaxHighlighter


class DiffHighlighter(_QSyntaxHighlighter):
    """Highlight diff-like text blocks."""

    def __init__(self, document: QtGui.QTextDocument) -> None:
        super().__init__(document)
        self._addition_format = QtGui.QTextCharFormat()
        self._addition_format.setBackground(QtGui.QColor("#e6ffed"))
        self._addition_format.setForeground(QtGui.QColor("#033a16"))

        self._removal_format = QtGui.QTextCharFormat()
        self._removal_format.setBackground(QtGui.QColor("#ffeef0"))
        self._removal_format.setForeground(QtGui.QColor("#86181d"))

        self._context_format = QtGui.QTextCharFormat()
        self._context_format.setBackground(QtGui.QColor("#f6f8fa"))
        self._context_format.setForeground(QtGui.QColor("#24292e"))

        self._header_format = QtGui.QTextCharFormat()
        self._header_format.setBackground(QtGui.QColor("#dbe9ff"))
        self._header_format.setForeground(QtGui.QColor("#032f62"))
        self._header_format.setFontWeight(QtGui.QFont.Weight.Bold)

        self._meta_format = QtGui.QTextCharFormat()
        self._meta_format.setForeground(QtGui.QColor("#6a737d"))
        self._meta_format.setFontItalic(True)

    def highlightBlock(self, text: str) -> None:  # noqa: N802 (Qt signature)
        if not text:
            return

        first = text[0]
        fmt: QtGui.QTextCharFormat | None

        if (
            text.startswith("@@")
            or text.startswith("diff ")
            or text.startswith("index ")
        ):
            fmt = self._header_format
        elif text.startswith("---") or text.startswith("+++"):
            fmt = self._header_format
        elif first == "+":
            fmt = self._addition_format
        elif first == "-":
            fmt = self._removal_format
        elif first == " " or first == "\t":
            fmt = self._context_format
        elif text.startswith("\\ No newline"):
            fmt = self._meta_format
        else:
            fmt = None

        if fmt is not None:
            self.setFormat(0, len(text), fmt)
