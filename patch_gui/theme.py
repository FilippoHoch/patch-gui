"""Application-wide theming helpers."""

from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

from .platform import running_under_wsl


_ACCENT_COLOR = QtGui.QColor("#3d7dca")
_ACCENT_DARK = QtGui.QColor("#2f5a94")
_BACKGROUND_DARK = QtGui.QColor("#1f1f28")
_BACKGROUND_ELEVATED = QtGui.QColor("#27293a")
_BACKGROUND_INPUT = QtGui.QColor("#252535")
_BORDER_COLOR = QtGui.QColor("#3d3d52")
_BORDER_FOCUS = QtGui.QColor("#4d8fe3")
_TEXT_PRIMARY = QtGui.QColor("#f2f2f5")
_TEXT_SECONDARY = QtGui.QColor("#c7cad4")
_TEXT_DISABLED = QtGui.QColor("#7a7d8a")
_SELECTION_BG = _ACCENT_COLOR
_SELECTION_FG = QtGui.QColor("#ffffff")


def _build_palette() -> QtGui.QPalette:
    palette = QtGui.QPalette()

    palette.setColor(QtGui.QPalette.ColorRole.Window, _BACKGROUND_DARK)
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, _TEXT_PRIMARY)
    palette.setColor(QtGui.QPalette.ColorRole.Base, _BACKGROUND_INPUT)
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, _BACKGROUND_ELEVATED)
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, _BACKGROUND_ELEVATED)
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, _TEXT_PRIMARY)
    palette.setColor(QtGui.QPalette.ColorRole.Text, _TEXT_PRIMARY)
    palette.setColor(QtGui.QPalette.ColorRole.Button, _BACKGROUND_ELEVATED)
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, _TEXT_PRIMARY)
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtCore.Qt.GlobalColor.red)
    palette.setColor(QtGui.QPalette.ColorRole.Link, _ACCENT_COLOR)
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, _SELECTION_BG)
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, _SELECTION_FG)

    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.Text,
        _TEXT_DISABLED,
    )
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.ButtonText,
        _TEXT_DISABLED,
    )
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.WindowText,
        _TEXT_DISABLED,
    )

    return palette


def _resolve_default_font(app: QtWidgets.QApplication) -> QtGui.QFont:
    general_font = QtGui.QFontDatabase.systemFont(
        QtGui.QFontDatabase.SystemFont.GeneralFont
    )
    if general_font.family():
        font = QtGui.QFont(general_font)
    else:
        font = QtGui.QFont(app.font())

    if font.pointSize() <= 0:
        font.setPointSize(10)
    font.setHintingPreference(QtGui.QFont.HintingPreference.PreferFullHinting)
    font.setStyleHint(
        QtGui.QFont.StyleHint.SansSerif, QtGui.QFont.StyleStrategy.PreferAntialias
    )
    return font


def _build_stylesheet() -> str:
    return (
        "QToolTip {"
        "    color: %s;"
        "    background-color: %s;"
        "    border: 1px solid %s;"
        "    border-radius: 6px;"
        "    padding: 6px;"
        "}" % (_TEXT_PRIMARY.name(), _BACKGROUND_ELEVATED.name(), _BORDER_COLOR.name())
        + "\n"
        "QMainWindow {"
        "    background-color: %s;"
        "    color: %s;"
        "}" % (_BACKGROUND_DARK.name(), _TEXT_PRIMARY.name()) + "\n"
        "QWidget {"
        "    color: %s;"
        "    background-color: %s;"
        "    selection-background-color: %s;"
        "    selection-color: %s;"
        "}"
        % (
            _TEXT_PRIMARY.name(),
            _BACKGROUND_DARK.name(),
            _SELECTION_BG.name(),
            _SELECTION_FG.name(),
        )
        + "\n"
        "QLabel { color: %s; }" % _TEXT_PRIMARY.name() + "\n"
        "QPushButton {"
        "    background-color: %s;"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    padding: 6px 14px;"
        "    color: %s;"
        "}"
        % (
            _BACKGROUND_ELEVATED.name(),
            _BORDER_COLOR.name(),
            _TEXT_PRIMARY.name(),
        )
        + "\n"
        "QPushButton:hover {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}" % (_ACCENT_COLOR.lighter(125).name(), _ACCENT_COLOR.name()) + "\n"
        "QPushButton:pressed {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}" % (_ACCENT_DARK.name(), _ACCENT_DARK.darker(115).name()) + "\n"
        "QPushButton:disabled {"
        "    color: %s;"
        "    background-color: %s;"
        "    border-color: %s;"
        "}"
        % (
            _TEXT_DISABLED.name(),
            _BACKGROUND_ELEVATED.darker(110).name(),
            _BACKGROUND_ELEVATED.darker(125).name(),
        )
        + "\n"
        "QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
        "    background-color: %s;"
        "    border: 1px solid %s;"
        "    border-radius: 6px;"
        "    padding: 6px 8px;"
        "    color: %s;"
        "}"
        % (
            _BACKGROUND_INPUT.name(),
            _BORDER_COLOR.name(),
            _TEXT_PRIMARY.name(),
        )
        + "\n"
        "QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus,"
        " QSpinBox:focus, QDoubleSpinBox:focus {"
        "    border: 1px solid %s;"
        "    background-color: %s;"
        "}" % (_BORDER_FOCUS.name(), _BACKGROUND_ELEVATED.name()) + "\n"
        "QTreeWidget, QTreeView, QListWidget, QListView {"
        "    background-color: %s;"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    alternate-background-color: %s;"
        "}"
        % (
            _BACKGROUND_ELEVATED.name(),
            _BORDER_COLOR.name(),
            _BACKGROUND_INPUT.name(),
        )
        + "\n"
        "QHeaderView::section {"
        "    background-color: %s;"
        "    color: %s;"
        "    padding: 6px;"
        "    border: none;"
        "    border-right: 1px solid %s;"
        "}"
        % (
            _BACKGROUND_INPUT.name(),
            _TEXT_SECONDARY.name(),
            _BORDER_COLOR.name(),
        )
        + "\n"
        "QSplitter::handle {"
        "    background: %s;"
        "    border: 1px solid %s;"
        "    margin: 4px;"
        "    border-radius: 4px;"
        "}" % (_BACKGROUND_INPUT.name(), _BORDER_COLOR.name()) + "\n"
        "QSplitter::handle:hover {"
        "    background: %s;"
        "    border-color: %s;"
        "}" % (_ACCENT_COLOR.name(), _ACCENT_COLOR.darker(120).name()) + "\n"
        "QSplitter::handle:pressed {"
        "    background: %s;"
        "}" % (_ACCENT_DARK.name(),) + "\n"
        "QProgressBar {"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    background-color: %s;"
        "    color: %s;"
        "    text-align: center;"
        "    padding: 2px;"
        "}"
        % (
            _BORDER_COLOR.name(),
            _BACKGROUND_ELEVATED.name(),
            _TEXT_PRIMARY.name(),
        )
        + "\n"
        "QProgressBar::chunk {"
        "    background-color: %s;"
        "    border-radius: 6px;"
        "}" % (_ACCENT_COLOR.name(),) + "\n"
        "QScrollBar:vertical {"
        "    background: %s;"
        "    width: 14px;"
        "    margin: 4px 2px 4px 2px;"
        "    border-radius: 6px;"
        "}" % (_BACKGROUND_ELEVATED.name(),) + "\n"
        "QScrollBar::handle:vertical {"
        "    background: %s;"
        "    min-height: 24px;"
        "    border-radius: 6px;"
        "}" % (_ACCENT_COLOR.name(),) + "\n"
        "QScrollBar::handle:vertical:hover {"
        "    background: %s;"
        "}" % (_ACCENT_DARK.name(),) + "\n"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
        "    background: none;"
        "}" + "\n"
        "QStatusBar {"
        "    background: %s;"
        "    color: %s;"
        "}" % (_BACKGROUND_ELEVATED.name(), _TEXT_PRIMARY.name()) + "\n"
        "QGroupBox {"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    margin-top: 16px;"
        "    padding: 10px;"
        "}" % (_BORDER_COLOR.name(),) + "\n"
        "QGroupBox::title {"
        "    subcontrol-origin: margin;"
        "    subcontrol-position: top left;"
        "    padding: 0 6px;"
        "    color: %s;"
        "}" % (_TEXT_SECONDARY.name(),)
    )


def apply_modern_theme(app: QtWidgets.QApplication) -> None:
    """Apply a modern dark theme to ``app`` while remaining WSL-friendly."""

    if app is None:
        return

    # ``Fusion`` provides a predictable baseline but we allow power users to
    # override it via the standard ``QT_STYLE_OVERRIDE`` variable. Keeping the
    # existing style is especially important for WSL sessions where users may
    # prefer the Windows host look & feel.
    style_override = os.getenv("QT_STYLE_OVERRIDE")
    if style_override:
        app.setStyle(style_override)
    elif not running_under_wsl():
        available_styles = {
            name.lower(): name for name in QtWidgets.QStyleFactory.keys()
        }
        fusion = available_styles.get("fusion")
        if fusion:
            app.setStyle(fusion)

    app.setPalette(_build_palette())
    app.setFont(_resolve_default_font(app))
    app.setStyleSheet(_build_stylesheet())
