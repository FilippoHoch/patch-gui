from __future__ import annotations

from typing import Any, cast

import pytest

from tests._pytest_typing import typed_fixture

try:  # pragma: no cover - optional dependency guard
    from PySide6 import QtWidgets as _QtWidgets
except Exception as exc:  # pragma: no cover - optional dependency
    QtWidgets: Any | None = None
    _QT_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - exercised when bindings are available
    QtWidgets = cast(Any, _QtWidgets)
    _QT_IMPORT_ERROR = None

try:  # pragma: no cover - optional dependency guard
    from patch_gui.diff_search import DiffSearchHelper as _DiffSearchHelper
except Exception as exc:  # pragma: no cover - optional dependency
    DiffSearchHelper: Any | None = None
    _DIFF_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - exercised when bindings are available
    DiffSearchHelper = cast(Any, _DiffSearchHelper)
    _DIFF_IMPORT_ERROR = None


@typed_fixture()
def qt_app() -> Any:
    if QtWidgets is None or DiffSearchHelper is None:
        reason = _QT_IMPORT_ERROR if QtWidgets is None else _DIFF_IMPORT_ERROR
        pytest.skip(f"PySide6 non disponibile: {reason}")
    assert QtWidgets is not None
    assert DiffSearchHelper is not None
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def test_diff_search_helper_navigation(qt_app: Any) -> None:
    if QtWidgets is None or DiffSearchHelper is None:
        reason = _QT_IMPORT_ERROR if QtWidgets is None else _DIFF_IMPORT_ERROR
        pytest.skip(f"PySide6 non disponibile: {reason}")
    assert QtWidgets is not None
    assert DiffSearchHelper is not None

    editor = QtWidgets.QPlainTextEdit()
    editor.setPlainText("uno\nfoo\nFoo\nqualcosa\nfoo")
    helper = DiffSearchHelper(editor)

    helper.search("foo")

    matches = helper.matches
    assert len(matches) == 3
    assert matches[0].line == 1
    assert matches[1].line == 2
    assert matches[2].line == 4

    assert helper.current_index == 0
    assert helper.current_match == matches[0]

    helper.find_next()
    assert helper.current_match == matches[1]

    helper.find_next()
    assert helper.current_match == matches[2]

    helper.find_next()  # wrap around
    assert helper.current_match == matches[0]

    helper.find_previous()
    assert helper.current_match == matches[2]

    helper.set_case_sensitive(True)
    helper.search("Foo")
    case_sensitive = helper.matches
    assert len(case_sensitive) == 1
    assert case_sensitive[0].line == 2
    assert helper.current_match == case_sensitive[0]


def test_diff_search_helper_updates_on_text_change(qt_app: Any) -> None:
    if QtWidgets is None or DiffSearchHelper is None:
        reason = _QT_IMPORT_ERROR if QtWidgets is None else _DIFF_IMPORT_ERROR
        pytest.skip(f"PySide6 non disponibile: {reason}")
    assert QtWidgets is not None
    assert DiffSearchHelper is not None

    editor = QtWidgets.QPlainTextEdit()
    editor.setPlainText("alpha\nbeta\ngamma")
    helper = DiffSearchHelper(editor)

    helper.search("beta")
    assert len(helper.matches) == 1

    editor.setPlainText("alpha\ngamma")
    qt_app.processEvents()
    qt_app.processEvents()

    assert helper.matches == ()
    assert helper.current_match is None
