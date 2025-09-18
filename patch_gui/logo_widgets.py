"""Qt widgets that render the application logos procedurally.

This module provides lightweight logo components that can be embedded in the
GUI without relying on external binary assets. Both widgets use QPainter to
produce stylised graphics so that the project can ship without raster images.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

__all__ = ["LogoWidget", "WordmarkWidget", "create_logo_pixmap"]


if TYPE_CHECKING:
    # ``PySide6`` does not ship typing-friendly base classes, so mypy sees them
    # as ``Any``. Defining the class in the ``TYPE_CHECKING`` branch gives the
    # type checker something concrete to work with, while the assignment keeps
    # the runtime behaviour identical.

    class _QWidgetBase(QtWidgets.QWidget):
        """Concrete ``QWidget`` subclass with a stable static type for mypy."""

else:
    _QWidgetBase = QtWidgets.QWidget


def _draw_logo(painter: QtGui.QPainter, target: QtCore.QRectF) -> None:
    """Draw the square Patch GUI logo inside ``target``."""

    if target.width() <= 0 or target.height() <= 0:
        return

    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

    inset = min(target.width(), target.height()) * 0.04
    rect = target.adjusted(inset, inset, -inset, -inset)
    radius = min(rect.width(), rect.height()) * 0.24

    shadow = rect.translated(rect.width() * 0.04, rect.height() * 0.05)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QColor(0, 0, 0, 55))
    painter.drawRoundedRect(shadow, radius * 1.05, radius * 1.05)

    border_pen = QtGui.QPen(
        QtGui.QColor("#08172c"), max(rect.width(), rect.height()) * 0.055
    )
    border_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(border_pen)

    background = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
    background.setColorAt(0.0, QtGui.QColor("#0b1d36"))
    background.setColorAt(1.0, QtGui.QColor("#1e4074"))
    painter.setBrush(QtGui.QBrush(background))
    painter.drawRoundedRect(rect, radius, radius)

    sheet = rect.adjusted(
        rect.width() * 0.16,
        rect.height() * 0.16,
        -rect.width() * 0.16,
        -rect.height() * 0.16,
    )
    sheet_gradient = QtGui.QLinearGradient(sheet.topLeft(), sheet.bottomRight())
    sheet_gradient.setColorAt(0.0, QtGui.QColor("#f9fcff"))
    sheet_gradient.setColorAt(1.0, QtGui.QColor("#e0e8ff"))
    sheet_pen = QtGui.QPen(
        QtGui.QColor("#1b365f"), max(rect.width(), rect.height()) * 0.03
    )
    sheet_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(sheet_pen)
    painter.setBrush(QtGui.QBrush(sheet_gradient))
    painter.drawRoundedRect(sheet, radius * 0.7, radius * 0.7)

    accent_rect = QtCore.QRectF(
        sheet.left() + sheet.width() * 0.05,
        sheet.top() + sheet.height() * 0.12,
        sheet.width() * 0.08,
        sheet.height() * 0.76,
    )
    accent_gradient = QtGui.QLinearGradient(
        accent_rect.topLeft(), accent_rect.bottomRight()
    )
    accent_gradient.setColorAt(0.0, QtGui.QColor("#4aa8ff"))
    accent_gradient.setColorAt(1.0, QtGui.QColor("#2465dd"))
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QBrush(accent_gradient))
    painter.drawRoundedRect(
        accent_rect, accent_rect.width() / 2.2, accent_rect.width() / 2.2
    )

    line_height = sheet.height() / 5.2
    vertical_margin = (sheet.height() - 3 * line_height) / 4
    start_x = accent_rect.right() + sheet.width() * 0.06
    end_x = sheet.right() - sheet.width() * 0.1
    accents = [
        ("plus", QtGui.QColor("#3ddc97")),
        ("minus", QtGui.QColor("#ff6b6b")),
        ("review", QtGui.QColor("#4aa8ff")),
    ]

    y = sheet.top() + vertical_margin
    for kind, accent in accents:
        line_rect = QtCore.QRectF(start_x, y, end_x - start_x, line_height)
        highlight = QtGui.QColor(accent)
        highlight.setAlpha(60)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(highlight))
        painter.drawRoundedRect(line_rect, line_height / 2.3, line_height / 2.3)

        pen = QtGui.QPen(
            accent.darker(110),
            line_height * 0.45,
            QtCore.Qt.PenStyle.SolidLine,
            QtCore.Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        centre_y = line_rect.center().y()
        if kind == "review":
            dots = 4
            dot_spacing = line_rect.width() / (dots + 1)
            for idx in range(dots):
                painter.drawPoint(
                    QtCore.QPointF(line_rect.left() + dot_spacing * (idx + 1), centre_y)
                )
        else:
            painter.drawLine(
                QtCore.QPointF(line_rect.left() + line_height * 0.55, centre_y),
                QtCore.QPointF(line_rect.right() - line_height * 0.55, centre_y),
            )
            if kind == "plus":
                mid_x = (line_rect.left() + line_rect.right()) / 2
                painter.drawLine(
                    QtCore.QPointF(mid_x, centre_y - line_height * 0.6),
                    QtCore.QPointF(mid_x, centre_y + line_height * 0.6),
                )
        y += line_height + vertical_margin

    fold = QtCore.QRectF(
        sheet.right() - sheet.width() * 0.28,
        sheet.top() + sheet.height() * 0.05,
        sheet.width() * 0.28,
        sheet.height() * 0.28,
    )
    fold_path = QtGui.QPainterPath()
    fold_path.moveTo(fold.topLeft())
    fold_path.lineTo(fold.topRight())
    fold_path.lineTo(fold.bottomRight())
    fold_path.closeSubpath()
    fold_gradient = QtGui.QLinearGradient(fold.topLeft(), fold.bottomRight())
    fold_gradient.setColorAt(0.0, QtGui.QColor("#d1ddff"))
    fold_gradient.setColorAt(1.0, QtGui.QColor("#a8bbff"))
    painter.setBrush(QtGui.QBrush(fold_gradient))
    painter.setPen(
        QtGui.QPen(QtGui.QColor("#1b365f"), max(rect.width(), rect.height()) * 0.022)
    )
    painter.drawPath(fold_path)

    painter.restore()


def create_logo_pixmap(size: int = 128) -> QtGui.QPixmap:
    """Return a :class:`~PySide6.QtGui.QPixmap` containing the logo artwork."""

    if size <= 0:
        raise ValueError("size must be positive")
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    _draw_logo(painter, QtCore.QRectF(0, 0, size, size))
    painter.end()
    return pixmap


class LogoWidget(_QWidgetBase):
    """Widget that paints the square logo procedurally."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setMinimumSize(88, 88)

    def sizeHint(self) -> QtCore.QSize:  # pragma: no cover - trivial Qt override
        return QtCore.QSize(96, 96)

    def minimumSizeHint(self) -> QtCore.QSize:  # pragma: no cover - trivial Qt override
        return QtCore.QSize(88, 88)

    def paintEvent(
        self, event: QtGui.QPaintEvent
    ) -> None:  # pragma: no cover - UI feedback
        painter = QtGui.QPainter(self)
        rect = QtCore.QRectF(self.rect()).adjusted(4.0, 4.0, -4.0, -4.0)
        _draw_logo(painter, rect)
        painter.end()


class WordmarkWidget(_QWidgetBase):
    """Widget that draws a wordmark banner for the application."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setMinimumHeight(92)

    def sizeHint(self) -> QtCore.QSize:  # pragma: no cover - trivial Qt override
        return QtCore.QSize(320, 110)

    def minimumSizeHint(self) -> QtCore.QSize:  # pragma: no cover - trivial Qt override
        return QtCore.QSize(240, 92)

    def paintEvent(
        self, event: QtGui.QPaintEvent
    ) -> None:  # pragma: no cover - UI feedback
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        radius = rect.height() * 0.32

        background = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
        background.setColorAt(0.0, QtGui.QColor("#0c1b2f"))
        background.setColorAt(1.0, QtGui.QColor("#17345b"))
        border = QtGui.QPen(QtGui.QColor("#071224"), 2.4)
        border.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setBrush(QtGui.QBrush(background))
        painter.setPen(border)
        painter.drawRoundedRect(rect, radius, radius)

        accent_rect = QtCore.QRectF(
            rect.left() + rect.width() * 0.045,
            rect.top() + rect.height() * 0.18,
            rect.width() * 0.022,
            rect.height() * 0.64,
        )
        accent_gradient = QtGui.QLinearGradient(
            accent_rect.topLeft(), accent_rect.bottomRight()
        )
        accent_gradient.setColorAt(0.0, QtGui.QColor("#52b2ff"))
        accent_gradient.setColorAt(1.0, QtGui.QColor("#2f7df2"))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(accent_gradient))
        painter.drawRoundedRect(accent_rect, accent_rect.width(), accent_rect.width())

        highlight_rect = QtCore.QRectF(
            rect.left() + rect.width() * 0.12,
            rect.bottom() - rect.height() * 0.3,
            rect.width() * 0.3,
            rect.height() * 0.12,
        )
        highlight_gradient = QtGui.QLinearGradient(
            highlight_rect.topLeft(), highlight_rect.topRight()
        )
        highlight_gradient.setColorAt(0.0, QtGui.QColor("#4ac6ff"))
        highlight_gradient.setColorAt(1.0, QtGui.QColor("#3ddc97"))
        painter.setBrush(QtGui.QBrush(highlight_gradient))
        painter.drawRoundedRect(
            highlight_rect, highlight_rect.height() / 2, highlight_rect.height() / 2
        )

        title_rect = QtCore.QRectF(
            rect.left() + rect.width() * 0.12,
            rect.top() + rect.height() * 0.1,
            rect.width() * 0.8,
            rect.height() * 0.45,
        )
        title_font = QtGui.QFont(self.font())
        title_font.setBold(True)
        title_font.setPointSizeF(rect.height() * 0.34)
        title_font.setLetterSpacing(QtGui.QFont.SpacingType.PercentageSpacing, 103)
        painter.setFont(title_font)
        painter.setPen(QtGui.QColor("#f0f6ff"))
        painter.drawText(
            title_rect,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            "Patch GUI",
        )

        subtitle_rect = QtCore.QRectF(
            rect.left() + rect.width() * 0.12,
            rect.bottom() - rect.height() * 0.34,
            rect.width() * 0.78,
            rect.height() * 0.28,
        )
        subtitle_font = QtGui.QFont(self.font())
        subtitle_font.setPointSizeF(rect.height() * 0.2)
        subtitle_font.setLetterSpacing(QtGui.QFont.SpacingType.PercentageSpacing, 103)
        painter.setFont(subtitle_font)
        painter.setPen(QtGui.QColor("#a8c2ff"))
        painter.drawText(
            subtitle_rect,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            "Diff Applier",
        )

        painter.end()
