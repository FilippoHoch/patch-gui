"""Interactive diff viewer with drag-and-drop reordering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from PySide6 import QtCore, QtGui, QtWidgets

from .highlighter import DiffHighlighter
from .localization import gettext as _


@dataclass(frozen=True, slots=True)
class FileDiffEntry:
    """Store information about a file diff block."""

    file_label: str
    diff_text: str
    additions: int
    deletions: int

    @property
    def display_text(self) -> str:
        additions = _("+{count}").format(count=self.additions)
        deletions = _("-{count}").format(count=self.deletions)
        return _("{name} · {additions} / {deletions}").format(
            name=self.file_label,
            additions=additions,
            deletions=deletions,
        )


class InteractiveDiffWidget(QtWidgets.QWidget):
    """Widget that shows diff blocks and allows reordering them interactively."""

    diffReordered = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._original_entries: list[FileDiffEntry] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._info_label = QtWidgets.QLabel(
            _(
                "Trascina i file per cambiare l'ordine delle patch."
                " Premi \"Aggiorna editor diff\" per riscrivere il testo."
            )
        )
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        upper = QtWidgets.QWidget()
        upper_layout = QtWidgets.QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(6)

        self._order_label = QtWidgets.QLabel("")
        self._order_label.setObjectName("interactiveDiffOrderLabel")
        self._order_label.setWordWrap(True)
        upper_layout.addWidget(self._order_label)

        self._list_widget = QtWidgets.QListWidget()
        self._list_widget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self._list_widget.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        self._list_widget.setAlternatingRowColors(True)
        self._list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self._list_widget.viewport().setProperty("interactive", True)
        upper_layout.addWidget(self._list_widget, 1)

        splitter.addWidget(upper)

        self._preview = QtWidgets.QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText(
            _("Seleziona un file dall'elenco per vederne il diff completo.")
        )
        self._highlighter = DiffHighlighter(self._preview.document())
        splitter.addWidget(self._preview)
        splitter.setSizes([180, 320])

        buttons = QtWidgets.QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(12)

        self._btn_apply = QtWidgets.QPushButton(_("Aggiorna editor diff"))
        self._btn_apply.clicked.connect(self._apply_reordered_diff)
        buttons.addWidget(self._btn_apply)

        self._btn_reset = QtWidgets.QPushButton(_("Ripristina ordine iniziale"))
        self._btn_reset.clicked.connect(self._reset_order)
        buttons.addWidget(self._btn_reset)

        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self._list_widget.model().rowsMoved.connect(self._on_rows_moved)

        self._update_enabled_state()

    def clear(self) -> None:
        """Reset the widget to an empty state."""

        self._original_entries = []
        self._list_widget.clear()
        self._preview.clear()
        self._order_label.clear()
        self._update_enabled_state()

    def set_patch(self, patch: Iterable[object]) -> None:
        """Populate the widget using a parsed patch set."""

        entries: list[FileDiffEntry] = []
        for patched_file in patch:
            file_label = getattr(patched_file, "path", None) or getattr(
                patched_file, "target_file", None
            ) or getattr(patched_file, "source_file", None) or _("<sconosciuto>")
            diff_text = str(patched_file)
            if not diff_text.endswith("\n"):
                diff_text += "\n"
            additions, deletions = _count_changes(diff_text)
            entries.append(
                FileDiffEntry(
                    file_label=file_label,
                    diff_text=diff_text,
                    additions=additions,
                    deletions=deletions,
                )
            )

        self._original_entries = list(entries)
        self._populate(entries)

    def _populate(self, entries: List[FileDiffEntry]) -> None:
        self._list_widget.clear()
        for entry in entries:
            item = QtWidgets.QListWidgetItem(entry.display_text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry)
            if entry.additions and not entry.deletions:
                item.setBackground(QtGui.QColor("#d1f8d1"))
                item.setForeground(QtGui.QColor("#0e5a0e"))
            elif entry.deletions and not entry.additions:
                item.setBackground(QtGui.QColor("#fcd6d6"))
                item.setForeground(QtGui.QColor("#7a1e1e"))
            elif entry.additions or entry.deletions:
                item.setBackground(QtGui.QColor("#f0f4ff"))
            self._list_widget.addItem(item)

        if entries:
            self._list_widget.setCurrentRow(0)
        self._update_order_label()
        self._update_enabled_state()

    def _update_order_label(self) -> None:
        order_parts: list[str] = []
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            entry: FileDiffEntry | None = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if entry is None:
                continue
            order_parts.append(f"{idx + 1}. {entry.file_label}")
        self._order_label.setText("\n".join(order_parts))

    def _update_enabled_state(self) -> None:
        has_entries = self._list_widget.count() > 0
        self._btn_apply.setEnabled(has_entries)
        self._btn_reset.setEnabled(has_entries)
        self._preview.setEnabled(has_entries)
        self._list_widget.setEnabled(has_entries)

    def _current_entries(self) -> list[FileDiffEntry]:
        result: list[FileDiffEntry] = []
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(entry, FileDiffEntry):
                result.append(entry)
        return result

    def _on_current_item_changed(
        self,
        current: QtWidgets.QListWidgetItem | None,
        previous: QtWidgets.QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self._preview.clear()
            return
        entry = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(entry, FileDiffEntry):
            self._preview.setPlainText(entry.diff_text)

    def _apply_reordered_diff(self) -> None:
        entries = self._current_entries()
        if not entries:
            return
        combined = _join_diff_entries(entries)
        self.diffReordered.emit(combined)

    def _reset_order(self) -> None:
        self._populate(list(self._original_entries))
        self._preview.clear()

    def _on_rows_moved(
        self,
        parent: QtCore.QModelIndex,
        start: int,
        end: int,
        destination: QtCore.QModelIndex,
        row: int,
    ) -> None:
        del parent, start, end, destination, row
        self._update_order_label()


def _count_changes(diff_text: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _join_diff_entries(entries: Iterable[FileDiffEntry]) -> str:
    parts: list[str] = []
    for entry in entries:
        text = entry.diff_text
        if not text.endswith("\n"):
            text += "\n"
        parts.append(text)
    return "".join(parts)
