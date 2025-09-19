"""Diff syntax highlighter for the Patch GUI application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6 import QtGui

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


@dataclass(frozen=True, slots=True)
class DiffHighlightPalette:
    """Colours used by :class:`DiffHighlighter`."""

    addition_bg: QtGui.QColor
    addition_fg: QtGui.QColor
    removal_bg: QtGui.QColor
    removal_fg: QtGui.QColor
    context_bg: QtGui.QColor
    context_fg: QtGui.QColor
    header_bg: QtGui.QColor
    header_fg: QtGui.QColor
    meta_fg: QtGui.QColor


def _to_color(value: QtGui.QColor | str) -> QtGui.QColor:
    return QtGui.QColor(value)


DEFAULT_DIFF_PALETTE = DiffHighlightPalette(
    addition_bg=_to_color("#e6ffed"),
    addition_fg=_to_color("#033a16"),
    removal_bg=_to_color("#ffeef0"),
    removal_fg=_to_color("#86181d"),
    context_bg=_to_color("#f6f8fa"),
    context_fg=_to_color("#24292e"),
    header_bg=_to_color("#dbe9ff"),
    header_fg=_to_color("#032f62"),
    meta_fg=_to_color("#6a737d"),
)


def _blend(base: QtGui.QColor, overlay: QtGui.QColor, alpha: float) -> QtGui.QColor:
    result = QtGui.QColor()
    base = QtGui.QColor(base)
    overlay = QtGui.QColor(overlay)
    alpha = max(0.0, min(alpha, 1.0))
    for channel, setter in (
        (base.red(), result.setRed),
        (base.green(), result.setGreen),
        (base.blue(), result.setBlue),
    ):
        overlay_value = getattr(overlay, f"{setter.__name__[3:].lower()}")()
        value = round(channel * (1 - alpha) + overlay_value * alpha)
        setter(value)
    result.setAlpha(max(base.alpha(), overlay.alpha()))
    return result


def build_diff_highlight_palette(qpalette: QtGui.QPalette) -> DiffHighlightPalette:
    """Derive a theme-aware palette from ``qpalette``."""

    base = qpalette.color(QtGui.QPalette.ColorRole.Base)
    alt = qpalette.color(QtGui.QPalette.ColorRole.AlternateBase)
    text = qpalette.color(QtGui.QPalette.ColorRole.Text)
    window_text = qpalette.color(QtGui.QPalette.ColorRole.WindowText)
    highlight = qpalette.color(QtGui.QPalette.ColorRole.Highlight)
    highlighted_text = qpalette.color(QtGui.QPalette.ColorRole.HighlightedText)

    addition = QtGui.QColor("#22c55e")
    removal = QtGui.QColor("#ef4444")
    neutral = QtGui.QColor("#94a3b8")

    context_bg = _blend(base, alt, 0.35)
    header_bg = _blend(alt, highlight, 0.25)
    meta_fg = _blend(window_text, neutral, 0.55)

    return DiffHighlightPalette(
        addition_bg=_blend(base, addition, 0.22),
        addition_fg=_blend(highlighted_text, QtGui.QColor("#064e3b"), 0.35),
        removal_bg=_blend(base, removal, 0.22),
        removal_fg=_blend(highlighted_text, QtGui.QColor("#7f1d1d"), 0.35),
        context_bg=context_bg,
        context_fg=text,
        header_bg=header_bg,
        header_fg=_blend(highlighted_text, window_text, 0.4),
        meta_fg=meta_fg,
    )


class DiffHighlighter(_QSyntaxHighlighter):
    """Highlight diff-like text blocks."""

    def __init__(
        self,
        document: QtGui.QTextDocument,
        *,
        palette: DiffHighlightPalette | None = None,
    ) -> None:
        super().__init__(document)
        self._addition_format = QtGui.QTextCharFormat()
        self._removal_format = QtGui.QTextCharFormat()
        self._context_format = QtGui.QTextCharFormat()
        self._header_format = QtGui.QTextCharFormat()
        self._meta_format = QtGui.QTextCharFormat()
        self._header_format.setFontWeight(QtGui.QFont.Weight.Bold)
        self._meta_format.setFontItalic(True)
        self.set_palette(palette or DEFAULT_DIFF_PALETTE)

    def set_palette(self, palette: DiffHighlightPalette) -> None:
        """Update the highlight colours used by the highlighter."""

        self._addition_format.setBackground(palette.addition_bg)
        self._addition_format.setForeground(palette.addition_fg)

        self._removal_format.setBackground(palette.removal_bg)
        self._removal_format.setForeground(palette.removal_fg)

        self._context_format.setBackground(palette.context_bg)
        self._context_format.setForeground(palette.context_fg)

        self._header_format.setBackground(palette.header_bg)
        self._header_format.setForeground(palette.header_fg)

        self._meta_format.setForeground(palette.meta_fg)

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
