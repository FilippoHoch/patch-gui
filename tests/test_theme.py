from __future__ import annotations

from typing import Any, Callable, TypeVar, cast

import pytest

from patch_gui import theme as theme_module
from patch_gui.config import Theme
from tests._pytest_typing import typed_fixture

try:  # pragma: no cover - optional dependency
    from PySide6 import QtGui as _QtGui
    from PySide6 import QtWidgets as _QtWidgets
except Exception as exc:  # pragma: no cover - bindings missing at runtime
    QtGui: Any | None = None
    QtWidgets: Any | None = None
    _QT_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - executed when bindings are available
    QtGui = cast(Any, _QtGui)
    QtWidgets = cast(Any, _QtWidgets)
_QT_IMPORT_ERROR = None

_F = TypeVar("_F", bound=Callable[..., object])


def typed_skipif(condition: bool, *, reason: str) -> Callable[[_F], _F]:
    decorator = pytest.mark.skipif(condition, reason=reason)
    return cast(Callable[[_F], _F], decorator)


@typed_fixture()
def themed_app() -> Any:
    if QtWidgets is None:
        pytest.skip(f"PySide6 non disponibile: {_QT_IMPORT_ERROR}")
    assert QtGui is not None
    assert QtWidgets is not None
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


@typed_skipif(QtWidgets is None, reason="PySide6 non disponibile")
def test_build_palette_high_contrast_uses_tokens() -> None:
    assert QtGui is not None
    palette = theme_module.build_palette(Theme.HIGH_CONTRAST)
    assert palette is not None
    window_color = palette.color(QtGui.QPalette.ColorRole.Window).name().lower()
    highlight_color = palette.color(QtGui.QPalette.ColorRole.Highlight).name().lower()
    assert window_color == "#000000"
    assert highlight_color == "#ffd500"


@typed_skipif(QtWidgets is None, reason="PySide6 non disponibile")
def test_apply_modern_theme_updates_palette_and_stylesheet(themed_app: Any) -> None:
    assert QtGui is not None
    theme_module.apply_modern_theme(Theme.LIGHT, themed_app)
    palette = themed_app.palette()
    window_color = palette.color(QtGui.QPalette.ColorRole.Window).name().lower()
    assert window_color == "#f5f7fa"
    stylesheet = themed_app.styleSheet()
    assert "#f5f7fa" in stylesheet


def test_apply_modern_theme_gracefully_handles_missing_qt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(theme_module, "QtWidgets", None)
    monkeypatch.setattr(theme_module, "QtGui", None)
    theme_module.apply_modern_theme(Theme.DARK, None)
    assert theme_module.build_palette(Theme.DARK) is None
    assert theme_module.resolve_theme_choice(Theme.AUTO, None) is Theme.DARK


def test_theme_manager_exposes_core_palettes() -> None:
    palettes = theme_module.theme_manager.palettes
    assert Theme.DARK in palettes
    assert Theme.LIGHT in palettes
    assert "background_window" in palettes[Theme.DARK]


@typed_skipif(QtWidgets is None, reason="PySide6 non disponibile")
def test_theme_manager_notifies_listeners(themed_app: Any) -> None:
    assert QtGui is not None
    previous = theme_module.theme_manager.snapshot
    received: list[Theme] = []

    def listener(snapshot: theme_module.ThemeSnapshot) -> None:
        received.append(snapshot.theme)

    theme_module.theme_manager.add_listener(listener)
    try:
        theme_module.apply_modern_theme(Theme.LIGHT, themed_app)
        assert received and received[-1] == Theme.LIGHT
    finally:
        theme_module.theme_manager.remove_listener(listener)
        theme_module.apply_modern_theme(previous.theme, themed_app)
