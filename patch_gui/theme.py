"""Application-wide theming helpers."""

from __future__ import annotations

from dataclasses import dataclass
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
    "diff_add_bg": "#1f3d2c",
    "diff_add_fg": "#9ae6b4",
    "diff_remove_bg": "#3c262c",
    "diff_remove_fg": "#f9a8b3",
    "diff_context_bg": "#24263a",
    "diff_context_fg": "#d4d7e8",
    "diff_header_bg": "#2f3d58",
    "diff_header_fg": "#f2f2f5",
    "diff_meta_fg": "#9ca0b5",
    "interactive_background": "#1f1f28",
    "interactive_surface": "#27293a",
    "interactive_surface_hover": "#30324a",
    "interactive_surface_pressed": "#23253b",
    "interactive_surface_disabled": "#1c1d2a",
    "interactive_border": "#3d3d52",
    "interactive_border_subtle": "#333449",
    "interactive_header_gradient_start": "#2f3a58",
    "interactive_header_gradient_end": "#252b40",
    "interactive_list_background": "#27293a",
    "interactive_list_hover_bg": "rgba(61, 125, 202, 0.18)",
    "interactive_list_selected_bg": "rgba(61, 125, 202, 0.32)",
    "interactive_list_selected_border": "#3d7dca",
    "interactive_preview_background": "#252535",
    "interactive_preview_border": "#3d3d52",
    "interactive_preview_disabled_bg": "#1f1f28",
    "interactive_preview_disabled_fg": "#7a7d8a",
    "interactive_badge_add_bg": "rgba(34, 197, 94, 0.24)",
    "interactive_badge_add_fg": "#8df0b6",
    "interactive_badge_del_bg": "rgba(239, 68, 68, 0.26)",
    "interactive_badge_del_fg": "#fca5a5",
    "interactive_badge_neutral_bg": "rgba(148, 163, 184, 0.22)",
    "interactive_badge_neutral_fg": "#f2f2f5",
    "interactive_order_index_color": "#3d7dca",
    "interactive_order_name_color": "#f2f2f5",
    "interactive_accent_disabled_bg": "rgba(61, 125, 202, 0.45)",
    "interactive_accent_disabled_fg": "#c7cad4",
    "interactive_on_accent": "#ffffff",
    "icon_base": "#0f172a",
    "icon_surface": "#1f2b4d",
    "icon_primary": "#4a7bd6",
    "icon_accent": "#7aa2ff",
    "icon_light": "#f1f5ff",
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
        "diff_add_bg": "#e6ffed",
        "diff_add_fg": "#166534",
        "diff_remove_bg": "#ffeef0",
        "diff_remove_fg": "#b91c1c",
        "diff_context_bg": "#f6f8fa",
        "diff_context_fg": "#24292e",
        "diff_header_bg": "#dbe9ff",
        "diff_header_fg": "#032f62",
        "diff_meta_fg": "#6a737d",
        "interactive_background": "#f5f7fa",
        "interactive_surface": "#ffffff",
        "interactive_surface_hover": "#f3f6fc",
        "interactive_surface_pressed": "#e4e8f4",
        "interactive_surface_disabled": "#e0e7f1",
        "interactive_border": "#c5d0e0",
        "interactive_border_subtle": "#d4dbe8",
        "interactive_header_gradient_start": "#f0f5ff",
        "interactive_header_gradient_end": "#dce7fa",
        "interactive_list_background": "#ffffff",
        "interactive_list_hover_bg": "rgba(61, 125, 202, 0.12)",
        "interactive_list_selected_bg": "rgba(61, 125, 202, 0.20)",
        "interactive_list_selected_border": "#3d7dca",
        "interactive_preview_background": "#f0f2f7",
        "interactive_preview_border": "#c5d0e0",
        "interactive_preview_disabled_bg": "#e0e7f1",
        "interactive_preview_disabled_fg": "#9ca3af",
        "interactive_badge_add_bg": "rgba(34, 197, 94, 0.16)",
        "interactive_badge_add_fg": "#166534",
        "interactive_badge_del_bg": "rgba(239, 68, 68, 0.16)",
        "interactive_badge_del_fg": "#b91c1c",
        "interactive_badge_neutral_bg": "rgba(148, 163, 184, 0.16)",
        "interactive_badge_neutral_fg": "#1f2937",
        "interactive_order_index_color": "#3d7dca",
        "interactive_order_name_color": "#1f2937",
        "interactive_accent_disabled_bg": "rgba(61, 125, 202, 0.32)",
        "interactive_accent_disabled_fg": "#9ca3af",
        "interactive_on_accent": "#ffffff",
        "icon_base": "#1f2937",
        "icon_surface": "#dce7fa",
        "icon_primary": "#2563eb",
        "icon_accent": "#3b82f6",
        "icon_light": "#eff6ff",
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
        "diff_add_bg": "#002b00",
        "diff_add_fg": "#00ff00",
        "diff_remove_bg": "#2b0000",
        "diff_remove_fg": "#ff4d4d",
        "diff_context_bg": "#000000",
        "diff_context_fg": "#ffffff",
        "diff_header_bg": "#000000",
        "diff_header_fg": "#ffd500",
        "diff_meta_fg": "#ffffff",
        "interactive_background": "#000000",
        "interactive_surface": "#000000",
        "interactive_surface_hover": "#1a1a1a",
        "interactive_surface_pressed": "#333333",
        "interactive_surface_disabled": "#0d0d0d",
        "interactive_border": "#ffffff",
        "interactive_border_subtle": "#666666",
        "interactive_header_gradient_start": "#333333",
        "interactive_header_gradient_end": "#000000",
        "interactive_list_background": "#000000",
        "interactive_list_hover_bg": "rgba(255, 213, 0, 0.25)",
        "interactive_list_selected_bg": "rgba(255, 213, 0, 0.35)",
        "interactive_list_selected_border": "#ffd500",
        "interactive_preview_background": "#000000",
        "interactive_preview_border": "#ffffff",
        "interactive_preview_disabled_bg": "#1a1a1a",
        "interactive_preview_disabled_fg": "#f0f0f0",
        "interactive_badge_add_bg": "rgba(0, 255, 0, 0.40)",
        "interactive_badge_add_fg": "#000000",
        "interactive_badge_del_bg": "rgba(255, 0, 0, 0.40)",
        "interactive_badge_del_fg": "#000000",
        "interactive_badge_neutral_bg": "rgba(255, 255, 255, 0.40)",
        "interactive_badge_neutral_fg": "#000000",
        "interactive_order_index_color": "#ffd500",
        "interactive_order_name_color": "#ffffff",
        "interactive_accent_disabled_bg": "rgba(255, 213, 0, 0.40)",
        "interactive_accent_disabled_fg": "#000000",
        "interactive_on_accent": "#000000",
        "icon_base": "#ffffff",
        "icon_surface": "#000000",
        "icon_primary": "#ffd500",
        "icon_accent": "#ffffff",
        "icon_light": "#000000",
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


@dataclass(frozen=True, slots=True)
class ThemePalette:
    """Container holding the resolved colour tokens for a theme."""

    theme: Theme
    tokens: Mapping[str, str]

    def color(self, token: str) -> str:
        return self.tokens[token]

    def get(self, token: str, default: str | None = None) -> str | None:
        return self.tokens.get(token, default)

    def qcolor(self, token: str) -> "QtGui.QColor":
        if QtGui is None:  # pragma: no cover - GUI bindings not available
            raise RuntimeError("Qt GUI bindings are not available")
        return QtGui.QColor(self.color(token))


class _CallbackSignal:
    """Fallback signal implementation used when Qt signals are unavailable."""

    __slots__ = ("_callbacks",)

    def __init__(self) -> None:
        self._callbacks: list[callable] = []

    def connect(self, callback: callable) -> None:
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs) -> None:
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class _ThemeManagerBase:
    """Shared implementation for the :class:`ThemeManager`."""

    def __init__(self) -> None:
        self._palettes: dict[Theme, ThemePalette] = {}
        self._selected_theme: Theme = Theme.AUTO
        self._resolved_theme: Theme = Theme.DARK
        self._current_palette: ThemePalette = ThemePalette(
            self._resolved_theme, _resolve_tokens(self._resolved_theme)
        )
        self._initializing = True
        for theme in (Theme.DARK, Theme.LIGHT, Theme.HIGH_CONTRAST):
            overrides = _THEME_TOKEN_OVERRIDES.get(theme, {})
            self.register_theme(theme, overrides)
        self._current_palette = self._palettes.get(
            self._resolved_theme, self._current_palette
        )
        self._initializing = False

    @property
    def palette(self) -> ThemePalette:
        return self._current_palette

    @property
    def selected_theme(self) -> Theme:
        return self._selected_theme

    @property
    def resolved_theme(self) -> Theme:
        return self._resolved_theme

    def register_theme(
        self, theme: Theme, overrides: Mapping[str, str] | None = None
    ) -> ThemePalette:
        tokens = dict(_BASE_TOKENS)
        if overrides:
            tokens.update(overrides)
        palette = ThemePalette(theme, tokens)
        self._palettes[theme] = palette
        if theme == self._resolved_theme:
            self._current_palette = palette
            if not self._initializing:
                self._emit_palette_changed(palette)
        return palette

    def activate(
        self,
        theme: Theme,
        app: "QtWidgets.QApplication | None" = None,
    ) -> ThemePalette:
        if theme is Theme.AUTO:
            resolved = resolve_theme_choice(theme, app)
        else:
            resolved = theme
        palette = self._palettes.get(resolved)
        if palette is None:
            overrides = _THEME_TOKEN_OVERRIDES.get(resolved, {})
            palette = self.register_theme(resolved, overrides)
        palette_changed = palette is not self._current_palette
        self._selected_theme = theme
        self._resolved_theme = resolved
        self._current_palette = palette
        if palette_changed and not self._initializing:
            self._emit_palette_changed(palette)
        return palette

    def _emit_palette_changed(self, palette: ThemePalette) -> None:
        raise NotImplementedError  # pragma: no cover - overridden in subclasses


if QtCore is not None:  # pragma: no cover - requires PySide6

    class ThemeManager(QtCore.QObject, _ThemeManagerBase):
        """Manager responsible for tracking and broadcasting theme changes."""

        palette_changed = QtCore.Signal(object)

        def __init__(self) -> None:
            QtCore.QObject.__init__(self)
            _ThemeManagerBase.__init__(self)

        def _emit_palette_changed(self, palette: ThemePalette) -> None:
            self.palette_changed.emit(palette)

else:  # pragma: no cover - executed when Qt bindings are unavailable

    class ThemeManager(_ThemeManagerBase):
        """Lightweight manager used when Qt signals are not available."""

        def __init__(self) -> None:
            self.palette_changed = _CallbackSignal()
            super().__init__()

        def _emit_palette_changed(self, palette: ThemePalette) -> None:
            self.palette_changed.emit(palette)


_THEME_MANAGER: ThemeManager | None = None


def theme_manager() -> ThemeManager:
    """Return the shared :class:`ThemeManager` instance."""

    global _THEME_MANAGER
    if _THEME_MANAGER is None:
        _THEME_MANAGER = ThemeManager()
    return _THEME_MANAGER


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

    manager = theme_manager()
    active_palette = manager.activate(theme, app if QtWidgets is not None else None)

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

    resolved = active_palette.theme

    palette = build_palette(resolved)
    if palette is not None:
        app.setPalette(palette)

    font = _resolve_default_font(app)
    if font is not None:
        app.setFont(font)

    app.setStyleSheet(build_stylesheet(resolved))


__all__ = [
    "ThemeManager",
    "ThemePalette",
    "apply_modern_theme",
    "build_palette",
    "build_stylesheet",
    "resolve_theme_choice",
    "theme_manager",
]
