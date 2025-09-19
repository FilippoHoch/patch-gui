import pytest

try:
    from patch_gui.theme import theme_manager
    from patch_gui.interactive_diff import InteractiveDiffWidget
except Exception as exc:  # pragma: no cover - optional dependency
    theme_manager = None
    InteractiveDiffWidget = None
    _THEME_IMPORT_ERROR: Exception | None = exc
else:
    _THEME_IMPORT_ERROR = None

try:  # pragma: no cover - environment-dependent
    from PySide6 import QtWidgets as _QtWidgets
except Exception as exc:  # pragma: no cover - optional dependency
    QtWidgets = None
    _QT_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - exercised when bindings are available
    QtWidgets = _QtWidgets
    _QT_IMPORT_ERROR = None


@pytest.fixture()
def qt_app() -> object:
    if QtWidgets is None:
        pytest.skip(f"PySide6 non disponibile: {_QT_IMPORT_ERROR}")
    if theme_manager is None:
        pytest.skip(f"Qt non disponibile: {_THEME_IMPORT_ERROR}")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    theme_manager.apply(app, theme="dark")
    return app


def test_theme_manager_switches_palettes(qt_app: object) -> None:
    if QtWidgets is None or theme_manager is None:
        pytest.skip(
            f"PySide6 non disponibile: {_QT_IMPORT_ERROR or _THEME_IMPORT_ERROR}"
        )
    seen: list[str] = []

    def _listener(key: str) -> None:
        seen.append(key)

    theme_manager.paletteChanged.connect(_listener)
    try:
        theme_manager.set_theme("light")
        if isinstance(qt_app, QtWidgets.QApplication):
            qt_app.processEvents()
        assert theme_manager.current_theme.key == "light"
        assert seen and seen[-1] == "light"

        light_palette = theme_manager.current_palette
        theme_manager.set_theme("dark")
        if isinstance(qt_app, QtWidgets.QApplication):
            qt_app.processEvents()
        assert theme_manager.current_theme.key == "dark"
        assert theme_manager.current_palette != light_palette
    finally:
        theme_manager.paletteChanged.disconnect(_listener)
        theme_manager.set_theme("dark")
        if isinstance(qt_app, QtWidgets.QApplication):
            qt_app.processEvents()


def test_interactive_diff_widget_updates_on_theme_change(qt_app: object) -> None:
    if QtWidgets is None or theme_manager is None or InteractiveDiffWidget is None:
        pytest.skip(
            f"PySide6 non disponibile: {_QT_IMPORT_ERROR or _THEME_IMPORT_ERROR}"
        )
    widget = InteractiveDiffWidget()
    initial_colors = widget._colors
    theme_manager.set_theme("light")
    if isinstance(qt_app, QtWidgets.QApplication):
        qt_app.processEvents()
    try:
        assert widget._colors != initial_colors
    finally:
        widget.deleteLater()
        theme_manager.set_theme("dark")
        if isinstance(qt_app, QtWidgets.QApplication):
            qt_app.processEvents()
