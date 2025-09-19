from __future__ import annotations

from typing import Any

import pytest

from patch_gui import theme as theme_module
from patch_gui.config import Theme

try:  # pragma: no cover - optional dependency
    from PySide6 import QtCore as _QtCore
    from PySide6 import QtGui as _QtGui
    from PySide6 import QtWidgets as _QtWidgets
except Exception as exc:  # pragma: no cover - bindings missing at runtime
    QtCore: Any | None = None
    QtGui: Any | None = None
    QtWidgets: Any | None = None
    _QT_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - executed when bindings are available
    QtCore = _QtCore
    QtGui = _QtGui
    QtWidgets = _QtWidgets
    _QT_IMPORT_ERROR = None

if QtWidgets is not None:  # pragma: no cover - optional dependency
    from patch_gui.highlighter import DiffHighlighter
else:  # pragma: no cover - executed when bindings are missing
    DiffHighlighter = None  # type: ignore[assignment]


@pytest.fixture()
def themed_app() -> Any:
    if QtWidgets is None:
        pytest.skip(f"PySide6 non disponibile: {_QT_IMPORT_ERROR}")
    assert QtGui is not None
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    original_palette = QtGui.QPalette(app.palette())
    original_stylesheet = app.styleSheet()
    original_style_name = app.style().objectName()
    yield app
    app.setPalette(original_palette)
    app.setStyleSheet(original_stylesheet)
    if original_style_name:
        app.setStyle(original_style_name)


@pytest.mark.skipif(QtWidgets is None, reason="PySide6 non disponibile")
def test_build_palette_high_contrast_uses_tokens() -> None:
    assert QtGui is not None
    palette = theme_module.build_palette(Theme.HIGH_CONTRAST)
    assert palette is not None
    window_color = palette.color(QtGui.QPalette.ColorRole.Window).name().lower()
    highlight_color = palette.color(
        QtGui.QPalette.ColorRole.Highlight
    ).name().lower()
    assert window_color == "#000000"
    assert highlight_color == "#ffd500"


@pytest.mark.skipif(QtWidgets is None, reason="PySide6 non disponibile")
def test_apply_modern_theme_updates_palette_and_stylesheet(themed_app: Any) -> None:
    assert QtGui is not None
    theme_module.apply_modern_theme(Theme.LIGHT, themed_app)
    palette = themed_app.palette()
    window_color = palette.color(QtGui.QPalette.ColorRole.Window).name().lower()
    assert window_color == "#f5f7fa"
    stylesheet = themed_app.styleSheet()
    assert "#f5f7fa" in stylesheet


def test_apply_modern_theme_gracefully_handles_missing_qt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(theme_module, "QtWidgets", None)
    monkeypatch.setattr(theme_module, "QtGui", None)
    theme_module.apply_modern_theme(Theme.DARK, None)
    assert theme_module.build_palette(Theme.DARK) is None
    assert theme_module.resolve_theme_choice(Theme.AUTO, None) is Theme.DARK


def test_theme_manager_activation_emits_palette_change() -> None:
    manager = theme_module.theme_manager()
    original_theme = manager.resolved_theme
    events: list[Theme] = []

    def _capture(palette: theme_module.ThemePalette) -> None:
        events.append(palette.theme)

    manager.palette_changed.connect(_capture)
    try:
        manager.activate(Theme.DARK, None)
        events.clear()
        manager.activate(Theme.LIGHT, None)
        assert manager.resolved_theme == Theme.LIGHT
        assert manager.palette.theme == Theme.LIGHT
        assert events and events[-1] == Theme.LIGHT
    finally:
        manager.activate(original_theme, None)


@pytest.mark.skipif(QtWidgets is None, reason="PySide6 non disponibile")
def test_diff_highlighter_updates_with_theme(themed_app: Any) -> None:
    assert QtGui is not None and DiffHighlighter is not None
    manager = theme_module.theme_manager()
    original_theme = manager.resolved_theme
    try:
        manager.activate(Theme.DARK, themed_app)
        document = QtGui.QTextDocument()
        highlighter = DiffHighlighter(document)
        dark_bg = (
            highlighter._addition_format.background().color().name().lower()  # type: ignore[attr-defined]
        )
        assert dark_bg == manager.palette.color("diff_add_bg").lower()

        manager.activate(Theme.LIGHT, themed_app)
        light_bg = (
            highlighter._addition_format.background().color().name().lower()  # type: ignore[attr-defined]
        )
        assert light_bg == manager.palette.color("diff_add_bg").lower()
        assert light_bg != dark_bg
    finally:
        manager.activate(original_theme, themed_app)


@pytest.mark.skipif(QtWidgets is None, reason="PySide6 non disponibile")
def test_icon_palette_tracks_theme_tokens(themed_app: Any) -> None:
    assert QtGui is not None and QtCore is not None
    from patch_gui import app as app_module

    manager = theme_module.theme_manager()
    original_theme = manager.resolved_theme
    try:
        manager.activate(Theme.DARK, themed_app)
        dark_palette = app_module._icon_palette()
        dark_base = dark_palette["base"].name().lower()
        assert dark_base == manager.palette.qcolor("icon_base").name().lower()

        manager.activate(Theme.LIGHT, themed_app)
        light_palette = app_module._icon_palette()
        light_base = light_palette["base"].name().lower()
        assert light_base == manager.palette.qcolor("icon_base").name().lower()
        assert dark_base != light_base
    finally:
        manager.activate(original_theme, themed_app)


@pytest.mark.skipif(QtWidgets is None, reason="PySide6 non disponibile")
def test_generated_icon_uses_active_palette_colors(themed_app: Any) -> None:
    assert QtGui is not None and QtCore is not None
    from patch_gui import app as app_module

    manager = theme_module.theme_manager()
    original_theme = manager.resolved_theme
    try:
        manager.activate(Theme.DARK, themed_app)
        dark_icon = app_module._create_generated_icon("load_diff", QtCore.QSize(48, 48))
        assert dark_icon is not None
        dark_image = dark_icon.pixmap(48, 48).toImage()
        dark_colors = {
            QtGui.QColor(dark_image.pixel(x, y)).name().lower()
            for x in range(dark_image.width())
            for y in range(dark_image.height())
        }
        dark_accent = manager.palette.qcolor("icon_accent").name().lower()
        assert dark_accent in dark_colors

        manager.activate(Theme.LIGHT, themed_app)
        light_icon = app_module._create_generated_icon("load_diff", QtCore.QSize(48, 48))
        assert light_icon is not None
        light_image = light_icon.pixmap(48, 48).toImage()
        light_colors = {
            QtGui.QColor(light_image.pixel(x, y)).name().lower()
            for x in range(light_image.width())
            for y in range(light_image.height())
        }
        light_accent = manager.palette.qcolor("icon_accent").name().lower()
        assert light_accent in light_colors

        assert dark_accent != light_accent
    finally:
        manager.activate(original_theme, themed_app)
