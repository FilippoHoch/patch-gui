"""Application-wide theming helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, MutableMapping, TYPE_CHECKING

from .config import Theme
from .platform import running_on_windows_native, running_under_wsl

if TYPE_CHECKING:  # pragma: no cover - hints for type checkers only
    from PySide6 import QtCore, QtGui, QtWidgets
else:  # pragma: no cover - optional dependency
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except Exception:  # pragma: no cover - bindings missing at runtime
        QtCore = QtGui = QtWidgets = None  # type: ignore[assignment]


_ICON_DIR = Path(__file__).with_name("icons")
_SPIN_UP_ICON = (_ICON_DIR / "spin_up.svg").resolve().as_posix()
_SPIN_DOWN_ICON = (_ICON_DIR / "spin_down.svg").resolve().as_posix()
_RESOURCE_DIR = Path(__file__).resolve().parent / "resources"


_BASE_TOKENS: Mapping[str, str] = {
    "accent": "#3d7dca",
    "accent_hover": "#4d8fe3",
    "accent_pressed": "#2f5a94",
    "background_window": "#1f1f28",
    "background_surface": "#27293a",
    "background_input": "#252535",
    "background_input_focus": "#2f3043",
    "background_disabled": "#2c2c3b",
    "border": "#3d3d52",
    "border_focus": "#4d8fe3",
    "border_disabled": "#2a2a3a",
    "text_primary": "#f2f2f5",
    "text_secondary": "#c7cad4",
    "text_disabled": "#7a7d8a",
    "selection_bg": "#3d7dca",
    "selection_fg": "#ffffff",
    "tooltip_bg": "#27293a",
    "tooltip_fg": "#f2f2f5",
    "tooltip_border": "#3d3d52",
    "button_disabled_bg": "#2c2c3b",
    "button_disabled_border": "#2a2a3a",
    "tree_alternate_bg": "#2c2c3b",
    "header_bg": "#2c2c3b",
    "header_text": "#c7cad4",
    "splitter_handle_bg": "#2c2c3b",
    "progress_chunk": "#3d7dca",
    "status_bg": "#27293a",
    "scrollbar_bg": "#27293a",
    "scrollbar_handle": "#3d7dca",
    "scrollbar_handle_hover": "#2f5a94",
}


_THEME_TOKEN_OVERRIDES: Mapping[Theme, MutableMapping[str, str]] = {
    Theme.DARK: {},
    Theme.LIGHT: {
        "background_window": "#f5f7fa",
        "background_surface": "#ffffff",
        "background_input": "#f0f2f7",
        "background_input_focus": "#e6ebf5",
        "background_disabled": "#e0e7f1",
        "border": "#c5d0e0",
        "border_focus": "#3d7dca",
        "border_disabled": "#d1d9e6",
        "text_primary": "#1f2937",
        "text_secondary": "#4b5563",
        "text_disabled": "#9ca3af",
        "selection_bg": "#3d7dca",
        "selection_fg": "#ffffff",
        "tooltip_bg": "#ffffff",
        "tooltip_fg": "#1f2937",
        "tooltip_border": "#c5d0e0",
        "button_disabled_bg": "#e0e7f1",
        "button_disabled_border": "#d1d9e6",
        "tree_alternate_bg": "#eef2fb",
        "header_bg": "#eef2fb",
        "header_text": "#4b5563",
        "splitter_handle_bg": "#d1d9e6",
        "progress_chunk": "#3d7dca",
        "status_bg": "#eef2fb",
        "scrollbar_bg": "#e5e9f2",
        "scrollbar_handle": "#c5d0e0",
        "scrollbar_handle_hover": "#a7b4c8",
    },
    Theme.HIGH_CONTRAST: {
        "accent": "#ffd500",
        "accent_hover": "#ffea66",
        "accent_pressed": "#caa700",
        "background_window": "#000000",
        "background_surface": "#000000",
        "background_input": "#111111",
        "background_input_focus": "#222222",
        "background_disabled": "#1a1a1a",
        "border": "#ffffff",
        "border_focus": "#ffd500",
        "border_disabled": "#666666",
        "text_primary": "#ffffff",
        "text_secondary": "#f0f0f0",
        "text_disabled": "#aaaaaa",
        "selection_bg": "#ffd500",
        "selection_fg": "#000000",
        "tooltip_bg": "#000000",
        "tooltip_fg": "#ffffff",
        "tooltip_border": "#ffffff",
        "button_disabled_bg": "#1a1a1a",
        "button_disabled_border": "#333333",
        "tree_alternate_bg": "#111111",
        "header_bg": "#111111",
        "header_text": "#ffffff",
        "splitter_handle_bg": "#333333",
        "progress_chunk": "#ffd500",
        "status_bg": "#111111",
        "scrollbar_bg": "#111111",
        "scrollbar_handle": "#666666",
        "scrollbar_handle_hover": "#999999",
    },
}


def _resource_url(name: str) -> str:
    path = (_RESOURCE_DIR / name).resolve()
    return path.as_posix()


def _resolve_tokens(theme: Theme) -> dict[str, str]:
    base = dict(_BASE_TOKENS)
    overrides = _THEME_TOKEN_OVERRIDES.get(theme)
    if overrides:
        base.update(overrides)
    return base


def resolve_theme_choice(
    theme: Theme, app: "QtWidgets.QApplication | None" = None
) -> Theme:
    """Resolve ``Theme.AUTO`` into a concrete theme."""

    if theme is not Theme.AUTO:
        return theme
    if QtGui is None or QtWidgets is None or app is None:
        return Theme.DARK
    palette = app.palette()
    window = palette.color(QtGui.QPalette.ColorRole.Window)
    return Theme.LIGHT if window.lightness() > 128 else Theme.DARK


def build_palette(theme: Theme) -> "QtGui.QPalette | None":
    """Build a :class:`~PySide6.QtGui.QPalette` for ``theme``."""

    if QtGui is None:
        return None
    resolved = theme if theme is not Theme.AUTO else Theme.DARK
    tokens = _resolve_tokens(resolved)
    palette = QtGui.QPalette()

    palette.setColor(
        QtGui.QPalette.ColorRole.Window, QtGui.QColor(tokens["background_window"])
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(tokens["text_primary"])
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.Base, QtGui.QColor(tokens["background_input"])
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.AlternateBase,
        QtGui.QColor(tokens["tree_alternate_bg"]),
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(tokens["tooltip_bg"])
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor(tokens["tooltip_fg"])
    )
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(tokens["text_primary"]))
    palette.setColor(
        QtGui.QPalette.ColorRole.Button, QtGui.QColor(tokens["background_surface"])
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor(tokens["text_primary"])
    )
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor("#ff0000"))
    palette.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(tokens["accent"]))
    palette.setColor(
        QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(tokens["selection_bg"])
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.HighlightedText,
        QtGui.QColor(tokens["selection_fg"]),
    )

    disabled_group = QtGui.QPalette.ColorGroup.Disabled
    palette.setColor(
        disabled_group, QtGui.QPalette.ColorRole.Text, QtGui.QColor(tokens["text_disabled"])
    )
    palette.setColor(
        disabled_group,
        QtGui.QPalette.ColorRole.ButtonText,
        QtGui.QColor(tokens["text_disabled"]),
    )
    palette.setColor(
        disabled_group,
        QtGui.QPalette.ColorRole.WindowText,
        QtGui.QColor(tokens["text_disabled"]),
    )
    palette.setColor(
        disabled_group, QtGui.QPalette.ColorRole.Base, QtGui.QColor(tokens["background_disabled"])
    )
    palette.setColor(
        disabled_group,
        QtGui.QPalette.ColorRole.Button,
        QtGui.QColor(tokens["button_disabled_bg"]),
    )

    return palette


def _resolve_default_font(app: "QtWidgets.QApplication") -> "QtGui.QFont | None":
    if QtGui is None:
        return None
    if running_on_windows_native():
        font = QtGui.QFont("Segoe UI")
        if font.pointSize() <= 0:
            font.setPointSize(10)
    else:
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


def build_stylesheet(theme: Theme) -> str:
    """Return the Qt stylesheet string for ``theme``."""

    resolved = theme if theme is not Theme.AUTO else Theme.DARK
    tokens = _resolve_tokens(resolved)
    branch_closed_icon = _resource_url("tree_branch_closed.svg")
    branch_open_icon = _resource_url("tree_branch_open.svg")

    return (
        "QToolTip {"
        "    color: %s;"
        "    background-color: %s;"
        "    border: 1px solid %s;"
        "    border-radius: 6px;"
        "    padding: 6px;"
        "}"
        % (tokens["tooltip_fg"], tokens["tooltip_bg"], tokens["tooltip_border"])
        + "\n"
        "QMainWindow {"
        "    background-color: %s;"
        "    color: %s;"
        "}" % (tokens["background_window"], tokens["text_primary"]) + "\n"
        "QWidget {"
        "    color: %s;"
        "    background-color: %s;"
        "    selection-background-color: %s;"
        "    selection-color: %s;"
        "}"
        % (
            tokens["text_primary"],
            tokens["background_window"],
            tokens["selection_bg"],
            tokens["selection_fg"],
        )
        + "\n"
        "QLabel { color: %s; }" % tokens["text_primary"]
        + "\n"
        "QPushButton {"
        "    background-color: %s;"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    padding: 6px 14px;"
        "    color: %s;"
        "}"
        % (
            tokens["background_surface"],
            tokens["border"],
            tokens["text_primary"],
        )
        + "\n"
        "QPushButton:hover {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}" % (tokens["accent_hover"], tokens["accent"])
        + "\n"
        "QPushButton:pressed {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}" % (tokens["accent_pressed"], tokens["accent_pressed"])
        + "\n"
        "QPushButton:disabled {"
        "    color: %s;"
        "    background-color: %s;"
        "    border-color: %s;"
        "}"
        % (
            tokens["text_disabled"],
            tokens["button_disabled_bg"],
            tokens["button_disabled_border"],
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
            tokens["background_input"],
            tokens["border"],
            tokens["text_primary"],
        )
        + "\n"
        "QSpinBox, QDoubleSpinBox {"
        "    padding-right: 32px;"
        "}"
        + "\n"
        "QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus,"
        " QSpinBox:focus, QDoubleSpinBox:focus {"
        "    border: 1px solid %s;"
        "    background-color: %s;"
        "}"
        % (tokens["border_focus"], tokens["background_input_focus"])
        + "\n"
        "QSpinBox::up-button, QDoubleSpinBox::up-button {"
        "    subcontrol-origin: border;"
        "    subcontrol-position: top right;"
        "    width: 26px;"
        "    border-left: 1px solid %s;"
        "    border-bottom: 1px solid %s;"
        "    border-top-right-radius: 6px;"
        "    background-color: %s;"
        "    padding: 0;"
        "    margin: 0;"
        "}"
        % (
            tokens["border"],
            tokens["border"],
            tokens["background_surface"],
        )
        + "\n"
        "QSpinBox::down-button, QDoubleSpinBox::down-button {"
        "    subcontrol-origin: border;"
        "    subcontrol-position: bottom right;"
        "    width: 26px;"
        "    border-left: 1px solid %s;"
        "    border-top: 1px solid %s;"
        "    border-bottom-right-radius: 6px;"
        "    background-color: %s;"
        "    padding: 0;"
        "    margin: 0;"
        "}"
        % (
            tokens["border"],
            tokens["border"],
            tokens["background_surface"],
        )
        + "\n"
        "QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,"
        " QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}" % (tokens["accent_hover"], tokens["accent"])
        + "\n"
        "QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,"
        " QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}" % (tokens["accent_pressed"], tokens["accent_pressed"])
        + "\n"
        "QSpinBox::up-button:disabled, QDoubleSpinBox::up-button:disabled,"
        " QSpinBox::down-button:disabled, QDoubleSpinBox::down-button:disabled {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}"
        % (
            tokens["button_disabled_bg"],
            tokens["button_disabled_border"],
        )
        + "\n"
        "QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {"
        '    image: url("%s");'
        "    width: 12px;"
        "    height: 12px;"
        "}" % (_SPIN_UP_ICON,)
        + "\n"
        "QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {"
        '    image: url("%s");'
        "    width: 12px;"
        "    height: 12px;"
        "}" % (_SPIN_DOWN_ICON,)
        + "\n"
        "QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {"
        '    image: url("%s");'
        "}" % (_SPIN_UP_ICON,)
        + "\n"
        "QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {"
        '    image: url("%s");'
        "}" % (_SPIN_DOWN_ICON,)
        + "\n"
        "QTreeWidget, QTreeView, QListWidget, QListView {"
        "    background-color: %s;"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    alternate-background-color: %s;"
        "}"
        % (
            tokens["background_surface"],
            tokens["border"],
            tokens["tree_alternate_bg"],
        )
        + "\n"
        "QTreeView::branch:has-children:!has-siblings:closed,"
        "QTreeView::branch:has-children:!has-siblings:closed:hover,"
        "QTreeView::branch:has-children:!has-siblings:closed:pressed {"
        '    image: url("%s");'
        "    padding: 6px;"
        "    margin: 0px;"
        "}" % (branch_closed_icon,)
        + "\n"
        "QTreeView::branch:has-children:!has-siblings:open,"
        "QTreeView::branch:has-children:!has-siblings:open:hover,"
        "QTreeView::branch:has-children:!has-siblings:open:pressed {"
        '    image: url("%s");'
        "    padding: 6px;"
        "    margin: 0px;"
        "}" % (branch_open_icon,)
        + "\n"
        "QHeaderView::section {"
        "    background-color: %s;"
        "    color: %s;"
        "    padding: 6px;"
        "    border: none;"
        "    border-right: 1px solid %s;"
        "}"
        % (
            tokens["header_bg"],
            tokens["header_text"],
            tokens["border"],
        )
        + "\n"
        "QSplitter::handle {"
        "    background: %s;"
        "    border: 1px solid %s;"
        "    margin: 4px;"
        "    border-radius: 4px;"
        "}"
        % (tokens["splitter_handle_bg"], tokens["border"])
        + "\n"
        "QSplitter::handle:hover {"
        "    background: %s;"
        "    border-color: %s;"
        "}" % (tokens["accent"], tokens["accent"])
        + "\n"
        "QSplitter::handle:pressed {"
        "    background: %s;"
        "}" % (tokens["accent_pressed"],)
        + "\n"
        "QProgressBar {"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    background-color: %s;"
        "    color: %s;"
        "    text-align: center;"
        "    padding: 2px;"
        "}"
        % (
            tokens["border"],
            tokens["background_surface"],
            tokens["text_primary"],
        )
        + "\n"
        "QProgressBar::chunk {"
        "    background-color: %s;"
        "    border-radius: 6px;"
        "}" % (tokens["progress_chunk"],)
        + "\n"
        "QScrollBar:vertical {"
        "    background: %s;"
        "    width: 14px;"
        "    margin: 4px 2px 4px 2px;"
        "    border-radius: 6px;"
        "}" % (tokens["scrollbar_bg"],)
        + "\n"
        "QScrollBar::handle:vertical {"
        "    background: %s;"
        "    min-height: 24px;"
        "    border-radius: 6px;"
        "}" % (tokens["scrollbar_handle"],)
        + "\n"
        "QScrollBar::handle:vertical:hover {"
        "    background: %s;"
        "}" % (tokens["scrollbar_handle_hover"],)
        + "\n"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
        "    background: none;"
        "}"
        + "\n"
        "QStatusBar {"
        "    background: %s;"
        "    color: %s;"
        "}" % (tokens["status_bg"], tokens["text_primary"])
        + "\n"
        "QGroupBox {"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    margin-top: 16px;"
        "    padding: 10px;"
        "}"
        % (tokens["border"],)
        + "\n"
        "QGroupBox::title {"
        "    subcontrol-origin: margin;"
        "    subcontrol-position: top left;"
        "    padding: 0 6px;"
        "    color: %s;"
        "}" % (tokens["text_secondary"],)
    )


def apply_modern_theme(theme: Theme, app: "QtWidgets.QApplication | None") -> None:
    """Apply the selected theme to ``app`` while remaining WSL-friendly."""

    if app is None or QtWidgets is None:
        return

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

    resolved = resolve_theme_choice(theme, app)

    palette = build_palette(resolved)
    if palette is not None:
        app.setPalette(palette)

    font = _resolve_default_font(app)
    if font is not None:
        app.setFont(font)

    app.setStyleSheet(build_stylesheet(resolved))


__all__ = [
    "apply_modern_theme",
    "build_palette",
    "build_stylesheet",
    "resolve_theme_choice",
]
