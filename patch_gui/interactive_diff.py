"""Interactive diff viewer with drag-and-drop reordering."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Iterable, List

from PySide6 import QtCore, QtGui, QtWidgets

from .highlighter import DiffHighlighter
from .localization import gettext as _
from .diff_formatting import format_diff_with_line_numbers
from .interactive_diff_models import FileDiffEntry, populate_ai_note


@dataclass(frozen=True, slots=True)
class _DiffPalette:
    """Collection of colours tuned for the interactive diff widget."""

    background: str
    surface: str
    surface_hover: str
    surface_pressed: str
    surface_disabled: str
    border: str
    border_subtle: str
    text_primary: str
    text_secondary: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_disabled_bg: str
    accent_disabled_fg: str
    on_accent: str
    header_gradient_start: str
    header_gradient_end: str
    list_background: str
    list_hover_bg: str
    list_selected_bg: str
    list_selected_border: str
    preview_background: str
    preview_border: str
    preview_disabled_bg: str
    preview_disabled_fg: str
    badge_add_bg: str
    badge_add_fg: str
    badge_del_bg: str
    badge_del_fg: str
    badge_neutral_bg: str
    badge_neutral_fg: str
    order_index_color: str
    order_name_color: str


def _colour_name(color: QtGui.QColor, *, with_alpha: bool = False) -> str:
    format_ = (
        QtGui.QColor.NameFormat.HexArgb
        if with_alpha
        else QtGui.QColor.NameFormat.HexRgb
    )
    return str(QtGui.QColor(color).name(format_))


def _build_diff_palette(widget: QtWidgets.QWidget) -> _DiffPalette:
    palette = widget.palette()

    background = palette.color(QtGui.QPalette.ColorRole.Window)
    surface = palette.color(QtGui.QPalette.ColorRole.AlternateBase)
    input_background = palette.color(QtGui.QPalette.ColorRole.Base)
    text_primary = palette.color(QtGui.QPalette.ColorRole.WindowText)
    text_secondary = palette.color(
        QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text
    )
    accent = palette.color(QtGui.QPalette.ColorRole.Highlight)
    on_accent = palette.color(QtGui.QPalette.ColorRole.HighlightedText)

    def lighten(color: QtGui.QColor, amount: int) -> QtGui.QColor:
        return QtGui.QColor(color).lighter(amount)

    def darken(color: QtGui.QColor, amount: int) -> QtGui.QColor:
        return QtGui.QColor(color).darker(amount)

    header_gradient_start = lighten(surface, 110)
    header_gradient_end = darken(surface, 115)
    border = darken(surface, 150)
    border_subtle = darken(surface, 125)
    surface_hover = lighten(surface, 108)
    surface_pressed = darken(surface, 120)
    surface_disabled = darken(surface, 110)
    accent_hover = lighten(accent, 120)
    accent_pressed = darken(accent, 130)
    accent_disabled_bg = QtGui.QColor(accent)
    accent_disabled_bg.setAlpha(140)
    list_hover_bg = QtGui.QColor(accent)
    list_hover_bg.setAlpha(55)
    list_selected_bg = QtGui.QColor(accent)
    list_selected_bg.setAlpha(90)

    preview_border = lighten(border, 130)
    preview_disabled_bg = darken(input_background, 110)

    return _DiffPalette(
        background=_colour_name(background),
        surface=_colour_name(surface),
        surface_hover=_colour_name(surface_hover),
        surface_pressed=_colour_name(surface_pressed),
        surface_disabled=_colour_name(surface_disabled),
        border=_colour_name(border),
        border_subtle=_colour_name(border_subtle),
        text_primary=_colour_name(text_primary),
        text_secondary=_colour_name(text_secondary),
        accent=_colour_name(accent),
        accent_hover=_colour_name(accent_hover),
        accent_pressed=_colour_name(accent_pressed),
        accent_disabled_bg=_colour_name(accent_disabled_bg, with_alpha=True),
        accent_disabled_fg=_colour_name(text_secondary),
        on_accent=_colour_name(on_accent),
        header_gradient_start=_colour_name(header_gradient_start),
        header_gradient_end=_colour_name(header_gradient_end),
        list_background=_colour_name(surface),
        list_hover_bg=_colour_name(list_hover_bg, with_alpha=True),
        list_selected_bg=_colour_name(list_selected_bg, with_alpha=True),
        list_selected_border=_colour_name(accent),
        preview_background=_colour_name(input_background),
        preview_border=_colour_name(preview_border),
        preview_disabled_bg=_colour_name(preview_disabled_bg),
        preview_disabled_fg=_colour_name(text_secondary),
        badge_add_bg="rgba(34, 197, 94, 0.22)",
        badge_add_fg="#86efac",
        badge_del_bg="rgba(239, 68, 68, 0.24)",
        badge_del_fg="#fca5a5",
        badge_neutral_bg="rgba(148, 163, 184, 0.20)",
        badge_neutral_fg=_colour_name(text_primary),
        order_index_color=_colour_name(accent),
        order_name_color=_colour_name(text_primary),
    )


class InteractiveDiffWidget(QtWidgets.QWidget):  # type: ignore[misc]
    """Widget that shows diff blocks and allows reordering them interactively."""

    diffReordered = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._original_entries: list[FileDiffEntry] = []
        self._ai_notes_enabled = False
        self._colors = _build_diff_palette(self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QtWidgets.QFrame()
        header.setObjectName("interactiveDiffHeader")
        header.setStyleSheet(
            """
            QFrame#interactiveDiffHeader {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 %(gradient_start)s,
                    stop: 1 %(gradient_end)s
                );
                border: 1px solid %(border)s;
                border-radius: 10px;
            }
            QLabel#interactiveDiffTitle {
                font-size: 16px;
                font-weight: 700;
                color: %(title_color)s;
            }
            QLabel#interactiveDiffSubtitle {
                color: %(subtitle_color)s;
            }
            QLabel#interactiveDiffSubtitle .highlight {
                color: %(accent)s;
                font-weight: 600;
            }
            """
            % {
                "gradient_start": self._colors.header_gradient_start,
                "gradient_end": self._colors.header_gradient_end,
                "border": self._colors.border,
                "title_color": self._colors.text_primary,
                "subtitle_color": self._colors.text_secondary,
                "accent": self._colors.accent,
            }
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
                '<span class="highlight">"Aggiorna editor diff"</span> '
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
                background-color: %(border_subtle)s;
                margin: 6px 0;
            }
            QSplitter::handle:hover {
                background-color: %(accent)s;
            }
            """
            % {
                "border_subtle": self._colors.border_subtle,
                "accent": self._colors.accent,
            }
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
                background-color: %(surface)s;
                border: 1px solid %(border)s;
                border-top: 4px solid %(accent)s;
                border-radius: 10px;
            }
            QLabel#interactiveDiffOrderTitle {
                font-weight: 600;
                color: %(title)s;
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
                color: %(index_color)s;
            }
            QLabel#interactiveDiffOrderLabel .diff-order-name {
                color: %(name_color)s;
            }
            QLabel#interactiveDiffOrderLabel .diff-badge {
                border-radius: 10px;
                padding: 1px 8px;
                font-weight: 600;
                font-size: 11px;
            }
            QLabel#interactiveDiffOrderLabel .diff-badge.additions {
                background-color: %(badge_add_bg)s;
                color: %(badge_add_fg)s;
            }
            QLabel#interactiveDiffOrderLabel .diff-badge.deletions {
                background-color: %(badge_del_bg)s;
                color: %(badge_del_fg)s;
            }
            QLabel#interactiveDiffOrderLabel .diff-badge.neutral {
                background-color: %(badge_neutral_bg)s;
                color: %(badge_neutral_fg)s;
            }
            """
            % {
                "surface": self._colors.surface,
                "border": self._colors.border,
                "accent": self._colors.accent,
                "title": self._colors.text_primary,
                "index_color": self._colors.order_index_color,
                "name_color": self._colors.order_name_color,
                "badge_add_bg": self._colors.badge_add_bg,
                "badge_add_fg": self._colors.badge_add_fg,
                "badge_del_bg": self._colors.badge_del_bg,
                "badge_del_fg": self._colors.badge_del_fg,
                "badge_neutral_bg": self._colors.badge_neutral_bg,
                "badge_neutral_fg": self._colors.badge_neutral_fg,
            }
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
                background-color: %(background)s;
                border: 1px solid %(border)s;
                border-radius: 10px;
                padding: 6px 4px;
            }
            QListWidget::item {
                border-radius: 6px;
                margin: 2px 4px;
                padding: 0px;
            }
            QListWidget::item:selected {
                background-color: %(selected)s;
                border: 1px solid %(selected_border)s;
            }
            QListWidget::item:hover {
                background-color: %(hover)s;
            }
            """
            % {
                "background": self._colors.list_background,
                "border": self._colors.border,
                "selected": self._colors.list_selected_bg,
                "selected_border": self._colors.list_selected_border,
                "hover": self._colors.list_hover_bg,
            }
        )
        self._list_widget.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._list_widget.setAlternatingRowColors(False)
        self._list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self._list_widget.viewport().setProperty("interactive", True)
        upper_layout.addWidget(self._list_widget, 1)

        splitter.addWidget(upper)

        preview_panel = QtWidgets.QWidget()
        preview_layout = QtWidgets.QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6)

        self._ai_note_label = QtWidgets.QLabel("")
        self._ai_note_label.setObjectName("interactiveDiffAiNote")
        self._ai_note_label.setWordWrap(True)
        self._ai_note_label.setVisible(False)
        self._ai_note_label.setStyleSheet(
            """
            QLabel#interactiveDiffAiNote {
                background-color: %(surface)s;
                border: 1px solid %(border)s;
                border-radius: 8px;
                padding: 6px 8px;
                color: %(text_secondary)s;
                font-style: italic;
            }
            """
            % {
                "surface": self._colors.surface,
                "border": self._colors.border_subtle,
                "text_secondary": self._colors.text_secondary,
            }
        )
        preview_layout.addWidget(self._ai_note_label)

        self._preview = QtWidgets.QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText(
            _("Seleziona un file dall'elenco per vederne il diff completo."),
        )
        self._preview.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: %(background)s;
                color: %(text)s;
                border: 1px solid %(border)s;
                border-radius: 10px;
                selection-background-color: %(selection_bg)s;
                selection-color: %(selection_fg)s;
            }
            QPlainTextEdit[enabled="false"] {
                background-color: %(disabled_bg)s;
                color: %(disabled_fg)s;
                border-color: %(border_subtle)s;
            }
            """
            % {
                "background": self._colors.preview_background,
                "text": self._colors.text_primary,
                "border": self._colors.preview_border,
                "selection_bg": self._colors.accent,
                "selection_fg": self._colors.on_accent,
                "disabled_bg": self._colors.preview_disabled_bg,
                "disabled_fg": self._colors.preview_disabled_fg,
                "border_subtle": self._colors.border_subtle,
            }
        )
        self._highlighter = DiffHighlighter(self._preview.document())
        preview_layout.addWidget(self._preview, 1)
        splitter.addWidget(preview_panel)
        splitter.setSizes([180, 320])

        buttons = QtWidgets.QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(12)

        self._btn_apply = QtWidgets.QPushButton(_("Aggiorna editor diff"))
        self._btn_apply.setStyleSheet(
            """
            QPushButton {
                background-color: %(accent)s;
                color: %(on_accent)s;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
                border: none;
            }
            QPushButton:hover {
                background-color: %(accent_hover)s;
            }
            QPushButton:pressed {
                background-color: %(accent_pressed)s;
            }
            QPushButton:disabled {
                background-color: %(accent_disabled_bg)s;
                color: %(accent_disabled_fg)s;
            }
            """
            % {
                "accent": self._colors.accent,
                "on_accent": self._colors.on_accent,
                "accent_hover": self._colors.accent_hover,
                "accent_pressed": self._colors.accent_pressed,
                "accent_disabled_bg": self._colors.accent_disabled_bg,
                "accent_disabled_fg": self._colors.accent_disabled_fg,
            }
        )
        self._btn_apply.clicked.connect(self._apply_reordered_diff)
        buttons.addWidget(self._btn_apply)

        self._btn_reset = QtWidgets.QPushButton(_("Ripristina ordine iniziale"))
        self._btn_reset.setStyleSheet(
            """
            QPushButton {
                background-color: %(surface)s;
                color: %(text)s;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
                border: 1px solid %(border)s;
            }
            QPushButton:hover {
                background-color: %(hover)s;
                border-color: %(accent)s;
            }
            QPushButton:pressed {
                background-color: %(pressed)s;
            }
            QPushButton:disabled {
                background-color: %(disabled)s;
                color: %(disabled_text)s;
                border-color: %(border_subtle)s;
            }
            """
            % {
                "surface": self._colors.surface,
                "text": self._colors.text_primary,
                "border": self._colors.border,
                "hover": self._colors.surface_hover,
                "accent": self._colors.accent,
                "pressed": self._colors.surface_pressed,
                "disabled": self._colors.surface_disabled,
                "disabled_text": self._colors.text_secondary,
                "border_subtle": self._colors.border_subtle,
            }
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
        self._update_note_display(None)
        self._order_label.clear()
        self._update_enabled_state()

    def set_patch(self, patch: Iterable[object]) -> None:
        """Populate the widget using a parsed patch set."""

        entries: list[FileDiffEntry] = []
        for patched_file in patch:
            file_label = (
                getattr(patched_file, "path", None)
                or getattr(patched_file, "target_file", None)
                or getattr(patched_file, "source_file", None)
                or _("<sconosciuto>")
            )
            diff_text = str(patched_file)
            if not diff_text.endswith("\n"):
                diff_text += "\n"
            additions, deletions = _count_changes(diff_text)
            annotated_text = format_diff_with_line_numbers(patched_file, diff_text)
            entry = FileDiffEntry(
                file_label=file_label,
                diff_text=diff_text,
                annotated_diff_text=annotated_text,
                additions=additions,
                deletions=deletions,
            )
            if self._ai_notes_enabled:
                entry = populate_ai_note(entry)
            entries.append(entry)

        self._original_entries = list(entries)
        self._populate(entries)

    def _populate(self, entries: List[FileDiffEntry]) -> None:
        self._list_widget.clear()
        for entry in entries:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry)
            widget = _DiffListItemWidget(entry, self._colors)
            widget.update_ai_note(entry.ai_note if self._ai_notes_enabled else None)
            item.setSizeHint(widget.sizeHint())
            self._list_widget.addItem(item)
            self._list_widget.setItemWidget(item, widget)

        if entries:
            self._list_widget.setCurrentRow(0)
            self._update_note_display(entries[0])
        else:
            self._update_note_display(None)
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
                    badges=_format_badges(entry, self._colors),
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
            self._update_note_display(None)
            return
        entry = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(entry, FileDiffEntry):
            self._preview.setPlainText(entry.annotated_diff_text)
            self._update_note_display(entry)
        self._refresh_item_selection()

    def _update_note_display(self, entry: FileDiffEntry | None) -> None:
        if not self._ai_notes_enabled or entry is None:
            self._ai_note_label.clear()
            self._ai_note_label.setVisible(False)
            return
        note = entry.ai_note
        if note:
            self._ai_note_label.setText(note)
            self._ai_note_label.setVisible(True)
        else:
            self._ai_note_label.clear()
            self._ai_note_label.setVisible(False)

    def set_ai_notes_enabled(self, enabled: bool) -> None:
        if self._ai_notes_enabled == enabled:
            return
        self._ai_notes_enabled = enabled
        fetch_notes = enabled

        updated_originals: list[FileDiffEntry] = []
        for entry in self._original_entries:
            updated_originals.append(populate_ai_note(entry) if fetch_notes else entry)
        self._original_entries = updated_originals

        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if not isinstance(entry, FileDiffEntry):
                continue
            new_entry = populate_ai_note(entry) if fetch_notes else entry
            if new_entry is not entry:
                item.setData(QtCore.Qt.ItemDataRole.UserRole, new_entry)
            widget = self._list_widget.itemWidget(item)
            if isinstance(widget, _DiffListItemWidget):
                widget.update_ai_note(new_entry.ai_note if enabled else None)

        current_entry = self._current_entry()
        self._update_note_display(current_entry)

    def _current_entry(self) -> FileDiffEntry | None:
        current = self._list_widget.currentItem()
        if current is None:
            return None
        entry = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(entry, FileDiffEntry):
            return entry
        return None

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


class _DiffListItemWidget(QtWidgets.QFrame):  # type: ignore[misc]
    """Custom widget for list items with colourful diff statistics."""

    def __init__(self, entry: FileDiffEntry, colors: _DiffPalette) -> None:
        super().__init__()
        self.setObjectName("diffListItem")
        self.setProperty("selected", False)
        self.setStyleSheet(
            """
            QFrame#diffListItem {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 %(gradient_start)s,
                    stop: 1 %(gradient_end)s
                );
                border: 1px solid %(border)s;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QFrame#diffListItem[selected="true"] {
                border-color: %(selected_border)s;
                background-color: %(selected_bg)s;
            }
            QLabel#diffListItemPath {
                font-weight: 600;
                color: %(text)s;
            }
            QLabel#diffListItemPath[selected="true"] {
                color: %(accent)s;
            }
            QLabel#diffListItemNote {
                color: %(note_color)s;
                font-size: 11px;
                font-style: italic;
            }
            QLabel.diffStatBadge {
                border-radius: 10px;
                padding: 2px 10px;
                font-weight: 600;
                font-size: 11px;
                background-color: %(badge_neutral_bg)s;
                color: %(badge_neutral_fg)s;
            }
            QLabel.diffStatBadge[badgeType="additions"] {
                background-color: %(badge_add_bg)s;
                color: %(badge_add_fg)s;
            }
            QLabel.diffStatBadge[badgeType="deletions"] {
                background-color: %(badge_del_bg)s;
                color: %(badge_del_fg)s;
            }
            QLabel.diffStatBadge[badgeType="neutral"] {
                background-color: %(badge_neutral_bg)s;
                color: %(badge_neutral_fg)s;
            }
            """
            % {
                "gradient_start": colors.header_gradient_start,
                "gradient_end": colors.surface,
                "border": colors.border,
                "selected_border": colors.list_selected_border,
                "selected_bg": colors.list_selected_bg,
                "text": colors.text_primary,
                "accent": colors.accent,
                "note_color": colors.text_secondary,
                "badge_neutral_bg": colors.badge_neutral_bg,
                "badge_neutral_fg": colors.badge_neutral_fg,
                "badge_add_bg": colors.badge_add_bg,
                "badge_add_fg": colors.badge_add_fg,
                "badge_del_bg": colors.badge_del_bg,
                "badge_del_fg": colors.badge_del_fg,
            }
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(10)

        self._path_label = QtWidgets.QLabel(entry.file_label)
        self._path_label.setObjectName("diffListItemPath")
        self._path_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        text_container = QtWidgets.QWidget()
        text_layout = QtWidgets.QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(self._path_label)

        self._note_label = QtWidgets.QLabel("")
        self._note_label.setObjectName("diffListItemNote")
        self._note_label.setWordWrap(True)
        self._note_label.setVisible(False)
        self._note_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        text_layout.addWidget(self._note_label)

        layout.addWidget(text_container, 1)

        badges_container = QtWidgets.QWidget()
        badges_layout = QtWidgets.QHBoxLayout(badges_container)
        badges_layout.setContentsMargins(0, 0, 0, 0)
        badges_layout.setSpacing(6)
        for badge in _create_badge_widgets(entry, colors):
            badges_layout.addWidget(badge)
        layout.addWidget(badges_container, 0, QtCore.Qt.AlignmentFlag.AlignRight)

        self._base_tooltip = entry.display_text
        self._ai_note: str | None = None
        self.update_ai_note(entry.ai_note)

    def setSelected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self._path_label.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self._path_label.style().unpolish(self._path_label)
        self._path_label.style().polish(self._path_label)
        self.update()

    def update_ai_note(self, note: str | None) -> None:
        self._ai_note = note or None
        if self._ai_note:
            self._note_label.setText(self._ai_note)
            self._note_label.setVisible(True)
        else:
            self._note_label.clear()
            self._note_label.setVisible(False)
        tooltip = self._base_tooltip
        if self._ai_note:
            tooltip = f"{tooltip}\n\n{self._ai_note}"
        self.setToolTip(tooltip)


def _create_badge_widgets(
    entry: FileDiffEntry, colors: _DiffPalette
) -> list[QtWidgets.QLabel]:
    badges: list[QtWidgets.QLabel] = []
    if entry.additions:
        badges.append(
            _make_badge(
                _("+{count}").format(count=entry.additions),
                "additions",
                colors,
            )
        )
    if entry.deletions:
        badges.append(
            _make_badge(
                _("-{count}").format(count=entry.deletions),
                "deletions",
                colors,
            )
        )
    if not badges:
        badges.append(_make_badge(_("0 modifiche"), "neutral", colors))
    return badges


def _make_badge(text: str, badge_type: str, colors: _DiffPalette) -> QtWidgets.QLabel:
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
            background-color: %(neutral_bg)s;
            color: %(neutral_fg)s;
        }
        QLabel#diffStatBadge[badgeType="additions"] {
            background-color: %(add_bg)s;
            color: %(add_fg)s;
        }
        QLabel#diffStatBadge[badgeType="deletions"] {
            background-color: %(del_bg)s;
            color: %(del_fg)s;
        }
        QLabel#diffStatBadge[badgeType="neutral"] {
            background-color: %(neutral_bg)s;
            color: %(neutral_fg)s;
        }
        """
        % {
            "neutral_bg": colors.badge_neutral_bg,
            "neutral_fg": colors.badge_neutral_fg,
            "add_bg": colors.badge_add_bg,
            "add_fg": colors.badge_add_fg,
            "del_bg": colors.badge_del_bg,
            "del_fg": colors.badge_del_fg,
        }
    )
    return badge


def _format_badges(entry: FileDiffEntry, colors: _DiffPalette) -> str:
    badges: list[str] = []
    base_style = (
        "border-radius: 10px; padding: 1px 8px; font-weight: 600; font-size: 11px;"
    )
    if entry.additions:
        badges.append(
            '<span class="diff-badge additions" style="{style} background-color: {bg}; '
            'color: {fg};">+{count}</span>'.format(
                style=base_style,
                bg=colors.badge_add_bg,
                fg=colors.badge_add_fg,
                count=entry.additions,
            )
        )
    if entry.deletions:
        badges.append(
            '<span class="diff-badge deletions" style="{style} background-color: {bg}; '
            'color: {fg};">-{count}</span>'.format(
                style=base_style,
                bg=colors.badge_del_bg,
                fg=colors.badge_del_fg,
                count=entry.deletions,
            )
        )
    if not badges:
        badges.append(
            '<span class="diff-badge neutral" style="{style} background-color: {bg}; '
            'color: {fg};">0</span>'.format(
                style=base_style,
                bg=colors.badge_neutral_bg,
                fg=colors.badge_neutral_fg,
            )
        )
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
