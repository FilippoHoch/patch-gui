"""Interactive diff viewer with drag-and-drop reordering."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Iterable, List

from PySide6 import QtCore, QtGui, QtWidgets

from .diff_formatting import format_diff_with_line_numbers
from .highlighter import DiffHighlighter
from .interactive_diff_model import (
    FileDiffEntry,
    enrich_entry_with_ai_note,
)
from .localization import gettext as _
from .theme import ThemePalette, theme_manager


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


def _palette_token(palette: ThemePalette, name: str, fallback: str) -> str:
    value = palette.get(name)
    return value if value is not None else fallback


def _build_diff_palette(palette: ThemePalette) -> _DiffPalette:
    accent = palette.color("accent")
    text_primary = palette.color("text_primary")
    text_secondary = palette.color("text_secondary")

    return _DiffPalette(
        background=_palette_token(
            palette, "interactive_background", palette.color("background_window")
        ),
        surface=_palette_token(
            palette, "interactive_surface", palette.color("background_surface")
        ),
        surface_hover=_palette_token(
            palette, "interactive_surface_hover", palette.color("background_surface")
        ),
        surface_pressed=_palette_token(
            palette, "interactive_surface_pressed", palette.color("background_surface")
        ),
        surface_disabled=_palette_token(
            palette, "interactive_surface_disabled", palette.color("background_disabled")
        ),
        border=_palette_token(palette, "interactive_border", palette.color("border")),
        border_subtle=_palette_token(
            palette, "interactive_border_subtle", palette.color("border")
        ),
        text_primary=text_primary,
        text_secondary=text_secondary,
        accent=accent,
        accent_hover=_palette_token(palette, "accent_hover", accent),
        accent_pressed=_palette_token(palette, "accent_pressed", accent),
        accent_disabled_bg=_palette_token(
            palette, "interactive_accent_disabled_bg", accent
        ),
        accent_disabled_fg=_palette_token(
            palette, "interactive_accent_disabled_fg", text_secondary
        ),
        on_accent=_palette_token(
            palette, "interactive_on_accent", palette.color("selection_fg")
        ),
        header_gradient_start=_palette_token(
            palette, "interactive_header_gradient_start", accent
        ),
        header_gradient_end=_palette_token(
            palette, "interactive_header_gradient_end", accent
        ),
        list_background=_palette_token(
            palette, "interactive_list_background", palette.color("background_surface")
        ),
        list_hover_bg=_palette_token(
            palette, "interactive_list_hover_bg", "rgba(61, 125, 202, 0.18)"
        ),
        list_selected_bg=_palette_token(
            palette, "interactive_list_selected_bg", "rgba(61, 125, 202, 0.32)"
        ),
        list_selected_border=_palette_token(
            palette, "interactive_list_selected_border", accent
        ),
        preview_background=_palette_token(
            palette, "interactive_preview_background", palette.color("background_input")
        ),
        preview_border=_palette_token(
            palette, "interactive_preview_border", palette.color("border")
        ),
        preview_disabled_bg=_palette_token(
            palette, "interactive_preview_disabled_bg", palette.color("background_disabled")
        ),
        preview_disabled_fg=_palette_token(
            palette, "interactive_preview_disabled_fg", palette.color("text_disabled")
        ),
        badge_add_bg=_palette_token(
            palette, "interactive_badge_add_bg", "rgba(34, 197, 94, 0.22)"
        ),
        badge_add_fg=_palette_token(
            palette, "interactive_badge_add_fg", text_primary
        ),
        badge_del_bg=_palette_token(
            palette, "interactive_badge_del_bg", "rgba(239, 68, 68, 0.24)"
        ),
        badge_del_fg=_palette_token(
            palette, "interactive_badge_del_fg", text_primary
        ),
        badge_neutral_bg=_palette_token(
            palette, "interactive_badge_neutral_bg", "rgba(148, 163, 184, 0.20)"
        ),
        badge_neutral_fg=_palette_token(
            palette, "interactive_badge_neutral_fg", text_primary
        ),
        order_index_color=_palette_token(
            palette, "interactive_order_index_color", accent
        ),
        order_name_color=_palette_token(
            palette, "interactive_order_name_color", text_primary
        ),
    )


def _header_stylesheet(colors: _DiffPalette) -> str:
    return (
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
            "gradient_start": colors.header_gradient_start,
            "gradient_end": colors.header_gradient_end,
            "border": colors.border,
            "title_color": colors.text_primary,
            "subtitle_color": colors.text_secondary,
            "accent": colors.accent,
        }
    )


def _splitter_stylesheet(colors: _DiffPalette) -> str:
    return (
        """
        QSplitter::handle {
            background-color: %(border_subtle)s;
            margin: 6px 0;
        }
        QSplitter::handle:hover {
            background-color: %(accent)s;
        }
        """
        % {"border_subtle": colors.border_subtle, "accent": colors.accent}
    )


def _order_container_stylesheet(colors: _DiffPalette) -> str:
    return (
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
            "surface": colors.surface,
            "border": colors.border,
            "accent": colors.accent,
            "title": colors.text_primary,
            "index_color": colors.order_index_color,
            "name_color": colors.order_name_color,
            "badge_add_bg": colors.badge_add_bg,
            "badge_add_fg": colors.badge_add_fg,
            "badge_del_bg": colors.badge_del_bg,
            "badge_del_fg": colors.badge_del_fg,
            "badge_neutral_bg": colors.badge_neutral_bg,
            "badge_neutral_fg": colors.badge_neutral_fg,
        }
    )


def _list_stylesheet(colors: _DiffPalette) -> str:
    return (
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
            "background": colors.list_background,
            "border": colors.border,
            "selected": colors.list_selected_bg,
            "selected_border": colors.list_selected_border,
            "hover": colors.list_hover_bg,
        }
    )


def _preview_stylesheet(colors: _DiffPalette) -> str:
    return (
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
            "background": colors.preview_background,
            "text": colors.text_primary,
            "border": colors.preview_border,
            "selection_bg": colors.accent,
            "selection_fg": colors.on_accent,
            "disabled_bg": colors.preview_disabled_bg,
            "disabled_fg": colors.preview_disabled_fg,
            "border_subtle": colors.border_subtle,
        }
    )


def _apply_button_stylesheet(colors: _DiffPalette) -> str:
    return (
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
            "accent": colors.accent,
            "on_accent": colors.on_accent,
            "accent_hover": colors.accent_hover,
            "accent_pressed": colors.accent_pressed,
            "accent_disabled_bg": colors.accent_disabled_bg,
            "accent_disabled_fg": colors.accent_disabled_fg,
        }
    )


def _reset_button_stylesheet(colors: _DiffPalette) -> str:
    return (
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
            "surface": colors.surface,
            "text": colors.text_primary,
            "border": colors.border,
            "hover": colors.surface_hover,
            "accent": colors.accent,
            "pressed": colors.surface_pressed,
            "disabled": colors.surface_disabled,
            "disabled_text": colors.text_secondary,
            "border_subtle": colors.border_subtle,
        }
    )


def _list_item_stylesheet(colors: _DiffPalette) -> str:
    return (
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
            font-style: italic;
            font-size: 11px;
        }
        QLabel#diffListItemNote[selected="true"] {
            color: %(selected_note_color)s;
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
            "selected_note_color": colors.text_primary,
            "badge_neutral_bg": colors.badge_neutral_bg,
            "badge_neutral_fg": colors.badge_neutral_fg,
            "badge_add_bg": colors.badge_add_bg,
            "badge_add_fg": colors.badge_add_fg,
            "badge_del_bg": colors.badge_del_bg,
            "badge_del_fg": colors.badge_del_fg,
        }
    )


def _badge_stylesheet(colors: _DiffPalette) -> str:
    return (
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


class InteractiveDiffWidget(QtWidgets.QWidget):  # type: ignore[misc]
    """Widget that shows diff blocks and allows reordering them interactively."""

    diffReordered = QtCore.Signal(str)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        ai_notes_enabled: bool = False,
    ) -> None:
        super().__init__(parent)
        self._original_entries: list[FileDiffEntry] = []
        self._ai_notes_enabled = ai_notes_enabled
        self._theme_manager = theme_manager()
        self._colors = _build_diff_palette(self._theme_manager.palette)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QtWidgets.QFrame()
        header.setObjectName("interactiveDiffHeader")
        self._header = header
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
        self._splitter = splitter
        layout.addWidget(splitter, 1)

        upper = QtWidgets.QWidget()
        upper_layout = QtWidgets.QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(12)

        order_container = QtWidgets.QFrame()
        order_container.setObjectName("interactiveDiffOrderContainer")
        self._order_container = order_container
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
        self._list_widget.itemSelectionChanged.connect(self._refresh_item_selection)

        self._update_enabled_state()
        self._apply_colors()
        self._theme_manager.palette_changed.connect(self._on_palette_changed)

    def clear(self) -> None:
        """Reset the widget to an empty state."""

        self._original_entries = []
        self._list_widget.clear()
        self._preview.clear()
        self._apply_preview_note(None)
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
            entry = enrich_entry_with_ai_note(entry, enabled=self._ai_notes_enabled)
            entries.append(entry)

        self._original_entries = list(entries)
        self._populate(entries)

    def set_ai_notes_enabled(self, enabled: bool) -> None:
        """Toggle the visibility and retrieval of AI-generated notes."""

        if self._ai_notes_enabled == enabled:
            return
        self._ai_notes_enabled = enabled
        if enabled:
            cache: dict[FileDiffEntry, FileDiffEntry] = {}

            def _resolve(entry: FileDiffEntry) -> FileDiffEntry:
                cached = cache.get(entry)
                if cached is not None:
                    return cached
                enriched = enrich_entry_with_ai_note(entry, enabled=True)
                cache[entry] = enriched
                return enriched

            self._original_entries = [
                _resolve(entry) for entry in self._original_entries
            ]
            for idx in range(self._list_widget.count()):
                item = self._list_widget.item(idx)
                entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(entry, FileDiffEntry):
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, _resolve(entry))
        self._update_ai_note_visibility()

    def _populate(self, entries: List[FileDiffEntry]) -> None:
        self._list_widget.clear()
        for entry in entries:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry)
            widget = _DiffListItemWidget(
                entry,
                self._colors,
                show_ai_note=self._ai_notes_enabled,
            )
            item.setSizeHint(widget.sizeHint())
            self._list_widget.addItem(item)
            self._list_widget.setItemWidget(item, widget)

        if entries:
            self._list_widget.setCurrentRow(0)
        self._refresh_item_selection()
        self._update_order_label()
        self._update_enabled_state()

    def _update_ai_note_visibility(self) -> None:
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
            widget = self._list_widget.itemWidget(item)
            if isinstance(entry, FileDiffEntry) and isinstance(
                widget, _DiffListItemWidget
            ):
                note = entry.ai_note if self._ai_notes_enabled else None
                widget.set_ai_note(note)

        current = self._list_widget.currentItem()
        if current is not None:
            entry = current.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(entry, FileDiffEntry):
                self._apply_preview_note(entry)
                return
        self._apply_preview_note(None)

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
        if not has_entries:
            self._apply_preview_note(None)

    def _apply_colors(self) -> None:
        self._header.setStyleSheet(_header_stylesheet(self._colors))
        self._splitter.setStyleSheet(_splitter_stylesheet(self._colors))
        self._order_container.setStyleSheet(_order_container_stylesheet(self._colors))
        self._list_widget.setStyleSheet(_list_stylesheet(self._colors))
        self._preview.setStyleSheet(_preview_stylesheet(self._colors))
        self._btn_apply.setStyleSheet(_apply_button_stylesheet(self._colors))
        self._btn_reset.setStyleSheet(_reset_button_stylesheet(self._colors))
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            widget = self._list_widget.itemWidget(item)
            if isinstance(widget, _DiffListItemWidget):
                widget.set_colors(self._colors)

    def _on_palette_changed(self, palette: ThemePalette) -> None:
        self._colors = _build_diff_palette(palette)
        self._apply_colors()
        self._update_order_label()

    def _current_entries(self) -> list[FileDiffEntry]:
        result: list[FileDiffEntry] = []
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(entry, FileDiffEntry):
                result.append(entry)
        return result

    def _apply_preview_note(self, entry: FileDiffEntry | None) -> None:
        if entry is not None and self._ai_notes_enabled and entry.ai_note:
            self._preview.setToolTip(entry.ai_note)
        else:
            self._preview.setToolTip("")

    def _on_current_item_changed(
        self,
        current: QtWidgets.QListWidgetItem | None,
        previous: QtWidgets.QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self._preview.clear()
            self._apply_preview_note(None)
            return
        entry = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(entry, FileDiffEntry):
            self._preview.setPlainText(entry.annotated_diff_text)
            self._apply_preview_note(entry)
        else:
            self._apply_preview_note(None)
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
        self._apply_preview_note(None)
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

    def __init__(
        self,
        entry: FileDiffEntry,
        colors: _DiffPalette,
        *,
        show_ai_note: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("diffListItem")
        self.setProperty("selected", False)
        self._colors = colors

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(10)

        path_layout = QtWidgets.QVBoxLayout()
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(2)
        layout.addLayout(path_layout, 1)

        self._path_label = QtWidgets.QLabel(entry.file_label)
        self._path_label.setObjectName("diffListItemPath")
        self._path_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        path_layout.addWidget(self._path_label)

        self._note_label = QtWidgets.QLabel()
        self._note_label.setObjectName("diffListItemNote")
        self._note_label.setWordWrap(True)
        self._note_label.setVisible(False)
        path_layout.addWidget(self._note_label)

        badges_container = QtWidgets.QWidget()
        badges_layout = QtWidgets.QHBoxLayout(badges_container)
        badges_layout.setContentsMargins(0, 0, 0, 0)
        badges_layout.setSpacing(6)
        badges = _create_badge_widgets(entry)
        self._badges = badges
        for badge in badges:
            badges_layout.addWidget(badge)
        layout.addWidget(badges_container, 0, QtCore.Qt.AlignmentFlag.AlignRight)

        self._base_tooltip = entry.display_text
        self.setToolTip(self._base_tooltip)
        self.set_ai_note(entry.ai_note if show_ai_note else None)
        self._apply_colors()

    def setSelected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self._path_label.setProperty("selected", selected)
        self._note_label.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self._path_label.style().unpolish(self._path_label)
        self._path_label.style().polish(self._path_label)
        self._note_label.style().unpolish(self._note_label)
        self._note_label.style().polish(self._note_label)
        self.update()

    def set_colors(self, colors: _DiffPalette) -> None:
        self._colors = colors
        self._apply_colors()

    def _apply_colors(self) -> None:
        self.setStyleSheet(_list_item_stylesheet(self._colors))
        badge_stylesheet = _badge_stylesheet(self._colors)
        for badge in self._badges:
            badge.setStyleSheet(badge_stylesheet)
        self.setSelected(bool(self.property("selected")))

    def set_ai_note(self, note: str | None) -> None:
        if note:
            self._note_label.setText(note)
            self._note_label.setVisible(True)
            self.setToolTip(f"{self._base_tooltip}\n\n{note}")
        else:
            self._note_label.clear()
            self._note_label.setVisible(False)
            self.setToolTip(self._base_tooltip)


def _create_badge_widgets(entry: FileDiffEntry) -> list[QtWidgets.QLabel]:
    badges: list[QtWidgets.QLabel] = []
    if entry.additions:
        badges.append(
            _make_badge(
                _("+{count}").format(count=entry.additions),
                "additions",
            )
        )
    if entry.deletions:
        badges.append(
            _make_badge(
                _("-{count}").format(count=entry.deletions),
                "deletions",
            )
        )
    if not badges:
        badges.append(_make_badge(_("0 modifiche"), "neutral"))
    return badges


def _make_badge(text: str, badge_type: str) -> QtWidgets.QLabel:
    badge = QtWidgets.QLabel(text)
    badge.setObjectName("diffStatBadge")
    badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    badge.setProperty("class", "diffStatBadge")
    badge.setProperty("badgeType", badge_type)
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
