"""Interactive diff viewer with drag-and-drop reordering."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Iterable, List

from PySide6 import QtCore, QtWidgets

from .highlighter import DiffHighlighter
from .localization import gettext as _
from .diff_formatting import format_diff_with_line_numbers


@dataclass(frozen=True, slots=True)
class FileDiffEntry:
    """Store information about a file diff block."""

    file_label: str
    diff_text: str
    annotated_diff_text: str
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

        header = QtWidgets.QFrame()
        header.setObjectName("interactiveDiffHeader")
        header.setStyleSheet(
            """
            QFrame#interactiveDiffHeader {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #e0f2fe,
                    stop: 1 #f1f5f9
                );
                border: 1px solid #bae6fd;
                border-radius: 10px;
            }
            QLabel#interactiveDiffTitle {
                font-size: 16px;
                font-weight: 700;
                color: #0f172a;
            }
            QLabel#interactiveDiffSubtitle {
                color: #1e3a8a;
            }
            QLabel#interactiveDiffSubtitle .highlight {
                color: #0ea5e9;
                font-weight: 600;
            }
            """
        )
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(6)

        title_label = QtWidgets.QLabel(_("Organizza il diff"))
        title_label.setObjectName("interactiveDiffTitle")
        header_layout.addWidget(title_label)

        self._info_label = QtWidgets.QLabel(
            _(
                "Trascina i file nell'elenco sottostante per definire l'ordine "
                "di applicazione della patch. Quando sei soddisfatto, premi "
                "<span class=\"highlight\">\"Aggiorna editor diff\"</span> "
                "per riscrivere il testo completo."
            )
        )
        self._info_label.setObjectName("interactiveDiffSubtitle")
        self._info_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._info_label.setWordWrap(True)
        header_layout.addWidget(self._info_label)

        layout.addWidget(header)

        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Orientation.Vertical)
        splitter.setStyleSheet(
            """
            QSplitter::handle {
                background-color: #bae6fd;
                margin: 6px 0;
            }
            QSplitter::handle:hover {
                background-color: #38bdf8;
            }
            """
        )
        layout.addWidget(splitter, 1)

        upper = QtWidgets.QWidget()
        upper_layout = QtWidgets.QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(12)

        order_container = QtWidgets.QFrame()
        order_container.setObjectName("interactiveDiffOrderContainer")
        order_container.setStyleSheet(
            """
            QFrame#interactiveDiffOrderContainer {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-top: 4px solid #38bdf8;
                border-radius: 10px;
            }
            QLabel#interactiveDiffOrderTitle {
                font-weight: 600;
                color: #0f172a;
            }
            QLabel#interactiveDiffOrderLabel {
                padding: 0px;
                margin: 0px;
            }
            QLabel#interactiveDiffOrderLabel .diff-order-entry {
                margin-bottom: 6px;
                font-size: 12px;
            }
            QLabel#interactiveDiffOrderLabel .diff-order-entry:last-child {
                margin-bottom: 0;
            }
            QLabel#interactiveDiffOrderLabel .diff-order-index {
                font-weight: 600;
                margin-right: 6px;
                color: #1d4ed8;
            }
            QLabel#interactiveDiffOrderLabel .diff-order-name {
                color: #0f172a;
            }
            QLabel#interactiveDiffOrderLabel .diff-badge {
                border-radius: 10px;
                padding: 1px 8px;
                font-weight: 600;
                font-size: 11px;
            }
            QLabel#interactiveDiffOrderLabel .diff-badge.additions {
                background-color: #dcfce7;
                color: #166534;
            }
            QLabel#interactiveDiffOrderLabel .diff-badge.deletions {
                background-color: #fee2e2;
                color: #b91c1c;
            }
            QLabel#interactiveDiffOrderLabel .diff-badge.neutral {
                background-color: #e2e8f0;
                color: #0f172a;
            }
            """
        )
        order_layout = QtWidgets.QVBoxLayout(order_container)
        order_layout.setContentsMargins(16, 14, 16, 14)
        order_layout.setSpacing(4)

        order_title = QtWidgets.QLabel(_("Sequenza dei file"))
        order_title.setObjectName("interactiveDiffOrderTitle")
        order_layout.addWidget(order_title)

        self._order_label = QtWidgets.QLabel("")
        self._order_label.setObjectName("interactiveDiffOrderLabel")
        self._order_label.setWordWrap(True)
        self._order_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        order_layout.addWidget(self._order_label)

        upper_layout.addWidget(order_container)

        self._list_widget = QtWidgets.QListWidget()
        self._list_widget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self._list_widget.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        self._list_widget.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self._list_widget.setStyleSheet(
            """
            QListWidget {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 6px 4px;
            }
            QListWidget::item {
                border-radius: 6px;
                margin: 2px 4px;
                padding: 0px;
            }
            QListWidget::item:selected {
                background-color: #dbeafe;
            }
            QListWidget::item:hover {
                background-color: #e0f2fe;
            }
            """
        )
        self._list_widget.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._list_widget.setAlternatingRowColors(False)
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
        self._preview.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #f8fafc;
                color: #0f172a;
                border: 1px solid #bae6fd;
                border-radius: 10px;
                selection-background-color: #38bdf8;
                selection-color: #0f172a;
            }
            QPlainTextEdit[enabled="false"] {
                background-color: #f1f5f9;
                color: #475569;
                border-color: #cbd5f5;
            }
            """
        )
        self._highlighter = DiffHighlighter(self._preview.document())
        splitter.addWidget(self._preview)
        splitter.setSizes([180, 320])

        buttons = QtWidgets.QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(12)

        self._btn_apply = QtWidgets.QPushButton(_("Aggiorna editor diff"))
        self._btn_apply.setStyleSheet(
            """
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            QPushButton:disabled {
                background-color: #bfdbfe;
                color: #1e3a8a;
            }
            """
        )
        self._btn_apply.clicked.connect(self._apply_reordered_diff)
        buttons.addWidget(self._btn_apply)

        self._btn_reset = QtWidgets.QPushButton(_("Ripristina ordine iniziale"))
        self._btn_reset.setStyleSheet(
            """
            QPushButton {
                background-color: #e2e8f0;
                color: #0f172a;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #cbd5f5;
            }
            QPushButton:pressed {
                background-color: #94a3b8;
            }
            QPushButton:disabled {
                background-color: #e2e8f0;
                color: #94a3b8;
            }
            """
        )
        self._btn_reset.clicked.connect(self._reset_order)
        buttons.addWidget(self._btn_reset)

        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self._list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self._list_widget.itemSelectionChanged.connect(self._refresh_item_selection)

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
            annotated_text = format_diff_with_line_numbers(patched_file, diff_text)
            entries.append(
                FileDiffEntry(
                    file_label=file_label,
                    diff_text=diff_text,
                    annotated_diff_text=annotated_text,
                    additions=additions,
                    deletions=deletions,
                )
            )

        self._original_entries = list(entries)
        self._populate(entries)

    def _populate(self, entries: List[FileDiffEntry]) -> None:
        self._list_widget.clear()
        for entry in entries:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry)
            widget = _DiffListItemWidget(entry)
            item.setSizeHint(widget.sizeHint())
            self._list_widget.addItem(item)
            self._list_widget.setItemWidget(item, widget)

        if entries:
            self._list_widget.setCurrentRow(0)
        self._refresh_item_selection()
        self._update_order_label()
        self._update_enabled_state()

    def _update_order_label(self) -> None:
        order_parts: list[str] = []
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            entry: FileDiffEntry | None = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if entry is None:
                continue
            order_parts.append(
                """
                <div class="diff-order-entry">
                    <span class="diff-order-index">{index}.</span>
                    <span class="diff-order-name">{name}</span>
                    {badges}
                </div>
                """.format(
                    index=idx + 1,
                    name=escape(entry.file_label),
                    badges=_format_badges(entry),
                )
            )
        self._order_label.setText("".join(order_parts))

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
            self._preview.setPlainText(entry.annotated_diff_text)
        self._refresh_item_selection()

    def _apply_reordered_diff(self) -> None:
        entries = self._current_entries()
        if not entries:
            return
        combined = _join_diff_entries(entries)
        self.diffReordered.emit(combined)

    def _reset_order(self) -> None:
        self._populate(list(self._original_entries))
        self._preview.clear()
        self._refresh_item_selection()

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
        self._refresh_item_selection()

    def _refresh_item_selection(self) -> None:
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            widget = self._list_widget.itemWidget(item)
            if isinstance(widget, _DiffListItemWidget):
                widget.setSelected(item.isSelected())
                widget.updateGeometry()


class _DiffListItemWidget(QtWidgets.QFrame):
    """Custom widget for list items with colourful diff statistics."""

    def __init__(self, entry: FileDiffEntry) -> None:
        super().__init__()
        self.setObjectName("diffListItem")
        self.setProperty("selected", False)
        self.setStyleSheet(
            """
            QFrame#diffListItem {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #ffffff,
                    stop: 1 #f8fafc
                );
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QFrame#diffListItem[selected="true"] {
                border-color: #2563eb;
                background-color: #eff6ff;
            }
            QLabel#diffListItemPath {
                font-weight: 600;
                color: #0f172a;
            }
            QLabel#diffListItemPath[selected="true"] {
                color: #1e3a8a;
            }
            QLabel.diffStatBadge {
                border-radius: 10px;
                padding: 2px 10px;
                font-weight: 600;
                font-size: 11px;
            }
            QLabel.diffStatBadge[badgeType="additions"] {
                background-color: #bbf7d0;
                color: #166534;
            }
            QLabel.diffStatBadge[badgeType="deletions"] {
                background-color: #fecaca;
                color: #991b1b;
            }
            QLabel.diffStatBadge[badgeType="neutral"] {
                background-color: #e2e8f0;
                color: #0f172a;
            }
            """
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(10)

        self._path_label = QtWidgets.QLabel(entry.file_label)
        self._path_label.setObjectName("diffListItemPath")
        self._path_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._path_label, 1)

        badges_container = QtWidgets.QWidget()
        badges_layout = QtWidgets.QHBoxLayout(badges_container)
        badges_layout.setContentsMargins(0, 0, 0, 0)
        badges_layout.setSpacing(6)
        for badge in _create_badge_widgets(entry):
            badges_layout.addWidget(badge)
        layout.addWidget(badges_container, 0, QtCore.Qt.AlignmentFlag.AlignRight)

        self.setToolTip(entry.display_text)

    def setSelected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self._path_label.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self._path_label.style().unpolish(self._path_label)
        self._path_label.style().polish(self._path_label)
        self.update()


def _create_badge_widgets(entry: FileDiffEntry) -> list[QtWidgets.QLabel]:
    badges: list[QtWidgets.QLabel] = []
    if entry.additions:
        badges.append(_make_badge(_("+{count}").format(count=entry.additions), "additions"))
    if entry.deletions:
        badges.append(_make_badge(_("-{count}").format(count=entry.deletions), "deletions"))
    if not badges:
        badges.append(_make_badge(_("0 modifiche"), "neutral"))
    return badges


def _make_badge(text: str, badge_type: str) -> QtWidgets.QLabel:
    badge = QtWidgets.QLabel(text)
    badge.setObjectName("diffStatBadge")
    badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    badge.setProperty("class", "diffStatBadge")
    badge.setProperty("badgeType", badge_type)
    badge.setStyleSheet(
        """
        QLabel#diffStatBadge {
            border-radius: 10px;
            padding: 2px 10px;
            font-weight: 600;
            font-size: 11px;
            background-color: #e2e8f0;
            color: #1e293b;
        }
        QLabel#diffStatBadge[badgeType="additions"] {
            background-color: #bbf7d0;
            color: #166534;
        }
        QLabel#diffStatBadge[badgeType="deletions"] {
            background-color: #fecaca;
            color: #991b1b;
        }
        QLabel#diffStatBadge[badgeType="neutral"] {
            background-color: #e0e7ff;
            color: #312e81;
        }
        """
    )
    return badge


def _format_badges(entry: FileDiffEntry) -> str:
    badges: list[str] = []
    if entry.additions:
        badges.append(
            '<span class="diff-badge additions">+{count}</span>'.format(
                count=entry.additions
            )
        )
    if entry.deletions:
        badges.append(
            '<span class="diff-badge deletions">-{count}</span>'.format(
                count=entry.deletions
            )
        )
    if not badges:
        badges.append('<span class="diff-badge neutral">0</span>')
    return "".join(badges)


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

