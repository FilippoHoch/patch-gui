"""Interactive diff viewer with drag-and-drop reordering."""

from __future__ import annotations

from dataclasses import dataclass, replace
from html import escape
from typing import Iterable, List

from PySide6 import QtCore, QtGui, QtWidgets

from .highlighter import build_diff_highlight_palette
from .localization import gettext as _
from .diff_formatting import format_diff_with_line_numbers, render_diff_segments
from .interactive_diff_model import (
    FileDiffEntry,
    enrich_entry_with_ai_note,
)
from .split_diff_view import SplitDiffView
from .theme import ThemeSnapshot, theme_manager


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


_HEADER_STYLE_TEMPLATE = """
QFrame#interactiveDiffHeader {{
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 {gradient_start},
        stop: 1 {gradient_end}
    );
    border: 1px solid {border};
    border-radius: 10px;
}}
QLabel#interactiveDiffTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {title_color};
}}
QLabel#interactiveDiffSubtitle {{
    color: {subtitle_color};
}}
QLabel#interactiveDiffSubtitle .highlight {{
    color: {accent};
    font-weight: 600;
}}
"""


_SPLITTER_STYLE_TEMPLATE = """
QSplitter::handle {{
    background-color: {border_subtle};
    margin: 6px;
}}
QSplitter::handle:hover {{
    background-color: {accent};
}}
"""


_ORDER_CONTAINER_TEMPLATE = """
QFrame#interactiveDiffOrderContainer {{
    background-color: {surface};
    border: 1px solid {border};
    border-top: 4px solid {accent};
    border-radius: 10px;
}}
QLabel#interactiveDiffOrderTitle {{
    font-weight: 600;
    color: {title};
}}
QLabel#interactiveDiffOrderLabel {{
    padding: 0px;
    margin: 0px;
}}
QLabel#interactiveDiffOrderLabel .diff-order-entry {{
    margin-bottom: 6px;
    font-size: 12px;
}}
QLabel#interactiveDiffOrderLabel .diff-order-entry:last-child {{
    margin-bottom: 0;
}}
QLabel#interactiveDiffOrderLabel .diff-order-index {{
    font-weight: 600;
    margin-right: 6px;
    color: {index_color};
}}
QLabel#interactiveDiffOrderLabel .diff-order-name {{
    color: {name_color};
}}
QLabel#interactiveDiffOrderLabel .diff-badge {{
    border-radius: 10px;
    padding: 1px 8px;
    font-weight: 600;
    font-size: 11px;
}}
QLabel#interactiveDiffOrderLabel .diff-badge.additions {{
    background-color: {badge_add_bg};
    color: {badge_add_fg};
}}
QLabel#interactiveDiffOrderLabel .diff-badge.deletions {{
    background-color: {badge_del_bg};
    color: {badge_del_fg};
}}
QLabel#interactiveDiffOrderLabel .diff-badge.neutral {{
    background-color: {badge_neutral_bg};
    color: {badge_neutral_fg};
}}
"""


_LIST_WIDGET_TEMPLATE = """
QListWidget {{
    background-color: {background};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 6px 4px;
}}
QListWidget::item {{
    border-radius: 6px;
    margin: 2px 4px;
    padding: 0px;
}}
QListWidget::item:selected {{
    background-color: {selected};
    border: 1px solid {selected_border};
}}
QListWidget::item:hover {{
    background-color: {hover};
}}
"""


_PRIMARY_BUTTON_TEMPLATE = """
QPushButton {{
    background-color: {accent};
    color: {on_accent};
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
    border: none;
}}
QPushButton:hover {{
    background-color: {accent_hover};
}}
QPushButton:pressed {{
    background-color: {accent_pressed};
}}
QPushButton:disabled {{
    background-color: {accent_disabled_bg};
    color: {accent_disabled_fg};
}}
"""


_SECONDARY_BUTTON_TEMPLATE = """
QPushButton {{
    background-color: {surface};
    color: {text};
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
    border: 1px solid {border};
}}
QPushButton:hover {{
    background-color: {hover};
    border-color: {accent};
}}
QPushButton:pressed {{
    background-color: {pressed};
}}
QPushButton:disabled {{
    background-color: {disabled};
    color: {disabled_text};
    border-color: {border_subtle};
}}
"""


_LIST_ITEM_TEMPLATE = """
QFrame#diffListItem {{
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 {gradient_start},
        stop: 1 {gradient_end}
    );
    border: 1px solid {border};
    border-radius: 6px;
    padding: 8px 12px;
}}
QFrame#diffListItem[selected="true"] {{
    border-color: {selected_border};
    background-color: {selected_bg};
}}
QLabel#diffListItemPath {{
    font-weight: 600;
    color: {text};
}}
QLabel#diffListItemPath[selected="true"] {{
    color: {accent};
}}
QLabel#diffListItemNote {{
    color: {note_color};
    font-style: italic;
    font-size: 11px;
}}
QLabel#diffListItemNote[selected="true"] {{
    color: {selected_note_color};
}}
QLabel.diffStatBadge {{
    border-radius: 10px;
    padding: 2px 10px;
    font-weight: 600;
    font-size: 11px;
    background-color: {badge_neutral_bg};
    color: {badge_neutral_fg};
}}
QLabel.diffStatBadge[badgeType="additions"] {{
    background-color: {badge_add_bg};
    color: {badge_add_fg};
}}
QLabel.diffStatBadge[badgeType="deletions"] {{
    background-color: {badge_del_bg};
    color: {badge_del_fg};
}}
QLabel.diffStatBadge[badgeType="neutral"] {{
    background-color: {badge_neutral_bg};
    color: {badge_neutral_fg};
}}
"""


_BADGE_TEMPLATE = """
QLabel#diffStatBadge {{
    border-radius: 10px;
    padding: 2px 10px;
    font-weight: 600;
    font-size: 11px;
    background-color: {neutral_bg};
    color: {neutral_fg};
}}
QLabel#diffStatBadge[badgeType="additions"] {{
    background-color: {add_bg};
    color: {add_fg};
}}
QLabel#diffStatBadge[badgeType="deletions"] {{
    background-color: {del_bg};
    color: {del_fg};
}}
QLabel#diffStatBadge[badgeType="neutral"] {{
    background-color: {neutral_bg};
    color: {neutral_fg};
}}
"""


def _format_styles(template: str, **values: str) -> str:
    return template.format(**values)

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

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        ai_notes_enabled: bool = False,
    ) -> None:
        super().__init__(parent)
        self._original_entries: list[FileDiffEntry] = []
        self._ai_notes_enabled = ai_notes_enabled
        self._colors = _build_diff_palette(self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QtWidgets.QFrame()
        header.setObjectName("interactiveDiffHeader")
        self._header_widget = header
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(6)

        header_row = QtWidgets.QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header_layout.addLayout(header_row)

        title_label = QtWidgets.QLabel(_("Organizza il diff"))
        title_label.setObjectName("interactiveDiffTitle")
        header_row.addWidget(title_label)

        header_row.addStretch(1)

        self._layout_toggle = QtWidgets.QCheckBox(_("Vista impilata"))
        self._layout_toggle.setObjectName("interactiveDiffLayoutToggle")
        self._layout_toggle.setToolTip(
            _("Mostra il diff sotto l'elenco anziché affiancato.")
        )
        self._layout_toggle.toggled.connect(self._update_layout_mode)
        header_row.addWidget(self._layout_toggle)

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

        self._highlight_palette = build_diff_highlight_palette(self.palette())

        self._content_splitter = QtWidgets.QSplitter()
        self._content_splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self._content_splitter.setChildrenCollapsible(False)
        layout.addWidget(self._content_splitter, 1)

        list_panel = QtWidgets.QWidget()
        list_layout = QtWidgets.QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(12)

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

        list_layout.addWidget(order_container)

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
        list_layout.addWidget(self._list_widget, 1)

        self._content_splitter.addWidget(list_panel)

        self._split_view = SplitDiffView(
            highlighter_palette=self._highlight_palette,
        )
        self._split_view.setObjectName("interactiveDiffSplitView")
        self._split_view.hunkToggled.connect(self._on_hunk_toggled)
        self._content_splitter.addWidget(self._split_view)
        self._content_splitter.setSizes([300, 520])

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

        self._theme_listener = theme_manager.add_listener(self._apply_theme)
        self._apply_theme(theme_manager.snapshot)
        self.destroyed.connect(
            lambda: theme_manager.remove_listener(self._apply_theme)
        )

    def _apply_theme(self, snapshot: ThemeSnapshot) -> None:
        qpalette = snapshot.palette or self.palette()
        self._highlight_palette = build_diff_highlight_palette(qpalette)
        self._split_view.set_highlight_palette(self._highlight_palette)
        self._colors = _build_diff_palette(self)

        self._header_widget.setStyleSheet(
            _format_styles(
                _HEADER_STYLE_TEMPLATE,
                gradient_start=self._colors.header_gradient_start,
                gradient_end=self._colors.header_gradient_end,
                border=self._colors.border,
                title_color=self._colors.text_primary,
                subtitle_color=self._colors.text_secondary,
                accent=self._colors.accent,
            )
        )
        self._content_splitter.setStyleSheet(
            _format_styles(
                _SPLITTER_STYLE_TEMPLATE,
                border_subtle=self._colors.border_subtle,
                accent=self._colors.accent,
            )
        )
        self._order_container.setStyleSheet(
            _format_styles(
                _ORDER_CONTAINER_TEMPLATE,
                surface=self._colors.surface,
                border=self._colors.border,
                accent=self._colors.accent,
                title=self._colors.text_primary,
                index_color=self._colors.order_index_color,
                name_color=self._colors.order_name_color,
                badge_add_bg=self._colors.badge_add_bg,
                badge_add_fg=self._colors.badge_add_fg,
                badge_del_bg=self._colors.badge_del_bg,
                badge_del_fg=self._colors.badge_del_fg,
                badge_neutral_bg=self._colors.badge_neutral_bg,
                badge_neutral_fg=self._colors.badge_neutral_fg,
            )
        )
        self._list_widget.setStyleSheet(
            _format_styles(
                _LIST_WIDGET_TEMPLATE,
                background=self._colors.list_background,
                border=self._colors.border,
                selected=self._colors.list_selected_bg,
                selected_border=self._colors.list_selected_border,
                hover=self._colors.list_hover_bg,
            )
        )
        self._btn_apply.setStyleSheet(
            _format_styles(
                _PRIMARY_BUTTON_TEMPLATE,
                accent=self._colors.accent,
                on_accent=self._colors.on_accent,
                accent_hover=self._colors.accent_hover,
                accent_pressed=self._colors.accent_pressed,
                accent_disabled_bg=self._colors.accent_disabled_bg,
                accent_disabled_fg=self._colors.accent_disabled_fg,
            )
        )
        self._btn_reset.setStyleSheet(
            _format_styles(
                _SECONDARY_BUTTON_TEMPLATE,
                surface=self._colors.surface,
                text=self._colors.text_primary,
                border=self._colors.border,
                hover=self._colors.surface_hover,
                accent=self._colors.accent,
                pressed=self._colors.surface_pressed,
                disabled=self._colors.surface_disabled,
                disabled_text=self._colors.text_secondary,
                border_subtle=self._colors.border_subtle,
            )
        )

        current_entries = self._current_entries()
        current_row = self._list_widget.currentRow()
        if current_entries:
            self._populate(current_entries)
            target_row = current_row if 0 <= current_row < len(current_entries) else 0
            self._list_widget.setCurrentRow(target_row)
        else:
            self._populate([])
        self._refresh_item_selection()
        self._update_order_label()

    def clear(self) -> None:
        """Reset the widget to an empty state."""

        self._original_entries = []
        self._list_widget.clear()
        self._split_view.clear()
        self._apply_entry_note(None)
        self._order_label.clear()
        self._update_enabled_state()

    def set_patch(self, patch: Iterable[object]) -> None:
        """Populate the widget using a parsed patch set."""

        self._split_view.clear()
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
            try:
                rendered = render_diff_segments(patched_file)
            except Exception:
                rendered = None
            hunks = rendered.hunks if rendered is not None else ()
            if rendered is not None and hunks:
                annotated_parts = [rendered.annotated_header_text]
                annotated_parts.extend(h.annotated_text for h in hunks)
                annotated_text = "".join(annotated_parts)
                header_text = rendered.header_text
                annotated_header = rendered.annotated_header_text
                hunk_mask: tuple[bool, ...] | None = tuple(True for _ in hunks)
            else:
                annotated_text = format_diff_with_line_numbers(patched_file, diff_text)
                header_text = rendered.header_text if rendered is not None else ""
                annotated_header = (
                    rendered.annotated_header_text if rendered is not None else ""
                )
                hunk_mask = tuple(True for _ in hunks) if hunks else None
            entry = FileDiffEntry(
                file_label=file_label,
                diff_text=diff_text,
                annotated_diff_text=annotated_text,
                additions=additions,
                deletions=deletions,
                header_text=header_text,
                annotated_header_text=annotated_header,
                hunks=hunks,
                hunk_apply_mask=hunk_mask,
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

    def focus_file(self, file_label: str | None) -> bool:
        """Select and focus the entry matching ``file_label`` if present."""

        if not file_label:
            return False
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(entry, FileDiffEntry) and entry.file_label == file_label:
                self._list_widget.setCurrentItem(item)
                self._list_widget.scrollToItem(
                    item, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter
                )
                return True
        return False

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
                self._apply_entry_note(entry)
                return
        self._apply_entry_note(None)

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
        self._split_view.setEnabled(has_entries)
        self._list_widget.setEnabled(has_entries)
        if not has_entries:
            self._split_view.clear()
            self._apply_entry_note(None)

    def _current_entries(self) -> list[FileDiffEntry]:
        result: list[FileDiffEntry] = []
        for idx in range(self._list_widget.count()):
            item = self._list_widget.item(idx)
            entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(entry, FileDiffEntry):
                result.append(entry)
        return result

    def _apply_entry_note(self, entry: FileDiffEntry | None) -> None:
        if entry is not None and self._ai_notes_enabled and entry.ai_note:
            self._split_view.setToolTip(entry.ai_note)
        else:
            self._split_view.setToolTip("")

    def _on_current_item_changed(
        self,
        current: QtWidgets.QListWidgetItem | None,
        previous: QtWidgets.QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self._split_view.set_entry(None)
            self._apply_entry_note(None)
            return
        entry = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(entry, FileDiffEntry):
            self._split_view.set_entry(entry, apply_mask=entry.hunk_apply_mask)
            self._apply_entry_note(entry)
        else:
            self._split_view.set_entry(None)
            self._apply_entry_note(None)
        self._refresh_item_selection()

    def _build_combined_diff(self) -> str | None:
        entries = self._current_entries()
        if not entries:
            return None
        parts: list[str] = []
        for entry in entries:
            if entry.hunks:
                mask_source = entry.hunk_apply_mask
                if mask_source is None:
                    active_mask = [True] * entry.hunk_count
                else:
                    active_mask = list(mask_source)
                    if len(active_mask) < entry.hunk_count:
                        active_mask.extend([True] * (entry.hunk_count - len(active_mask)))
                selected = [
                    hunk
                    for idx, hunk in enumerate(entry.hunks)
                    if idx < len(active_mask) and active_mask[idx]
                ]
                if not selected:
                    continue
                segment_parts: list[str] = []
                if entry.header_text:
                    segment_parts.append(entry.header_text)
                segment_parts.extend(hunk.raw_text for hunk in selected)
                text = "".join(segment_parts)
            else:
                text = entry.diff_text
            if not text.endswith("\n"):
                text += "\n"
            parts.append(text)
        return "".join(parts)

    def _emit_current_diff(self) -> None:
        combined = self._build_combined_diff()
        if combined is None:
            return
        self.diffReordered.emit(combined)

    def _on_hunk_toggled(self, index: int, applied: bool) -> None:
        current_item = self._list_widget.currentItem()
        if current_item is None:
            return
        entry = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(entry, FileDiffEntry):
            return
        total = entry.hunk_count
        if total == 0 or index < 0 or index >= total:
            return
        mask_source = entry.hunk_apply_mask
        if mask_source is None:
            mask = [True] * total
        else:
            mask = list(mask_source)
            if len(mask) < total:
                mask.extend([True] * (total - len(mask)))
        if mask[index] == applied:
            return
        mask[index] = applied
        new_entry = replace(entry, hunk_apply_mask=tuple(mask))
        current_item.setData(QtCore.Qt.ItemDataRole.UserRole, new_entry)
        self._apply_entry_note(new_entry)
        self._emit_current_diff()

    def _update_layout_mode(self, stacked: bool) -> None:
        orientation = (
            QtCore.Qt.Orientation.Vertical
            if stacked
            else QtCore.Qt.Orientation.Horizontal
        )
        if self._content_splitter.orientation() != orientation:
            self._content_splitter.setOrientation(orientation)
        if stacked:
            self._content_splitter.setSizes([260, 360])
        else:
            self._content_splitter.setSizes([300, 520])

    def _apply_reordered_diff(self) -> None:
        combined = self._build_combined_diff()
        if combined is None:
            return
        self.diffReordered.emit(combined)

    def _reset_order(self) -> None:
        self._split_view.set_entry(None)
        self._apply_entry_note(None)
        self._populate(list(self._original_entries))
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
        self.setStyleSheet(
            _format_styles(
                _LIST_ITEM_TEMPLATE,
                gradient_start=colors.header_gradient_start,
                gradient_end=colors.surface,
                border=colors.border,
                selected_border=colors.list_selected_border,
                selected_bg=colors.list_selected_bg,
                text=colors.text_primary,
                accent=colors.accent,
                note_color=colors.text_secondary,
                selected_note_color=colors.text_primary,
                badge_neutral_bg=colors.badge_neutral_bg,
                badge_neutral_fg=colors.badge_neutral_fg,
                badge_add_bg=colors.badge_add_bg,
                badge_add_fg=colors.badge_add_fg,
                badge_del_bg=colors.badge_del_bg,
                badge_del_fg=colors.badge_del_fg,
            )
        )

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
        for badge in _create_badge_widgets(entry, colors):
            badges_layout.addWidget(badge)
        layout.addWidget(badges_container, 0, QtCore.Qt.AlignmentFlag.AlignRight)

        self._base_tooltip = entry.display_text
        self.setToolTip(self._base_tooltip)
        self.set_ai_note(entry.ai_note if show_ai_note else None)

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

    def set_ai_note(self, note: str | None) -> None:
        if note:
            self._note_label.setText(note)
            self._note_label.setVisible(True)
            self.setToolTip(f"{self._base_tooltip}\n\n{note}")
        else:
            self._note_label.clear()
            self._note_label.setVisible(False)
            self.setToolTip(self._base_tooltip)


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
        _format_styles(
            _BADGE_TEMPLATE,
            neutral_bg=colors.badge_neutral_bg,
            neutral_fg=colors.badge_neutral_fg,
            add_bg=colors.badge_add_bg,
            add_fg=colors.badge_add_fg,
            del_bg=colors.badge_del_bg,
            del_fg=colors.badge_del_fg,
        )
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
