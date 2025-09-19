"""Application-wide theming helpers."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from PySide6 import QtCore, QtGui, QtWidgets

from .platform import running_on_windows_native, running_under_wsl


@dataclass(frozen=True)
class PaletteColors:
    """Container for the core colours exposed by a theme."""

    accent: QtGui.QColor
    accent_dark: QtGui.QColor
    background_window: QtGui.QColor
    background_elevated: QtGui.QColor
    background_input: QtGui.QColor
    border: QtGui.QColor
    border_focus: QtGui.QColor
    text_primary: QtGui.QColor
    text_secondary: QtGui.QColor
    text_disabled: QtGui.QColor
    selection_bg: QtGui.QColor
    selection_fg: QtGui.QColor
    tooltip_bg: QtGui.QColor
    tooltip_text: QtGui.QColor
    brand_base: QtGui.QColor
    brand_surface: QtGui.QColor
    brand_primary: QtGui.QColor
    brand_accent: QtGui.QColor
    brand_light: QtGui.QColor
    diff_add_bg: QtGui.QColor
    diff_add_fg: QtGui.QColor
    diff_remove_bg: QtGui.QColor
    diff_remove_fg: QtGui.QColor
    diff_context_bg: QtGui.QColor
    diff_context_fg: QtGui.QColor
    diff_header_bg: QtGui.QColor
    diff_header_fg: QtGui.QColor
    diff_meta_fg: QtGui.QColor


@dataclass(frozen=True)
class ThemeDefinition:
    """Descriptor for an available theme option."""

    key: str
    label: str
    colors: PaletteColors


_RESOURCE_DIR = Path(__file__).resolve().parent / "resources"
_DEFAULT_THEME_KEY = "dark"


def _resource_url(name: str) -> str:
    path = (_RESOURCE_DIR / name).resolve()
    return path.as_posix()


def _colour_name(color: QtGui.QColor) -> str:
    return QtGui.QColor(color).name()


def _encoded_arrow_svg(path_d: str, colour: QtGui.QColor) -> str:
    svg = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<svg width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" "
        "fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\">"
        f"  <path d=\"{path_d}\" fill=\"{_colour_name(colour)}\"/>"
        "</svg>"
    )
    return base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _build_palette(colors: PaletteColors) -> QtGui.QPalette:
    palette = QtGui.QPalette()

    palette.setColor(QtGui.QPalette.ColorRole.Window, colors.background_window)
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, colors.text_primary)
    palette.setColor(QtGui.QPalette.ColorRole.Base, colors.background_input)
    palette.setColor(
        QtGui.QPalette.ColorRole.AlternateBase, colors.background_elevated
    )
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, colors.tooltip_bg)
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, colors.tooltip_text)
    palette.setColor(QtGui.QPalette.ColorRole.Text, colors.text_primary)
    palette.setColor(QtGui.QPalette.ColorRole.Button, colors.background_elevated)
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, colors.text_primary)
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtCore.Qt.GlobalColor.red)
    palette.setColor(QtGui.QPalette.ColorRole.Link, colors.accent)
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, colors.selection_bg)
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, colors.selection_fg)

    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.Text,
        colors.text_disabled,
    )
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.ButtonText,
        colors.text_disabled,
    )
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.WindowText,
        colors.text_disabled,
    )

    return palette


def _build_stylesheet(colors: PaletteColors) -> str:
    branch_closed_icon = _resource_url("tree_branch_closed.svg")
    branch_open_icon = _resource_url("tree_branch_open.svg")

    accent_hover = QtGui.QColor(colors.accent).lighter(125)
    accent_pressed = QtGui.QColor(colors.accent_dark).darker(115)
    elevated_darker = QtGui.QColor(colors.background_elevated).darker(110)
    elevated_darkest = QtGui.QColor(colors.background_elevated).darker(125)
    border_subtle = QtGui.QColor(colors.border).darker(120)

    spin_up_svg = _encoded_arrow_svg("M12 6l6 8H6z", colors.accent)
    spin_down_svg = _encoded_arrow_svg("M12 18l-6-8h12z", colors.accent)
    spin_up_disabled_svg = _encoded_arrow_svg("M12 6l6 8H6z", colors.text_disabled)
    spin_down_disabled_svg = _encoded_arrow_svg(
        "M12 18l-6-8h12z", colors.text_disabled
    )

    return (
        "QToolTip {"
        "    color: %s;"
        "    background-color: %s;"
        "    border: 1px solid %s;"
        "    border-radius: 6px;"
        "    padding: 6px;"
        "}"
        % (
            colors.tooltip_text.name(),
            colors.tooltip_bg.name(),
            colors.border.name(),
        )
        + "\n"
        "QMainWindow {"
        "    background-color: %s;"
        "    color: %s;"
        "}"
        % (colors.background_window.name(), colors.text_primary.name())
        + "\n"
        "QWidget {"
        "    color: %s;"
        "    background-color: %s;"
        "    selection-background-color: %s;"
        "    selection-color: %s;"
        "}"
        % (
            colors.text_primary.name(),
            colors.background_window.name(),
            colors.selection_bg.name(),
            colors.selection_fg.name(),
        )
        + "\n"
        "QLabel { color: %s; }" % colors.text_primary.name()
        + "\n"
        "QPushButton {"
        "    background-color: %s;"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    padding: 6px 14px;"
        "    color: %s;"
        "}"
        % (
            colors.background_elevated.name(),
            colors.border.name(),
            colors.text_primary.name(),
        )
        + "\n"
        "QPushButton:hover {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}"
        % (accent_hover.name(), colors.accent.name())
        + "\n"
        "QPushButton:pressed {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}"
        % (colors.accent_dark.name(), accent_pressed.name())
        + "\n"
        "QPushButton:disabled {"
        "    color: %s;"
        "    background-color: %s;"
        "    border-color: %s;"
        "}"
        % (
            colors.text_disabled.name(),
            elevated_darker.name(),
            elevated_darkest.name(),
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
            colors.background_input.name(),
            colors.border.name(),
            colors.text_primary.name(),
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
        % (colors.border_focus.name(), colors.background_elevated.name())
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
            colors.border.name(),
            colors.border.name(),
            colors.background_elevated.name(),
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
            colors.border.name(),
            colors.border.name(),
            colors.background_elevated.name(),
        )
        + "\n"
        "QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,"
        " QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}"
        % (accent_hover.name(), colors.accent.name())
        + "\n"
        "QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,"
        " QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}"
        % (colors.accent_dark.name(), accent_pressed.name())
        + "\n"
        "QSpinBox::up-button:disabled, QDoubleSpinBox::up-button:disabled,"
        " QSpinBox::down-button:disabled, QDoubleSpinBox::down-button:disabled {"
        "    background-color: %s;"
        "    border-color: %s;"
        "}"
        % (elevated_darker.name(), elevated_darkest.name())
        + "\n"
        "QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {"
        f'    image: url("data:image/svg+xml;base64,{spin_up_svg}");'
        "    width: 12px;"
        "    height: 12px;"
        "}"
        + "\n"
        "QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {"
        f'    image: url("data:image/svg+xml;base64,{spin_down_svg}");'
        "    width: 12px;"
        "    height: 12px;"
        "}"
        + "\n"
        "QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {"
        f'    image: url("data:image/svg+xml;base64,{spin_up_disabled_svg}");'
        "}"
        + "\n"
        "QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {"
        f'    image: url("data:image/svg+xml;base64,{spin_down_disabled_svg}");'
        "}"
        + "\n"
        "QTreeWidget, QTreeView, QListWidget, QListView {"
        "    background-color: %s;"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    alternate-background-color: %s;"
        "}"
        % (
            colors.background_elevated.name(),
            colors.border.name(),
            colors.background_input.name(),
        )
        + "\n"
        "QTreeView::branch:has-children:!has-siblings:closed,"
        "QTreeView::branch:has-children:!has-siblings:closed:hover,"
        "QTreeView::branch:has-children:!has-siblings:closed:pressed {"
        f'    image: url("{branch_closed_icon}");'
        "    padding: 6px;"
        "    margin: 0px;"
        "}"
        + "\n"
        "QTreeView::branch:has-children:!has-siblings:open,"
        "QTreeView::branch:has-children:!has-siblings:open:hover,"
        "QTreeView::branch:has-children:!has-siblings:open:pressed {"
        f'    image: url("{branch_open_icon}");'
        "    padding: 6px;"
        "    margin: 0px;"
        "}"
        + "\n"
        "QHeaderView::section {"
        "    background-color: %s;"
        "    color: %s;"
        "    padding: 6px;"
        "    border: none;"
        "    border-right: 1px solid %s;"
        "}"
        % (
            colors.background_input.name(),
            colors.text_secondary.name(),
            colors.border.name(),
        )
        + "\n"
        "QSplitter::handle {"
        "    background: %s;"
        "    border: 1px solid %s;"
        "    margin: 4px;"
        "    border-radius: 4px;"
        "}"
        % (colors.background_input.name(), colors.border.name())
        + "\n"
        "QSplitter::handle:hover {"
        "    background: %s;"
        "    border-color: %s;"
        "}"
        % (colors.accent.name(), colors.accent.darker(120).name())
        + "\n"
        "QSplitter::handle:pressed {"
        "    background: %s;"
        "}"
        % (colors.accent_dark.name(),)
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
            colors.border.name(),
            colors.background_elevated.name(),
            colors.text_primary.name(),
        )
        + "\n"
        "QProgressBar::chunk {"
        "    background-color: %s;"
        "    border-radius: 6px;"
        "}"
        % (colors.accent.name(),)
        + "\n"
        "QScrollBar:vertical {"
        "    background: %s;"
        "    width: 14px;"
        "    margin: 4px 2px 4px 2px;"
        "    border-radius: 6px;"
        "}"
        % (colors.background_elevated.name(),)
        + "\n"
        "QScrollBar::handle:vertical {"
        "    background: %s;"
        "    min-height: 24px;"
        "    border-radius: 6px;"
        "}"
        % (colors.accent.name(),)
        + "\n"
        "QScrollBar::handle:vertical:hover {"
        "    background: %s;"
        "}"
        % (colors.accent_dark.name(),)
        + "\n"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
        "    background: none;"
        "}"
        + "\n"
        "QStatusBar {"
        "    background: %s;"
        "    color: %s;"
        "}"
        % (colors.background_elevated.name(), colors.text_primary.name())
        + "\n"
        "QGroupBox {"
        "    border: 1px solid %s;"
        "    border-radius: 8px;"
        "    margin-top: 16px;"
        "    padding: 10px;"
        "}"
        % (colors.border.name(),)
        + "\n"
        "QGroupBox::title {"
        "    subcontrol-origin: margin;"
        "    subcontrol-position: top left;"
        "    padding: 0 6px;"
        "    color: %s;"
        "}"
        % (colors.text_secondary.name(),)
    )


def _resolve_default_font(app: QtWidgets.QApplication) -> QtGui.QFont:
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


_DARK_THEME = ThemeDefinition(
    key="dark",
    label="Dark",
    colors=PaletteColors(
        accent=QtGui.QColor("#3d7dca"),
        accent_dark=QtGui.QColor("#2f5a94"),
        background_window=QtGui.QColor("#1f1f28"),
        background_elevated=QtGui.QColor("#27293a"),
        background_input=QtGui.QColor("#252535"),
        border=QtGui.QColor("#3d3d52"),
        border_focus=QtGui.QColor("#4d8fe3"),
        text_primary=QtGui.QColor("#f2f2f5"),
        text_secondary=QtGui.QColor("#c7cad4"),
        text_disabled=QtGui.QColor("#7a7d8a"),
        selection_bg=QtGui.QColor("#3d7dca"),
        selection_fg=QtGui.QColor("#ffffff"),
        tooltip_bg=QtGui.QColor("#27293a"),
        tooltip_text=QtGui.QColor("#f2f2f5"),
        brand_base=QtGui.QColor("#0f172a"),
        brand_surface=QtGui.QColor("#1f2b4d"),
        brand_primary=QtGui.QColor("#4a7bd6"),
        brand_accent=QtGui.QColor("#7aa2ff"),
        brand_light=QtGui.QColor("#f1f5ff"),
        diff_add_bg=QtGui.QColor("#e6ffed"),
        diff_add_fg=QtGui.QColor("#033a16"),
        diff_remove_bg=QtGui.QColor("#ffeef0"),
        diff_remove_fg=QtGui.QColor("#86181d"),
        diff_context_bg=QtGui.QColor("#f6f8fa"),
        diff_context_fg=QtGui.QColor("#24292e"),
        diff_header_bg=QtGui.QColor("#dbe9ff"),
        diff_header_fg=QtGui.QColor("#032f62"),
        diff_meta_fg=QtGui.QColor("#6a737d"),
    ),
)

_LIGHT_THEME = ThemeDefinition(
    key="light",
    label="Light",
    colors=PaletteColors(
        accent=QtGui.QColor("#2563eb"),
        accent_dark=QtGui.QColor("#1d4ed8"),
        background_window=QtGui.QColor("#f3f4f6"),
        background_elevated=QtGui.QColor("#ffffff"),
        background_input=QtGui.QColor("#f9fafb"),
        border=QtGui.QColor("#d1d5db"),
        border_focus=QtGui.QColor("#2563eb"),
        text_primary=QtGui.QColor("#1f2937"),
        text_secondary=QtGui.QColor("#4b5563"),
        text_disabled=QtGui.QColor("#9ca3af"),
        selection_bg=QtGui.QColor("#2563eb"),
        selection_fg=QtGui.QColor("#ffffff"),
        tooltip_bg=QtGui.QColor("#111827"),
        tooltip_text=QtGui.QColor("#f9fafb"),
        brand_base=QtGui.QColor("#1f2937"),
        brand_surface=QtGui.QColor("#2563eb"),
        brand_primary=QtGui.QColor("#3b82f6"),
        brand_accent=QtGui.QColor("#38bdf8"),
        brand_light=QtGui.QColor("#eff6ff"),
        diff_add_bg=QtGui.QColor("#dafbe1"),
        diff_add_fg=QtGui.QColor("#0a3622"),
        diff_remove_bg=QtGui.QColor("#ffebe9"),
        diff_remove_fg=QtGui.QColor("#86181d"),
        diff_context_bg=QtGui.QColor("#f6f8fa"),
        diff_context_fg=QtGui.QColor("#24292e"),
        diff_header_bg=QtGui.QColor("#dbe9ff"),
        diff_header_fg=QtGui.QColor("#032f62"),
        diff_meta_fg=QtGui.QColor("#57606a"),
    ),
)

_THEMES: Mapping[str, ThemeDefinition] = {
    _DARK_THEME.key: _DARK_THEME,
    _LIGHT_THEME.key: _LIGHT_THEME,
}


class ThemeManager(QtCore.QObject):
    """Manage theme application and notify widgets about palette changes."""

    paletteChanged = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._themes: Mapping[str, ThemeDefinition] = _THEMES
        self._current_key: str = _DEFAULT_THEME_KEY
        self._app: QtWidgets.QApplication | None = None
        self._current_palette: QtGui.QPalette = _build_palette(
            self._themes[self._current_key].colors
        )
        self._style_configured = False

    @property
    def available_themes(self) -> tuple[ThemeDefinition, ...]:
        return tuple(self._themes.values())

    @property
    def current_theme(self) -> ThemeDefinition:
        return self._themes[self._current_key]

    @property
    def colors(self) -> PaletteColors:
        return self.current_theme.colors

    @property
    def current_palette(self) -> QtGui.QPalette:
        return QtGui.QPalette(self._current_palette)

    def apply(
        self, app: QtWidgets.QApplication, theme: str | None = None
    ) -> None:
        self._app = app
        if theme:
            self._current_key = self._normalize_key(theme)
        self._apply_palette()

    def set_theme(self, theme: str) -> None:
        normalized = self._normalize_key(theme)
        self._current_key = normalized
        self._apply_palette()

    def _normalize_key(self, theme: str) -> str:
        key = (theme or "").strip().lower()
        if key in self._themes:
            return key
        return _DEFAULT_THEME_KEY

    def _ensure_base_style(self) -> None:
        if self._app is None or self._style_configured:
            return
        style_override = os.getenv("QT_STYLE_OVERRIDE")
        if style_override:
            self._app.setStyle(style_override)
        elif not running_under_wsl():
            available_styles = {
                name.lower(): name for name in QtWidgets.QStyleFactory.keys()
            }
            fusion = available_styles.get("fusion")
            if fusion:
                self._app.setStyle(fusion)
        self._app.setFont(_resolve_default_font(self._app))
        self._style_configured = True

    def _apply_palette(self) -> None:
        definition = self._themes[self._current_key]
        self._current_palette = _build_palette(definition.colors)
        self._ensure_base_style()
        if self._app is not None:
            self._app.setPalette(self._current_palette)
            self._app.setStyleSheet(_build_stylesheet(definition.colors))
        self.paletteChanged.emit(self._current_key)


theme_manager = ThemeManager()


def apply_modern_theme(
    app: QtWidgets.QApplication, *, theme: str | None = None
) -> None:
    """Apply the requested theme to ``app`` and configure base styling."""

    if app is None:
        return
    theme_manager.apply(app, theme=theme)


__all__ = [
    "PaletteColors",
    "ThemeDefinition",
    "ThemeManager",
    "apply_modern_theme",
    "theme_manager",
]
