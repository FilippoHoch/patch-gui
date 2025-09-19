"""Synchronized split diff view for interactive review."""

from __future__ import annotations

import re
from typing import Sequence

from PySide6 import QtCore, QtGui, QtWidgets

from .highlighter import (
    DEFAULT_DIFF_PALETTE,
    DiffHighlighter,
    DiffHighlightPalette,
)
from .diff_formatting import RenderedHunk
from .interactive_diff_model import FileDiffEntry
from .localization import gettext as _


_NUMBERED_RE = re.compile(r"^(?P<left>.{6}) │ (?P<right>.{6}) │ (?P<content>.*)$")


class SplitDiffView(QtWidgets.QWidget):  # type: ignore[misc]
    """Render hunks of a :class:`FileDiffEntry` in synchronized columns."""

    hunkToggled = QtCore.Signal(int, bool)

    def __init__(
        self,
        *,
        highlighter_palette: DiffHighlightPalette | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._entry: FileDiffEntry | None = None
        self._highlighter_palette = highlighter_palette
        self._hunk_widgets: list[_HunkWidget] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._header_edit = QtWidgets.QPlainTextEdit()
        self._header_edit.setReadOnly(True)
        self._header_edit.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._header_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._header_edit.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._header_edit.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        header_font = QtGui.QFontDatabase.systemFont(
            QtGui.QFontDatabase.SystemFont.FixedFont
        )
        self._header_edit.setFont(header_font)
        self._header_highlighter = DiffHighlighter(
            self._header_edit.document(), palette=highlighter_palette
        )
        layout.addWidget(self._header_edit)

        self._scroll_area = QtWidgets.QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        layout.addWidget(self._scroll_area, 1)

        self._container = QtWidgets.QWidget()
        self._container_layout = QtWidgets.QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(16)
        self._scroll_area.setWidget(self._container)
        self._scroll_area.setVisible(False)

        self._placeholder = QtWidgets.QLabel(
            _("Nessun hunk da mostrare per questo file.")
        )
        self._placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setVisible(False)
        layout.addWidget(self._placeholder)

    @property
    def entry(self) -> FileDiffEntry | None:
        return self._entry

    @property
    def hunk_widgets(self) -> tuple["_HunkWidget", ...]:
        return tuple(self._hunk_widgets)

    def clear(self) -> None:
        self._entry = None
        self._header_edit.clear()
        self._header_edit.setVisible(False)
        self._clear_hunks()
        self._scroll_area.setVisible(False)
        self._placeholder.setVisible(False)

    def set_highlight_palette(self, palette: DiffHighlightPalette | None) -> None:
        self._highlighter_palette = palette
        self._header_highlighter.set_palette(palette or DEFAULT_DIFF_PALETTE)
        for widget in self._hunk_widgets:
            widget.set_highlight_palette(palette)

    def set_entry(
        self,
        entry: FileDiffEntry | None,
        *,
        apply_mask: Sequence[bool] | None = None,
    ) -> None:
        self._entry = entry
        self._clear_hunks()
        if entry is None:
            self._header_edit.clear()
            self._header_edit.setVisible(False)
            self._scroll_area.setVisible(False)
            self._placeholder.setVisible(False)
            return

        mask = _normalise_mask(entry, apply_mask)
        header_text = entry.annotated_header_text or entry.header_text
        self._header_edit.setPlainText(header_text)
        self._header_edit.setVisible(bool(header_text.strip()))

        if not entry.hunks:
            self._scroll_area.setVisible(False)
            self._placeholder.setVisible(True)
            return

        self._placeholder.setVisible(False)
        self._scroll_area.setVisible(True)
        for idx, hunk in enumerate(entry.hunks):
            applied = mask[idx] if idx < len(mask) else True
            widget = _HunkWidget(
                index=idx,
                hunk=hunk,
                applied=applied,
                highlighter_palette=self._highlighter_palette,
            )
            widget.hunkToggled.connect(self._emit_hunk_toggled)
            self._container_layout.addWidget(widget)
            self._hunk_widgets.append(widget)

        self._container_layout.addStretch(1)

    def update_hunk_state(self, index: int, applied: bool) -> None:
        if index < 0 or index >= len(self._hunk_widgets):
            return
        self._hunk_widgets[index].set_applied(applied)

    def _clear_hunks(self) -> None:
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._hunk_widgets.clear()

    def _emit_hunk_toggled(self, index: int, applied: bool) -> None:
        self.hunkToggled.emit(index, applied)


class _HunkWidget(QtWidgets.QFrame):  # type: ignore[misc]
    """Widget showing a single hunk with apply/skip controls."""

    hunkToggled = QtCore.Signal(int, bool)

    def __init__(
        self,
        *,
        index: int,
        hunk: RenderedHunk,
        applied: bool,
        highlighter_palette: DiffHighlightPalette | None,
    ) -> None:
        super().__init__()
        self._index = index
        self._applied = applied
        self._palette = highlighter_palette
        self.setObjectName("splitDiffHunk")
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header_row = QtWidgets.QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        layout.addLayout(header_row)

        title = QtWidgets.QLabel(hunk.header)
        title_font = QtGui.QFontDatabase.systemFont(
            QtGui.QFontDatabase.SystemFont.FixedFont
        )
        title.setFont(title_font)
        header_row.addWidget(title, 1)

        self._apply_button = QtWidgets.QToolButton()
        self._apply_button.setObjectName("splitDiffApplyButton")
        self._apply_button.setCheckable(True)
        self._apply_button.setText(_("Applica"))
        header_row.addWidget(self._apply_button)

        self._skip_button = QtWidgets.QToolButton()
        self._skip_button.setObjectName("splitDiffSkipButton")
        self._skip_button.setCheckable(True)
        self._skip_button.setText(_("Salta"))
        header_row.addWidget(self._skip_button)

        self._button_group = QtWidgets.QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._button_group.addButton(self._apply_button, 1)
        self._button_group.addButton(self._skip_button, 0)
        self._button_group.idClicked.connect(self._on_button_clicked)

        self._columns = _HunkColumns(hunk.annotated_text, highlighter_palette)
        layout.addWidget(self._columns)

        self.set_applied(applied)

    def set_highlight_palette(self, palette: DiffHighlightPalette | None) -> None:
        self._palette = palette
        self._columns.set_highlight_palette(palette)

    def set_applied(self, applied: bool) -> None:
        self._applied = applied
        target_id = 1 if applied else 0
        button = self._button_group.button(target_id)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self._columns.setEnabled(applied)

    @property
    def editors(self) -> tuple[QtWidgets.QPlainTextEdit, QtWidgets.QPlainTextEdit]:
        return (self._columns.left_editor, self._columns.right_editor)

    def _on_button_clicked(self, value: int) -> None:
        applied = bool(value)
        if self._applied == applied:
            return
        self._applied = applied
        self._columns.setEnabled(applied)
        self.hunkToggled.emit(self._index, applied)


class _HunkColumns(QtWidgets.QWidget):  # type: ignore[misc]
    """Two synchronized ``QPlainTextEdit`` widgets for a diff hunk."""

    def __init__(
        self,
        annotated_text: str,
        highlighter_palette: DiffHighlightPalette | None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.left_editor = _create_plain_text_edit()
        self.right_editor = _create_plain_text_edit()
        layout.addWidget(self.left_editor, 1)
        layout.addWidget(self.right_editor, 1)

        self._left_highlighter = DiffHighlighter(
            self.left_editor.document(), palette=highlighter_palette
        )
        self._right_highlighter = DiffHighlighter(
            self.right_editor.document(), palette=highlighter_palette
        )

        left_text, right_text = _split_columns(annotated_text)
        self.left_editor.setPlainText(left_text)
        self.right_editor.setPlainText(right_text)

        self._sync_guard = False
        self.left_editor.verticalScrollBar().valueChanged.connect(self._sync_right)
        self.right_editor.verticalScrollBar().valueChanged.connect(self._sync_left)

    def set_highlight_palette(self, palette: DiffHighlightPalette | None) -> None:
        self._left_highlighter.set_palette(palette or DEFAULT_DIFF_PALETTE)
        self._right_highlighter.set_palette(palette or DEFAULT_DIFF_PALETTE)

    def _sync_right(self, value: int) -> None:
        if self._sync_guard:
            return
        self._sync_guard = True
        self.right_editor.verticalScrollBar().setValue(value)
        self._sync_guard = False

    def _sync_left(self, value: int) -> None:
        if self._sync_guard:
            return
        self._sync_guard = True
        self.left_editor.verticalScrollBar().setValue(value)
        self._sync_guard = False


def _create_plain_text_edit() -> QtWidgets.QPlainTextEdit:
    editor = QtWidgets.QPlainTextEdit()
    editor.setReadOnly(True)
    editor.setFrameShape(QtWidgets.QFrame.Shape.Box)
    editor.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
    editor.setFont(
        QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
    )
    return editor


def _split_columns(annotated_text: str) -> tuple[str, str]:
    left_lines: list[str] = []
    right_lines: list[str] = []
    for line in annotated_text.splitlines():
        if line.startswith("@@"):
            continue
        match = _NUMBERED_RE.match(line)
        if not match:
            left_lines.append(line)
            right_lines.append(line)
            continue
        left_no = match.group("left")
        right_no = match.group("right")
        content = match.group("content")
        marker = content[:1] if content else ""
        remainder = content[1:] if len(content) > 1 else ""
        if marker == "+":
            left_content = " " + remainder
            right_content = content
        elif marker == "-":
            left_content = content
            right_content = " " + remainder
        else:
            left_content = content
            right_content = content
        left_lines.append(f"{left_no} │ {left_content}")
        right_lines.append(f"{right_no} │ {right_content}")
    return "\n".join(left_lines), "\n".join(right_lines)


def _normalise_mask(
    entry: FileDiffEntry, apply_mask: Sequence[bool] | None
) -> Sequence[bool]:
    if apply_mask is not None:
        return apply_mask
    if entry.hunk_apply_mask is not None:
        return entry.hunk_apply_mask
    return [True] * entry.hunk_count
