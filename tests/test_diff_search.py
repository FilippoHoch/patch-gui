from __future__ import annotations

from typing import Any, List, Tuple

import pytest

try:  # pragma: no cover - optional dependency
    from PySide6 import QtWidgets as _QtWidgets
except Exception as exc:  # pragma: no cover - optional dependency
    QtWidgets: Any | None = None
    _QT_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - executed when bindings available
    QtWidgets = _QtWidgets
    _QT_IMPORT_ERROR = None

try:  # pragma: no cover - optional dependency
    from patch_gui.diff_search import DiffSearchHelper as _DiffSearchHelper
except Exception as exc:  # pragma: no cover - optional dependency
    DiffSearchHelper: Any | None = None
    _HELPER_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - executed when bindings available
    DiffSearchHelper = _DiffSearchHelper
    _HELPER_IMPORT_ERROR = None


@pytest.fixture()
def qt_app() -> Any:
    if QtWidgets is None or DiffSearchHelper is None:
        reason = _QT_IMPORT_ERROR if QtWidgets is None else _HELPER_IMPORT_ERROR
        pytest.skip(f"PySide6 non disponibile: {reason}")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _collect_matches(helper: DiffSearchHelper) -> List[Tuple[int, int, int, int]]:
    matches: List[Tuple[int, int, int, int]] = []
    helper.matchChanged.connect(matches.append)
    return matches


def test_helper_finds_and_navigates_matches(qt_app: Any) -> None:
    if QtWidgets is None:
        pytest.skip(f"PySide6 non disponibile: {_QT_IMPORT_ERROR}")

    editor = QtWidgets.QPlainTextEdit()
    editor.setPlainText("Alpha\nbeta\nALPHA\nalpha")
    helper = DiffSearchHelper(editor)
    captured = _collect_matches(helper)

    helper.set_pattern("alpha")
    qt_app.processEvents()

    assert helper.match_count == 3
    assert helper.current_index == 0
    assert editor.textCursor().selectedText() == "Alpha"
    assert captured[-1][:2] == (0, 3)

    helper.find_next()
    qt_app.processEvents()

    assert helper.current_index == 1
    assert editor.textCursor().selectedText() == "ALPHA"

    helper.find_previous()
    qt_app.processEvents()

    assert helper.current_index == 0
    assert editor.textCursor().selectedText() == "Alpha"


def test_helper_refreshes_after_document_change(qt_app: Any) -> None:
    if QtWidgets is None:
        pytest.skip(f"PySide6 non disponibile: {_QT_IMPORT_ERROR}")

    editor = QtWidgets.QPlainTextEdit()
    editor.setPlainText("one two one")
    helper = DiffSearchHelper(editor)
    captured = _collect_matches(helper)

    helper.set_pattern("one")
    qt_app.processEvents()
    assert helper.match_count == 2
    assert captured[-1][1] == 2

    editor.setPlainText("zero")
    qt_app.processEvents()
    helper.set_pattern("one", restart=False)
    qt_app.processEvents()

    assert helper.match_count == 0
    assert helper.current_index == -1
    assert captured[-1][0] == -1
