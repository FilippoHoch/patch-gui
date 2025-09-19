from __future__ import annotations

from typing import Any, Callable, cast

import pytest
from unidiff import PatchSet

from patch_gui.diff_formatting import (
    format_diff_with_line_numbers,
    render_diff_segments,
)
from patch_gui.interactive_diff_model import FileDiffEntry
from tests._pytest_typing import typed_fixture

SplitDiffView: type[Any] | None
InteractiveDiffWidget: type[Any] | None
build_diff_highlight_palette: Callable[..., Any] | None

try:  # pragma: no cover - optional dependency
    from PySide6 import QtCore as _QtCore, QtWidgets as _QtWidgets
except Exception as exc:  # pragma: no cover - missing bindings
    QtWidgets: Any | None = None
    QtCore: Any | None = None
    _QT_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - bindings available
    QtWidgets = cast(Any, _QtWidgets)
    QtCore = cast(Any, _QtCore)
    _QT_IMPORT_ERROR = None

try:  # pragma: no cover - optional dependency
    from patch_gui.split_diff_view import SplitDiffView as _SplitDiffView
    from patch_gui.interactive_diff import (
        InteractiveDiffWidget as _InteractiveDiffWidget,
    )
    from patch_gui.highlighter import build_diff_highlight_palette as _build_palette
except Exception as exc:  # pragma: no cover - missing GUI deps
    SplitDiffView = None
    InteractiveDiffWidget = None
    build_diff_highlight_palette = None
    _WIDGET_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - bindings available
    SplitDiffView = cast(type[Any], _SplitDiffView)
    InteractiveDiffWidget = cast(type[Any], _InteractiveDiffWidget)
    build_diff_highlight_palette = cast(Callable[..., Any], _build_palette)
    _WIDGET_IMPORT_ERROR = None


@typed_fixture()
def qt_app() -> Any:
    if QtWidgets is None or _WIDGET_IMPORT_ERROR is not None:
        reason = _QT_IMPORT_ERROR or _WIDGET_IMPORT_ERROR
        pytest.skip(f"PySide6 non disponibile: {reason}")
    assert QtWidgets is not None
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _build_entry(diff_text: str) -> FileDiffEntry:
    patch_set = PatchSet(diff_text)
    assert patch_set, "diff privo di file"
    patched_file = patch_set[0]
    normalized = str(patched_file)
    if not normalized.endswith("\n"):
        normalized += "\n"
    additions = sum(
        1
        for line in normalized.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    deletions = sum(
        1
        for line in normalized.splitlines()
        if line.startswith("-") and not line.startswith("---")
    )
    try:
        rendered = render_diff_segments(patched_file)
    except Exception:
        rendered = None
    if rendered is not None and rendered.hunks:
        annotated_parts = [rendered.annotated_header_text]
        annotated_parts.extend(h.annotated_text for h in rendered.hunks)
        annotated = "".join(annotated_parts)
        header_text = rendered.header_text
        annotated_header = rendered.annotated_header_text
        hunks = rendered.hunks
        mask: tuple[bool, ...] | None = tuple(True for _ in hunks)
    else:
        annotated = format_diff_with_line_numbers(patched_file, normalized)
        header_text = rendered.header_text if rendered is not None else ""
        annotated_header = (
            rendered.annotated_header_text if rendered is not None else ""
        )
        hunks = rendered.hunks if rendered is not None else ()
        mask = tuple(True for _ in hunks) if hunks else None
    label = (
        getattr(patched_file, "path", None)
        or getattr(patched_file, "target_file", None)
        or getattr(patched_file, "source_file", None)
        or "file.txt"
    )
    return FileDiffEntry(
        file_label=label,
        diff_text=normalized,
        annotated_diff_text=annotated,
        additions=additions,
        deletions=deletions,
        header_text=header_text,
        annotated_header_text=annotated_header,
        hunks=hunks,
        hunk_apply_mask=mask,
    )


def _long_diff() -> str:
    lines: list[str] = [
        "diff --git a/long.txt b/long.txt",
        "index 0000000..1111111 100644",
        "--- a/long.txt",
        "+++ b/long.txt",
        "@@ -1,40 +1,40 @@",
    ]
    for idx in range(1, 41):
        if idx % 10 == 0:
            lines.append(f"-old line {idx}")
            lines.append(f"+new line {idx}")
        else:
            lines.append(f" line {idx}")
    return "\n".join(lines) + "\n"


def _two_hunk_diff() -> str:
    return (
        "\n".join(
            [
                "diff --git a/demo.txt b/demo.txt",
                "index 1111111..2222222 100644",
                "--- a/demo.txt",
                "+++ b/demo.txt",
                "@@ -1,4 +1,4 @@",
                " line a",
                "-line b",
                "+line bee",
                " line c",
                " line d",
                "@@ -10,0 +10,2 @@",
                "+tail one",
                "+tail two",
            ]
        )
        + "\n"
    )


def test_split_diff_view_synchronized_scroll(qt_app: Any) -> None:
    if SplitDiffView is None or QtWidgets is None:
        pytest.skip(
            f"PySide6 non disponibile: {_WIDGET_IMPORT_ERROR or _QT_IMPORT_ERROR}"
        )
    assert QtWidgets is not None
    assert build_diff_highlight_palette is not None
    entry = _build_entry(_long_diff())
    palette_widget = QtWidgets.QWidget()
    palette = build_diff_highlight_palette(palette_widget.palette())
    view = SplitDiffView(highlighter_palette=palette)
    view.set_entry(entry)
    view.show()
    qt_app.processEvents()

    assert view.hunk_widgets, "atteso almeno un hunk"
    hunk_widget = view.hunk_widgets[0]
    left_editor, right_editor = hunk_widget.editors

    left_bar = left_editor.verticalScrollBar()
    right_bar = right_editor.verticalScrollBar()

    left_bar.setValue(left_bar.maximum())
    qt_app.processEvents()
    assert right_bar.value() == left_bar.value()

    right_bar.setValue(0)
    qt_app.processEvents()
    assert left_bar.value() == 0


def test_interactive_diff_inline_toggle_emits_signal(qt_app: Any) -> None:
    if InteractiveDiffWidget is None or QtWidgets is None:
        pytest.skip(
            f"PySide6 non disponibile: {_WIDGET_IMPORT_ERROR or _QT_IMPORT_ERROR}"
        )
    assert QtWidgets is not None
    assert QtCore is not None
    widget = InteractiveDiffWidget()
    patch_set = PatchSet(_two_hunk_diff())
    widget.set_patch(patch_set)
    qt_app.processEvents()

    captured: list[str] = []
    widget.diffReordered.connect(captured.append)

    split_view = widget._split_view
    assert split_view.hunk_widgets
    first_hunk = split_view.hunk_widgets[0]
    skip_button = first_hunk.findChild(QtWidgets.QToolButton, "splitDiffSkipButton")
    assert skip_button is not None
    skip_button.click()
    qt_app.processEvents()

    assert captured, "il segnale diffReordered deve essere emesso"
    last_diff = captured[-1]
    assert "@@ -1,4 +1,4 @@" not in last_diff
    assert "@@ -10,0 +10,2 @@" in last_diff

    current_item = widget._list_widget.currentItem()
    assert current_item is not None
    current_entry = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
    assert isinstance(current_entry, FileDiffEntry)
    assert current_entry.hunk_apply_mask is not None
    assert current_entry.hunk_apply_mask[0] is False


def test_interactive_diff_export_respects_selection(qt_app: Any) -> None:
    if InteractiveDiffWidget is None or QtWidgets is None:
        pytest.skip(
            f"PySide6 non disponibile: {_WIDGET_IMPORT_ERROR or _QT_IMPORT_ERROR}"
        )
    assert QtWidgets is not None
    assert QtCore is not None
    widget = InteractiveDiffWidget()
    patch_set = PatchSet(_two_hunk_diff())
    widget.set_patch(patch_set)
    qt_app.processEvents()

    split_view = widget._split_view
    first_hunk = split_view.hunk_widgets[0]
    skip_button = first_hunk.findChild(QtWidgets.QToolButton, "splitDiffSkipButton")
    assert skip_button is not None
    skip_button.click()
    qt_app.processEvents()

    exported: list[str] = []
    widget.diffReordered.connect(exported.append)
    widget._apply_reordered_diff()
    qt_app.processEvents()

    expected = "\n".join(
        [
            "diff --git a/demo.txt b/demo.txt",
            "index 1111111..2222222 100644",
            "--- a/demo.txt",
            "+++ b/demo.txt",
            "@@ -10,0 +10,2 @@",
            "+tail one",
            "+tail two",
            "",
        ]
    )
    assert exported
    assert exported[-1] == expected
