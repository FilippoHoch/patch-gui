"""Qt widgets that render the application logos procedurally.

This module provides lightweight logo components that can be embedded in the
GUI without relying on external binary assets. Both widgets use QPainter to
produce stylised graphics so that the project can ship without raster images.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

__all__ = ["LogoWidget", "WordmarkWidget", "create_logo_pixmap"]


def _draw_logo(painter: QtGui.QPainter, target: QtCore.QRectF) -> None:
    """Draw the square Patch GUI logo inside ``target``."""

    if target.width() <= 0 or target.height() <= 0:
        return

    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

    radius = min(target.width(), target.height()) * 0.22
    border_pen = QtGui.QPen(QtGui.QColor("#061533"), max(target.width(), target.height()) * 0.045)
    border_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(border_pen)

    background = QtGui.QLinearGradient(target.topLeft(), target.bottomRight())
    background.setColorAt(0.0, QtGui.QColor("#102a43"))
    background.setColorAt(1.0, QtGui.QColor("#1f4b99"))
    painter.setBrush(QtGui.QBrush(background))
    painter.drawRoundedRect(target, radius, radius)

    sheet = target.adjusted(
        target.width() * 0.17,
        target.height() * 0.17,
        -target.width() * 0.17,
        -target.height() * 0.17,
    )
    sheet_gradient = QtGui.QLinearGradient(sheet.topLeft(), sheet.bottomRight())
    sheet_gradient.setColorAt(0.0, QtGui.QColor("#f5fbff"))
    sheet_gradient.setColorAt(1.0, QtGui.QColor("#e3f2fd"))
    sheet_pen = QtGui.QPen(QtGui.QColor("#0f3057"), max(target.width(), target.height()) * 0.03)
    sheet_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(sheet_pen)
    painter.setBrush(QtGui.QBrush(sheet_gradient))
    painter.drawRoundedRect(sheet, radius * 0.7, radius * 0.7)

    line_height = sheet.height() / 5.1
    vertical_margin = (sheet.height() - 3 * line_height) / 4
    horizontal_margin = sheet.width() * 0.12
    accents = [
        ("plus", QtGui.QColor("#2ecc71")),
        ("minus", QtGui.QColor("#e74c3c")),
        ("dots", QtGui.QColor("#2e86de")),
    ]

    y = sheet.top() + vertical_margin
    for kind, accent in accents:
        line_rect = QtCore.QRectF(
            sheet.left() + horizontal_margin,
            y,
            sheet.width() - 2 * horizontal_margin,
            line_height,
        )
        highlight = QtGui.QColor(accent)
        highlight.setAlpha(60)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(highlight))
        painter.drawRoundedRect(line_rect, line_height / 2.4, line_height / 2.4)

        pen = QtGui.QPen(
            accent,
            line_height * 0.35,
            QtCore.Qt.PenStyle.SolidLine,
            QtCore.Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        centre_y = line_rect.center().y()
        start_x = line_rect.left() + line_height * 0.6
        end_x = line_rect.right() - line_height * 0.6
        if kind == "dots":
            dots = 5
            if end_x > start_x:
                dot_spacing = (end_x - start_x) / (dots - 1)
            else:
                dot_spacing = 0
            for idx in range(dots):
                painter.drawPoint(QtCore.QPointF(start_x + dot_spacing * idx, centre_y))
        else:
            painter.drawLine(start_x, centre_y, end_x, centre_y)
            if kind == "plus":
                painter.drawLine(
                    (start_x + end_x) / 2,
                    centre_y - line_height * 0.55,
                    (start_x + end_x) / 2,
                    centre_y + line_height * 0.55,
                )
        y += line_height + vertical_margin

    fold = QtCore.QRectF(
        sheet.right() - sheet.width() * 0.28,
        sheet.top() + sheet.height() * 0.07,
        sheet.width() * 0.28,
        sheet.height() * 0.28,
    )
    fold_path = QtGui.QPainterPath()
    fold_path.moveTo(fold.topLeft())
    fold_path.lineTo(fold.topRight())
    fold_path.lineTo(fold.bottomRight())
    fold_path.closeSubpath()
    fold_gradient = QtGui.QLinearGradient(fold.topLeft(), fold.bottomRight())
    fold_gradient.setColorAt(0.0, QtGui.QColor("#bbdefb"))
    fold_gradient.setColorAt(1.0, QtGui.QColor("#90caf9"))
    painter.setBrush(QtGui.QBrush(fold_gradient))
    painter.setPen(QtGui.QPen(QtGui.QColor("#0f3057"), max(target.width(), target.height()) * 0.02))
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


class LogoWidget(QtWidgets.QWidget):
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

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # pragma: no cover - UI feedback
        painter = QtGui.QPainter(self)
        rect = QtCore.QRectF(self.rect()).adjusted(4.0, 4.0, -4.0, -4.0)
        _draw_logo(painter, rect)
        painter.end()


class WordmarkWidget(QtWidgets.QWidget):
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

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # pragma: no cover - UI feedback
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        radius = rect.height() * 0.32

        background = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
        background.setColorAt(0.0, QtGui.QColor("#0f2027"))
        background.setColorAt(1.0, QtGui.QColor("#203a43"))
        painter.setBrush(QtGui.QBrush(background))
        painter.setPen(QtGui.QPen(QtGui.QColor("#071018"), 2.2))
        painter.drawRoundedRect(rect, radius, radius)

        accent_rect = QtCore.QRectF(
            rect.left() + rect.width() * 0.05,
            rect.top() + rect.height() * 0.2,
            rect.width() * 0.02,
            rect.height() * 0.6,
        )
        accent_gradient = QtGui.QLinearGradient(accent_rect.topLeft(), accent_rect.bottomRight())
        accent_gradient.setColorAt(0.0, QtGui.QColor("#26c6da"))
        accent_gradient.setColorAt(1.0, QtGui.QColor("#00acc1"))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(accent_gradient))
        painter.drawRoundedRect(accent_rect, accent_rect.width(), accent_rect.width())

        highlight_rect = QtCore.QRectF(
            rect.left() + rect.width() * 0.13,
            rect.bottom() - rect.height() * 0.3,
            rect.width() * 0.28,
            rect.height() * 0.11,
        )
        highlight_gradient = QtGui.QLinearGradient(highlight_rect.topLeft(), highlight_rect.topRight())
        highlight_gradient.setColorAt(0.0, QtGui.QColor("#26c6da"))
        highlight_gradient.setColorAt(1.0, QtGui.QColor("#1de9b6"))
        painter.setBrush(QtGui.QBrush(highlight_gradient))
        painter.drawRoundedRect(highlight_rect, highlight_rect.height() / 2, highlight_rect.height() / 2)

        title_rect = QtCore.QRectF(
            rect.left() + rect.width() * 0.12,
            rect.top() + rect.height() * 0.08,
            rect.width() * 0.83,
            rect.height() * 0.45,
        )
        title_font = QtGui.QFont(self.font())
        title_font.setBold(True)
        title_font.setPointSizeF(rect.height() * 0.36)
        title_font.setLetterSpacing(QtGui.QFont.SpacingType.PercentageSpacing, 104)
        painter.setFont(title_font)
        painter.setPen(QtGui.QColor("#e0f7fa"))
        painter.drawText(
            title_rect,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            "Patch GUI",
        )

        subtitle_rect = QtCore.QRectF(
            rect.left() + rect.width() * 0.12,
            rect.bottom() - rect.height() * 0.34,
            rect.width() * 0.83,
            rect.height() * 0.28,
        )
        subtitle_font = QtGui.QFont(self.font())
        subtitle_font.setPointSizeF(rect.height() * 0.2)
        subtitle_font.setLetterSpacing(QtGui.QFont.SpacingType.PercentageSpacing, 104)
        painter.setFont(subtitle_font)
        painter.setPen(QtGui.QColor("#b3e5fc"))
        painter.drawText(
            subtitle_rect,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            "Diff Applier",
        )

        painter.end()
