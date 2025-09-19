"""Helper types that provide stable Qt base classes for type-checking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFrame, QWidget

__all__ = ["QObjectBase", "QWidgetBase", "QFrameBase"]


if TYPE_CHECKING:
    class QObjectBase(QObject):
        """Concrete ``QObject`` subclass recognised by static type checkers."""

    class QWidgetBase(QWidget):
        """Concrete ``QWidget`` subclass recognised by static type checkers."""

    class QFrameBase(QFrame):
        """Concrete ``QFrame`` subclass recognised by static type checkers."""

else:
    QObjectBase = QObject
    QWidgetBase = QWidget
    QFrameBase = QFrame

