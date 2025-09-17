"""GUI application logic for the Patch GUI diff applier."""

from __future__ import annotations

import difflib
import logging
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple, TypeVar, cast

from logging.handlers import RotatingFileHandler

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QDialog, QMainWindow
from unidiff import PatchSet

from .config import AppConfig, load_config, save_config
from .filetypes import inspect_file_type
from .highlighter import DiffHighlighter
from .i18n import install_translators
from .localization import gettext as _
from .logo_widgets import LogoWidget, WordmarkWidget, create_logo_pixmap
from .platform import running_under_wsl
from .theme import apply_modern_theme
from .patcher import (
    ApplySession,
    FileResult,
    HunkDecision,
    HunkView,
    DEFAULT_EXCLUDE_DIRS,
    apply_hunks,
    backup_file,
    build_hunk_view as patcher_build_hunk_view,
    find_file_candidates,
    prepare_backup_dir,
)
from .reporting import write_session_reports
from .utils import (
    APP_NAME,
    BACKUP_DIR,
    decode_bytes,
    display_path,
    display_relative_path,
    normalize_newlines,
    preprocess_patch_text,
    write_text_preserving_encoding,
)


if TYPE_CHECKING:
    from unidiff.patch import PatchedFile

_F = TypeVar("_F", bound=Callable[..., object])

if TYPE_CHECKING:
    # ``PySide6`` exposes these Qt base classes as ``Any`` which prevents mypy
    # from allowing subclassing. Providing explicit subclasses in the
    # ``TYPE_CHECKING`` branch gives the type checker concrete types while the
    # assignments below preserve the runtime behaviour.

    class _QObjectBase(QObject):
        """Concrete ``QObject`` subclass with a stable static type for mypy."""

    class _QDialogBase(QDialog):
        """Concrete ``QDialog`` subclass with a stable static type for mypy."""

    class _QThreadBase(QThread):
        """Concrete ``QThread`` subclass with a stable static type for mypy."""

    class _QMainWindowBase(QMainWindow):
        """Concrete ``QMainWindow`` subclass with a stable static type for mypy."""

else:
    _QObjectBase = QObject
    _QDialogBase = QDialog
    _QThreadBase = QThread
    _QMainWindowBase = QMainWindow


def _qt_slot(
    *types: type[object], name: str | None = None, result: type[object] | None = None
) -> Callable[[_F], _F]:
    """Typed wrapper around :func:`QtCore.Slot` to appease the type checker."""

    if name is None and result is None:
        slot = QtCore.Slot(*types)
    elif result is None:
        slot = QtCore.Slot(*types, name=name)
    elif name is None:
        slot = QtCore.Slot(*types, result=result)
    else:
        slot = QtCore.Slot(*types, name=name, result=result)
    return cast("Callable[[_F], _F]", slot)


_GUI_LOG_LEVEL_CHOICES: tuple[str, ...] = (
    "critical",
    "error",
    "warning",
    "info",
    "debug",
)


LOG_FILE_ENV_VAR: str = "PATCH_GUI_LOG_FILE"
LOG_LEVEL_ENV_VAR: str = "PATCH_GUI_LOG_LEVEL"
LOG_MAX_BYTES_ENV_VAR: str = "PATCH_GUI_LOG_MAX_BYTES"
LOG_BACKUP_COUNT_ENV_VAR: str = "PATCH_GUI_LOG_BACKUP_COUNT"
DEFAULT_LOG_FILE: Path = Path.home() / ".patch_gui.log"
DEFAULT_LOG_MAX_BYTES: int = 0
DEFAULT_LOG_BACKUP_COUNT: int = 0
LOG_TIMESTAMP_FORMAT: str = "%Y-%m-%d %H:%M:%S"


def _resolve_log_level(level: str | int | None) -> int:
    """Convert ``level`` to a ``logging`` level integer."""

    if level is None:
        level = os.getenv(LOG_LEVEL_ENV_VAR, "INFO")

    if isinstance(level, int):
        return level

    if isinstance(level, str):
        candidate = level.strip()
        if not candidate:
            return logging.INFO
        if candidate.isdigit():
            return int(candidate)
        numeric = logging.getLevelName(candidate.upper())
        if isinstance(numeric, int):
            return numeric

    return logging.INFO


def _coerce_non_negative_int(value: int | str | None) -> int | None:
    if value is None:
        return None

    if isinstance(value, int):
        numeric = value
    else:
        candidate = str(value).strip()
        if not candidate:
            return None
        try:
            numeric = int(candidate)
        except ValueError:
            return None

    return numeric if numeric >= 0 else None


def _resolve_rotation_setting(
    value: int | str | None, *, env_var: str, default: int
) -> int:
    direct_value = _coerce_non_negative_int(value)
    if direct_value is not None:
        return direct_value

    env_value = _coerce_non_negative_int(os.getenv(env_var))
    if env_value is not None:
        return env_value

    return default


def configure_logging(
    *,
    level: str | int | None = None,
    log_file: str | Path | None = None,
    max_bytes: int | str | None = None,
    backup_count: int | str | None = None,
) -> Path:
    """Configure the global logging setup with a rotating file handler."""

    resolved_level = _resolve_log_level(level)
    file_path = Path(
        os.getenv(LOG_FILE_ENV_VAR, log_file or DEFAULT_LOG_FILE)
    ).expanduser()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_max_bytes = _resolve_rotation_setting(
        max_bytes, env_var=LOG_MAX_BYTES_ENV_VAR, default=DEFAULT_LOG_MAX_BYTES
    )
    resolved_backup_count = _resolve_rotation_setting(
        backup_count, env_var=LOG_BACKUP_COUNT_ENV_VAR, default=DEFAULT_LOG_BACKUP_COUNT
    )

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt=LOG_TIMESTAMP_FORMAT,
    )

    file_handler = RotatingFileHandler(
        file_path,
        encoding="utf-8",
        maxBytes=resolved_max_bytes,
        backupCount=resolved_backup_count,
    )
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
            handler.close()

    root_logger.addHandler(file_handler)
    return file_path


class _QtLogEmitter(_QObjectBase):
    """Helper ``QObject`` used to forward log messages to the GUI thread."""

    message = QtCore.Signal(str, int)


class GuiLogHandler(logging.Handler):
    """Logging handler that forwards messages to a Qt callback."""

    def __init__(self, callback: Callable[[str, int], None]) -> None:
        super().__init__()
        self._emitter = _QtLogEmitter()
        self._emitter.message.connect(callback)

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - UI feedback
        try:
            message = self.format(record)
        except Exception:  # pragma: no cover - defensive guard for logging issues
            self.handleError(record)
            return
        self._emitter.message.emit(message, record.levelno)


logger = logging.getLogger(__name__)


def _apply_platform_workarounds() -> None:
    """Adjust Qt settings to improve rendering on specific platforms."""

    if not running_under_wsl():
        return

    logger.debug("Rilevata esecuzione in WSL: applicazione workaround High DPI.")

    attribute = getattr(QtCore.Qt, "AA_UseHighDpiPixmaps", None)
    if attribute is None:
        attribute = getattr(
            getattr(QtCore.Qt, "ApplicationAttribute", object),
            "AA_UseHighDpiPixmaps",
            None,
        )
    if attribute is not None:
        QtCore.QCoreApplication.setAttribute(attribute)

    if not os.getenv("QT_SCALE_FACTOR_ROUNDING_POLICY"):
        policy_enum = getattr(QtCore.Qt, "HighDpiScaleFactorRoundingPolicy", None)
        try:
            if policy_enum is not None:
                QtGui.QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
                    policy_enum.PassThrough
                )
        except AttributeError:
            logger.debug(
                "Qt non supporta la configurazione del rounding High DPI; workaround ignorato."
            )


def _parse_exclude_text(text: str) -> tuple[str, ...]:
    if not text:
        return tuple()
    parsed: list[str] = []
    for item in text.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        if normalized not in parsed:
            parsed.append(normalized)
    return tuple(parsed)


class CandidateDialog(_QDialogBase):
    def __init__(
        self,
        parent: QtWidgets.QWidget | None,
        file_text: str,
        candidates: List[Tuple[int, float]],
        hv: HunkView,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Seleziona posizione hunk (ambiguità)")
        self.setModal(True)
        self.resize(1000, 700)
        self.selected_pos: Optional[int] = None

        layout = QtWidgets.QVBoxLayout(self)

        info = QtWidgets.QLabel(
            "Sono state trovate più posizioni plausibili. Seleziona la posizione corretta.\n"
            "Anteprima: a sinistra il testo del file, evidenziata la finestra candidata; a destra il 'prima' del hunk."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)

        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        self.list: QtWidgets.QListWidget = QtWidgets.QListWidget()
        for pos, score in candidates:
            self.list.addItem(f"Linea {pos+1} – similarità {score:.3f}")
        self.list.setCurrentRow(0)
        left_layout.addWidget(self.list)

        self.preview_left: QtWidgets.QPlainTextEdit = QtWidgets.QPlainTextEdit()
        self.preview_left.setReadOnly(True)
        left_layout.addWidget(self.preview_left, 1)

        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.addWidget(QtWidgets.QLabel("Hunk – contenuto atteso (prima):"))
        self.preview_right: QtWidgets.QPlainTextEdit = QtWidgets.QPlainTextEdit(
            "".join(hv.before_lines)
        )
        self.preview_right.setReadOnly(True)
        right_layout.addWidget(self.preview_right, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        layout.addWidget(splitter, 1)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        def on_row_changed() -> None:
            row = self.list.currentRow()
            if row < 0:
                return
            pos, _ = candidates[row]
            file_lines = file_text.splitlines(keepends=True)
            start = max(0, pos - 15)
            end = min(len(file_lines), pos + len(hv.before_lines) + 15)
            snippet = "".join(file_lines[start:end])
            self.preview_left.setPlainText(snippet)

        self.list.currentRowChanged.connect(on_row_changed)
        on_row_changed()

    def accept(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(
                self, "Selezione obbligatoria", "Seleziona una posizione dalla lista."
            )
            return
        text = self.list.currentItem().text()
        m = re.search(r"Linea (\d+)", text)
        if m:
            self.selected_pos = int(m.group(1)) - 1
        super().accept()


class FileChoiceDialog(_QDialogBase):
    def __init__(
        self,
        parent: QtWidgets.QWidget | None,
        title: str,
        choices: List[Path],
        base: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(700, 400)
        self.chosen: Optional[Path] = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            QtWidgets.QLabel(
                "Sono stati trovati più file con lo stesso nome. Seleziona quello corretto:"
            )
        )
        self.list: QtWidgets.QListWidget = QtWidgets.QListWidget()
        for path in choices:
            if base is not None:
                label = display_relative_path(path, base)
            else:
                label = display_path(path)
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, path)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        layout.addWidget(self.list, 1)
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def accept(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            item = self.list.item(row)
        if item is not None:
            data = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(data, Path):
                self.chosen = data
            elif data is not None:
                self.chosen = Path(str(data))
        super().accept()


class SettingsDialog(_QDialogBase):
    def __init__(
        self,
        parent: QtWidgets.QWidget | None,
        *,
        config: AppConfig | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Impostazioni"))
        self.setModal(True)
        self.resize(480, 320)
        self._original_config = config or load_config()
        self.result_config: AppConfig | None = None

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)

        self.threshold_spin = QtWidgets.QDoubleSpinBox()
        self.threshold_spin.setRange(0.5, 1.0)
        self.threshold_spin.setSingleStep(0.01)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setValue(self._original_config.threshold)
        form.addRow(_("Soglia fuzzy"), self.threshold_spin)

        self.exclude_edit = QtWidgets.QLineEdit(
            ", ".join(self._original_config.exclude_dirs)
        )
        self.exclude_edit.setPlaceholderText(
            _("Directory escluse (separate da virgola)")
        )
        form.addRow(_("Directory escluse"), self.exclude_edit)

        self.backup_edit = QtWidgets.QLineEdit(
            str(self._original_config.backup_base)
        )
        self.backup_edit.setPlaceholderText(
            _("Percorso base per i backup")
        )
        backup_layout = QtWidgets.QHBoxLayout()
        backup_layout.setContentsMargins(0, 0, 0, 0)
        backup_layout.addWidget(self.backup_edit, 1)
        self.backup_button = QtWidgets.QPushButton(_("Sfoglia…"))
        self.backup_button.clicked.connect(self._on_choose_backup)
        backup_layout.addWidget(self.backup_button)
        backup_widget = QtWidgets.QWidget()
        backup_widget.setLayout(backup_layout)
        form.addRow(_("Directory backup"), backup_widget)

        self.log_combo = QtWidgets.QComboBox()
        for level in _GUI_LOG_LEVEL_CHOICES:
            self.log_combo.addItem(level.upper(), level)
        current_index = self.log_combo.findData(self._original_config.log_level)
        if current_index >= 0:
            self.log_combo.setCurrentIndex(current_index)
        form.addRow(_("Livello log"), self.log_combo)

        self.dry_run_check = QtWidgets.QCheckBox(
            _("Esegui sempre in dry-run inizialmente")
        )
        self.dry_run_check.setChecked(self._original_config.dry_run_default)
        form.addRow("", self.dry_run_check)

        self.reports_check = QtWidgets.QCheckBox(
            _("Genera report al termine (JSON + testo)")
        )
        self.reports_check.setChecked(self._original_config.write_reports)
        form.addRow("", self.reports_check)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)

    def _on_choose_backup(self) -> None:  # pragma: no cover - user interaction
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            _("Seleziona directory di backup"),
            str(self._original_config.backup_base),
        )
        if directory:
            self.backup_edit.setText(directory)

    def _on_accept(self) -> None:
        self.result_config = self._gather_config()
        self.accept()

    def _gather_config(self) -> AppConfig:
        threshold = float(self.threshold_spin.value())
        excludes = _parse_exclude_text(self.exclude_edit.text())
        backup_text = self.backup_edit.text().strip()
        if backup_text:
            backup_base = Path(backup_text).expanduser()
        else:
            backup_base = self._original_config.backup_base
        log_level_data = self.log_combo.currentData()
        log_level = (
            str(log_level_data)
            if isinstance(log_level_data, str)
            else self._original_config.log_level
        )

        return AppConfig(
            threshold=threshold,
            exclude_dirs=excludes,
            backup_base=backup_base,
            log_level=log_level,
            dry_run_default=self.dry_run_check.isChecked(),
            write_reports=self.reports_check.isChecked(),
        )


class PatchApplyWorker(_QThreadBase):
    progress = QtCore.Signal(str, int)
    finished = QtCore.Signal(object)
    error = QtCore.Signal(str)
    request_file_choice = QtCore.Signal(str, object)
    request_hunk_choice = QtCore.Signal(str, object, object)

    def __init__(self, patch: PatchSet, session: ApplySession) -> None:
        super().__init__()
        self.patch: PatchSet = patch
        self.session: ApplySession = session
        self._file_choice_event: threading.Event = threading.Event()
        self._file_choice_result: Optional[Path] = None
        self._hunk_choice_event: threading.Event = threading.Event()
        self._hunk_choice_result: Optional[int] = None
        self._total_files: int = len(self.patch)
        self._total_hunks: int = sum(len(pf) for pf in self.patch)
        self._total_units: int = sum(max(len(pf), 1) for pf in self.patch)
        self._processed_files: int = 0
        self._processed_hunks: int = 0
        self._processed_units: int = 0

    def _calculate_percent(self) -> int:
        if self._total_units:
            ratio = self._processed_units / self._total_units
        elif self._processed_files:
            ratio = 1.0
        else:
            ratio = 0.0
        percent = int(round(ratio * 100))
        return max(0, min(percent, 100))

    def _emit_progress(self, message: str, *, percent: Optional[int] = None) -> None:
        resolved_percent = self._calculate_percent() if percent is None else percent
        resolved_percent = max(0, min(int(resolved_percent), 100))
        self.progress.emit(message, resolved_percent)

    def provide_file_choice(self, choice: Optional[Path]) -> None:
        self._file_choice_result = choice
        self._file_choice_event.set()

    def provide_hunk_choice(self, choice: Optional[int]) -> None:
        self._hunk_choice_result = choice
        self._hunk_choice_event.set()

    def run(self) -> None:  # pragma: no cover - thread orchestration
        try:
            if not self._total_units:
                self._emit_progress("Nessun file o hunk da applicare.", percent=100)
            for pf in self.patch:
                rel = pf.path or pf.target_file or pf.source_file or ""
                file_result = self.apply_file_patch(pf, rel)
                self.session.results.append(file_result)
                self._processed_files += 1
                hunks_in_file = len(pf)
                self._processed_hunks += hunks_in_file
                self._processed_units += max(hunks_in_file, 1)
                hunks_total = self._total_hunks
                if hunks_total:
                    hunks_msg = f"hunk {self._processed_hunks}/{hunks_total}"
                else:
                    hunks_msg = "hunk 0/0"
                files_total = self._total_files or 0
                message = (
                    f"Applicazione file: {rel} "
                    f"(file {self._processed_files}/{files_total}, {hunks_msg})"
                )
                self._emit_progress(message)
            self._emit_progress("Applicazione diff completata.", percent=100)
            self.finished.emit(self.session)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Errore durante l'applicazione della patch: %s", exc)
            self.error.emit(str(exc))

    def apply_file_patch(self, pf: "PatchedFile", rel_path: str) -> FileResult:
        fr = FileResult(file_path=Path(), relative_to_root=rel_path)
        file_type_info = inspect_file_type(pf)
        fr.file_type = file_type_info.name

        if file_type_info.name == "binary":
            fr.skipped_reason = "Patch binaria non supportata nella GUI"
            return fr

        candidates = find_file_candidates(
            self.session.project_root,
            rel_path,
            exclude_dirs=self.session.exclude_dirs,
        )
        if not candidates:
            fr.skipped_reason = (
                "File non trovato nella root – salto per preferenza utente"
            )
            logger.warning("SKIP: %s non trovato.", rel_path)
            return fr
        if len(candidates) > 1:
            selected = self._wait_for_file_choice(rel_path, candidates)
            if selected is None:
                fr.skipped_reason = (
                    "Ambiguità sul file, operazione annullata dall'utente"
                )
                return fr
            path = selected
        else:
            path = candidates[0]

        fr.file_path = path
        fr.relative_to_root = display_relative_path(path, self.session.project_root)
        fr.hunks_total = len(pf)

        try:
            raw = path.read_bytes()
        except Exception as e:
            fr.skipped_reason = f"Impossibile leggere file: {e}"
            return fr

        content_str, file_encoding, used_fallback = decode_bytes(raw)
        if used_fallback:
            logger.warning(
                "Decodifica del file %s eseguita con fallback UTF-8 (encoding %s); "
                "alcuni caratteri potrebbero essere sostituiti.",
                path,
                file_encoding,
            )
        orig_eol = "\r\n" if "\r\n" in content_str else "\n"
        lines = normalize_newlines(content_str).splitlines(keepends=True)

        if not self.session.dry_run:
            backup_file(self.session.project_root, path, self.session.backup_dir)

        lines, decisions, applied = apply_hunks(
            lines,
            pf,
            threshold=self.session.threshold,
            manual_resolver=self._resolve_hunk_choice,
        )

        fr.hunks_applied = applied
        fr.decisions.extend(decisions)

        if not self.session.dry_run and applied:
            new_text = "".join(lines)
            new_text = new_text.replace("\n", orig_eol)
            write_text_preserving_encoding(path, new_text, file_encoding)

        return fr

    def _wait_for_file_choice(
        self, rel_path: str, candidates: List[Path]
    ) -> Optional[Path]:
        self._file_choice_result = None
        self._file_choice_event.clear()
        self.request_file_choice.emit(rel_path, candidates)
        self._file_choice_event.wait()
        return self._file_choice_result

    def _wait_for_hunk_choice(
        self, hv: HunkView, lines: List[str], candidates: List[Tuple[int, float]]
    ) -> Optional[int]:
        self._hunk_choice_result = None
        self._hunk_choice_event.clear()
        file_text = "".join(lines)
        self.request_hunk_choice.emit(file_text, candidates, hv)
        self._hunk_choice_event.wait()
        return self._hunk_choice_result

    def _resolve_hunk_choice(
        self,
        hv: HunkView,
        lines: List[str],
        candidates: List[Tuple[int, float]],
        decision: HunkDecision,
        reason: str,
    ) -> Optional[int]:
        pos = self._wait_for_hunk_choice(hv, lines, candidates)
        if pos is None:
            decision.strategy = "failed"
            if reason == "context":
                decision.message = "Scelta annullata (solo contesto)"
            else:
                decision.message = "Scelta annullata dall'utente"
        return pos


class MainWindow(_QMainWindowBase):
    def __init__(self, *, app_config: AppConfig | None = None) -> None:
        super().__init__()
        self.app_config: AppConfig = app_config or load_config()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)

        self._window_icon: Optional[QtGui.QIcon] = None
        if not running_under_wsl():
            icon_pixmap = create_logo_pixmap(256)
            self._window_icon = QtGui.QIcon(icon_pixmap)
            self.setWindowIcon(self._window_icon)

        self.project_root: Optional[Path] = None
        self.settings: QtCore.QSettings = QtCore.QSettings("Work", "PatchDiffApplier")
        self.diff_text: str = ""
        self.patch: Optional[PatchSet] = None

        self.threshold: float = self.app_config.threshold
        self.exclude_dirs: tuple[str, ...] = self.app_config.exclude_dirs
        self.reports_enabled: bool = self.app_config.write_reports
        self._qt_log_handler: Optional[GuiLogHandler] = None
        self._current_worker: Optional[PatchApplyWorker] = None

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        settings_menu = self.menuBar().addMenu(_("Impostazioni"))
        self.action_open_settings = settings_menu.addAction(_("Preferenze…"))
        self.action_open_settings.triggered.connect(self.open_settings_dialog)

        banner = QtWidgets.QHBoxLayout()
        banner.setContentsMargins(0, 0, 0, 0)
        banner.setSpacing(12)
        layout.addLayout(banner)

        if running_under_wsl():
            wsl_heading = QtWidgets.QLabel("Patch GUI – Diff Applier")
            font = QtGui.QFont(wsl_heading.font())
            font.setPointSize(20)
            font.setBold(True)
            wsl_heading.setFont(font)
            banner.addWidget(wsl_heading)
            banner.addStretch(1)
        else:
            self.logo_widget = LogoWidget()
            banner.addWidget(self.logo_widget)
            banner.addSpacing(12)

            self.wordmark_widget = WordmarkWidget()
            banner.addWidget(self.wordmark_widget)
            banner.addStretch(1)

        layout.addSpacing(6)

        style = self.style()

        self.toolbar = QtWidgets.QToolBar(_("Azioni"))
        self.toolbar.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.root_edit = QtWidgets.QLineEdit()
        self.root_edit.setPlaceholderText("Root del progetto (seleziona cartella)")
        self.root_edit.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        root_widget_action = QtWidgets.QWidgetAction(self.toolbar)
        root_widget_action.setDefaultWidget(self.root_edit)
        self.toolbar.addAction(root_widget_action)

        self.action_choose_root = QtGui.QAction(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DirOpenIcon),
            _("Scegli root…"),
            self,
        )
        self.action_choose_root.setToolTip(
            _("Seleziona la cartella radice del progetto da analizzare")
        )
        self.action_choose_root.setStatusTip(
            _("Scegli la directory del progetto da utilizzare come root")
        )
        self.action_choose_root.triggered.connect(self.choose_root)
        self.toolbar.addAction(self.action_choose_root)

        self.toolbar.addSeparator()

        self.action_load_file = QtGui.QAction(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogOpenButton),
            _("Apri file diff…"),
            self,
        )
        self.action_load_file.setToolTip(_("Seleziona un file .diff da aprire"))
        self.action_load_file.setStatusTip(_("Carica un file diff dal disco"))
        self.action_load_file.triggered.connect(self.load_diff_file)

        self.action_from_clip = QtGui.QAction(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogYesButton),
            _("Da appunti"),
            self,
        )
        self.action_from_clip.setToolTip(_("Incolla il diff dagli appunti"))
        self.action_from_clip.setStatusTip(
            _("Carica il diff direttamente dagli appunti di sistema")
        )
        self.action_from_clip.triggered.connect(self.load_from_clipboard)

        self.action_from_text = QtGui.QAction(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView),
            _("Da testo"),
            self,
        )
        self.action_from_text.setToolTip(
            _("Analizza il diff inserito nell'editor di testo")
        )
        self.action_from_text.setStatusTip(
            _("Analizza il diff incollato nell'editor interno")
        )
        self.action_from_text.triggered.connect(self.parse_from_textarea)

        self.load_diff_menu = QtWidgets.QMenu(_("Carica diff"), self)
        self.load_diff_menu.addAction(self.action_load_file)
        self.load_diff_menu.addAction(self.action_from_clip)
        self.load_diff_menu.addAction(self.action_from_text)

        self.load_diff_button = QtWidgets.QToolButton()
        self.load_diff_button.setText(_("Carica diff"))
        self.load_diff_button.setIcon(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogStart)
        )
        self.load_diff_button.setToolTip(
            _("Scegli come caricare o analizzare il diff da elaborare")
        )
        self.load_diff_button.setStatusTip(
            _("Apri un menu con le opzioni di caricamento del diff")
        )
        self.load_diff_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.load_diff_button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup
        )
        self.load_diff_button.setMenu(self.load_diff_menu)
        self.load_diff_button.setDefaultAction(self.action_load_file)
        load_diff_widget_action = QtWidgets.QWidgetAction(self.toolbar)
        load_diff_widget_action.setDefaultWidget(self.load_diff_button)
        self.toolbar.addAction(load_diff_widget_action)

        self.action_analyze = QtGui.QAction(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay),
            _("Analizza diff"),
            self,
        )
        self.action_analyze.setToolTip(
            _("Analizza il diff attualmente caricato o incollato")
        )
        self.action_analyze.setStatusTip(
            _("Avvia l'analisi del diff selezionato")
        )
        self.action_analyze.triggered.connect(self.analyze_diff)
        self.toolbar.addAction(self.action_analyze)

        second = QtWidgets.QHBoxLayout()
        layout.addLayout(second)
        self.chk_dry = QtWidgets.QCheckBox("Dry-run / anteprima")
        second.addWidget(self.chk_dry)

        second.addSpacing(20)
        second.addWidget(QtWidgets.QLabel("Soglia fuzzy"))
        self.spin_thresh = QtWidgets.QDoubleSpinBox()
        self.spin_thresh.setRange(0.5, 1.0)
        self.spin_thresh.setSingleStep(0.01)
        self.spin_thresh.setDecimals(2)
        self.spin_thresh.setValue(self.threshold)
        second.addWidget(self.spin_thresh)

        second.addSpacing(20)
        second.addWidget(QtWidgets.QLabel("Ignora directory"))
        self.exclude_edit = QtWidgets.QLineEdit()
        self.exclude_edit.setPlaceholderText("es. .git,.venv,node_modules")
        self.exclude_edit.setToolTip(
            "Elenco di directory da ignorare (relative alla root), separate da virgola."
        )
        second.addWidget(self.exclude_edit, 1)
        second.addStretch(1)

        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["File / Hunk", "Stato"])
        left_layout.addWidget(self.tree, 1)

        self.btn_apply = QtWidgets.QPushButton("Applica patch")
        self.btn_apply.clicked.connect(self.apply_patch)

        self.btn_restore = QtWidgets.QPushButton("Ripristina da backup…")
        self.btn_restore.clicked.connect(self.restore_from_backup)

        left_btns = QtWidgets.QHBoxLayout()
        left_btns.addWidget(self.btn_apply)
        left_btns.addWidget(self.btn_restore)
        left_layout.addLayout(left_btns)

        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        self.diff_tabs = QtWidgets.QTabWidget()

        self.text_diff = QtWidgets.QPlainTextEdit()
        self.text_diff.setPlaceholderText(
            "Incolla qui il diff se non stai aprendo un file…"
        )
        self._diff_highlighter = DiffHighlighter(self.text_diff.document())
        self.diff_tabs.addTab(self.text_diff, _("Editor diff"))

        self.preview_view = QtWidgets.QPlainTextEdit()
        self.preview_view.setReadOnly(True)
        self._preview_highlighter = DiffHighlighter(self.preview_view.document())
        self.diff_tabs.addTab(self.preview_view, _("Anteprima"))

        right_layout.addWidget(self.diff_tabs, 1)

        right_layout.addWidget(QtWidgets.QLabel("Log:"))
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        right_layout.addWidget(self.log, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([400, 800])

        self.tree.itemSelectionChanged.connect(self._update_preview_from_selection)

        self._apply_config_to_widgets()
        self._setup_gui_logging()

        status_bar = self.statusBar()
        status_bar.showMessage("Pronto")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
        status_bar.addPermanentWidget(self.progress_bar)

        self.restore_last_project_root()
        save_config(self.app_config)

    def _setup_gui_logging(self) -> None:
        handler = GuiLogHandler(self._handle_log_message)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.setLevel(logging.NOTSET)
        logging.getLogger().addHandler(handler)
        self._qt_log_handler = handler

    @_qt_slot(str, int)
    def _handle_log_message(
        self, message: str, level: int
    ) -> None:  # pragma: no cover - UI feedback
        self.log.appendPlainText(message)
        lines = [line for line in message.strip().splitlines() if line]
        if lines:
            self.statusBar().showMessage(lines[0][:100])

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        worker = self._current_worker
        if worker is not None and worker.isRunning():
            QtWidgets.QMessageBox.information(
                self,
                "Operazione in corso",
                "Attendi il completamento dell'applicazione della patch prima di chiudere.",
            )
            event.ignore()
            return
        self._persist_config()
        if self._qt_log_handler is not None:
            logging.getLogger().removeHandler(self._qt_log_handler)
            self._qt_log_handler.close()
            self._qt_log_handler = None
        super().closeEvent(event)

    def _apply_config_to_widgets(self) -> None:
        self.threshold = float(self.app_config.threshold)
        self.exclude_dirs = tuple(self.app_config.exclude_dirs)
        self.reports_enabled = bool(self.app_config.write_reports)
        self.spin_thresh.setValue(self.threshold)
        excludes_text = ", ".join(self.exclude_dirs) if self.exclude_dirs else ""
        self.exclude_edit.setText(excludes_text)
        self.chk_dry.setChecked(self.app_config.dry_run_default)

    def _create_settings_dialog(self) -> SettingsDialog:
        return SettingsDialog(self, config=self.app_config)

    def open_settings_dialog(self) -> None:
        dialog = self._create_settings_dialog()
        result = dialog.exec()
        if result != QtWidgets.QDialog.DialogCode.Accepted:
            return
        if dialog.result_config is None:
            return
        self.app_config = dialog.result_config
        configure_logging(level=self.app_config.log_level)
        self._apply_config_to_widgets()
        save_config(self.app_config)
        self.statusBar().showMessage(_("Impostazioni salvate"), 5000)

    def set_project_root(self, path: Path, persist: bool = True) -> bool:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            QtWidgets.QMessageBox.warning(
                self, "Root non valida", "La cartella selezionata non esiste."
            )
            return False
        self.project_root = resolved
        self.root_edit.setText(str(resolved))
        if persist:
            self.settings.setValue("last_project_root", str(resolved))
            self.settings.sync()
        return True

    def restore_last_project_root(self) -> None:
        raw_value = self.settings.value("last_project_root", type=str)
        if not isinstance(raw_value, str) or not raw_value:
            return
        path = Path(raw_value).expanduser()
        if path.exists() and path.is_dir():
            self.set_project_root(path, persist=False)
        else:
            self.settings.remove("last_project_root")
            self.settings.sync()

    def _current_exclude_dirs(self) -> tuple[str, ...]:
        text = self.exclude_edit.text() if hasattr(self, "exclude_edit") else ""
        return _parse_exclude_text(text)

    def _persist_config(self) -> None:
        self.app_config.threshold = float(self.spin_thresh.value())
        self.app_config.exclude_dirs = self._current_exclude_dirs()
        root_logger = logging.getLogger()
        level_name = logging.getLevelName(root_logger.level)
        if isinstance(level_name, str):
            self.app_config.log_level = level_name.lower()
        self.app_config.dry_run_default = self.chk_dry.isChecked()
        self.app_config.write_reports = self.reports_enabled
        self.threshold = self.app_config.threshold
        self.exclude_dirs = self.app_config.exclude_dirs
        self.reports_enabled = self.app_config.write_reports
        save_config(self.app_config)

    def choose_root(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Seleziona root del progetto"
        )
        if d:
            self.set_project_root(Path(d))

    def load_diff_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Apri file .diff",
            filter="Diff files (*.diff *.patch *.txt);;Tutti (*.*)",
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            self.diff_text = f.read()
        self.text_diff.setPlainText(self.diff_text)
        logger.info("Caricato diff da file: %s", path)

    def load_from_clipboard(self) -> None:
        cb = QtGui.QGuiApplication.clipboard()
        text = cb.text()
        if not text:
            QtWidgets.QMessageBox.information(
                self, "Appunti vuoti", "La clipboard non contiene testo."
            )
            return
        self.diff_text = text
        self.text_diff.setPlainText(self.diff_text)
        logger.info("Diff caricato dagli appunti.")

    def parse_from_textarea(self) -> None:
        self.diff_text = self.text_diff.toPlainText()
        if not self.diff_text.strip():
            QtWidgets.QMessageBox.warning(
                self, "Nessun testo", "Inserisci del testo diff nella textarea."
            )
            return
        logger.info("Testo diff pronto per analisi.")

    def analyze_diff(self) -> None:
        if not self.project_root:
            QtWidgets.QMessageBox.warning(
                self, "Root mancante", "Seleziona la root del progetto."
            )
            return
        self.diff_text = self.text_diff.toPlainText() or self.diff_text
        if not self.diff_text.strip():
            QtWidgets.QMessageBox.warning(
                self, "Diff mancante", "Carica o incolla un diff prima di analizzare."
            )
            return
        self.threshold = float(self.spin_thresh.value())

        preprocessed = preprocess_patch_text(self.diff_text)
        try:
            patch = PatchSet(preprocessed.splitlines(True))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Errore parsing diff", str(e))
            return
        self.patch = patch

        self.tree.clear()
        self.preview_view.clear()
        for pf in patch:
            rel = pf.path or pf.target_file or pf.source_file or "<sconosciuto>"
            node = QtWidgets.QTreeWidgetItem([rel, ""])
            node.setData(0, QtCore.Qt.ItemDataRole.UserRole, rel)
            node.setData(0, QtCore.Qt.ItemDataRole.UserRole + 1, [])
            self.tree.addTopLevelItem(node)
            for h in pf:
                hv = patcher_build_hunk_view(h)
                child = QtWidgets.QTreeWidgetItem([hv.header, ""])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, hv)
                node.addChild(child)
                file_hunks = list(
                    node.data(0, QtCore.Qt.ItemDataRole.UserRole + 1) or []
                )
                file_hunks.append(hv)
                node.setData(0, QtCore.Qt.ItemDataRole.UserRole + 1, file_hunks)
        self.tree.expandAll()
        self._update_preview_from_selection()
        logger.info("Analisi completata. File nel diff: %s", len(self.patch))

    @_qt_slot()
    def _update_preview_from_selection(self) -> None:
        selected = self.tree.selectedItems()
        if not selected:
            self.preview_view.clear()
            self.statusBar().showMessage(_("Nessuna selezione per l'anteprima"), 5000)
            return

        preview_parts: list[str] = []
        labels: list[str] = []

        for item in selected:
            label, text = self._compose_preview_for_item(item)
            if text:
                preview_parts.append(text)
                labels.append(label)

        if not preview_parts:
            self.preview_view.clear()
            self.statusBar().showMessage(
                _("Nessuna anteprima disponibile per la selezione corrente"), 5000
            )
            return

        combined = "\n\n".join(part.rstrip() for part in preview_parts)
        self.preview_view.setPlainText(combined)
        summary = ", ".join(labels)
        logger.info("Anteprima aggiornata: %s", summary)
        self.statusBar().showMessage(
            _("Anteprima aggiornata: {summary}").format(summary=summary), 5000
        )

    def _compose_preview_for_item(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> tuple[str, str]:
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(data, HunkView):
            return item.text(0), self._format_hunk_for_preview(data)

        hunks = item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)
        if isinstance(hunks, list) and hunks:
            formatted = [
                self._format_hunk_for_preview(hv)
                for hv in hunks
                if isinstance(hv, HunkView)
            ]
            if formatted:
                header = _("File: {name}").format(name=item.text(0))
                return item.text(0), f"{header}\n\n" + "\n\n".join(formatted)
        return item.text(0), ""

    def _format_hunk_for_preview(self, hv: HunkView) -> str:
        diff_lines = []
        for line in difflib.ndiff(hv.before_lines, hv.after_lines):
            if line.startswith("?"):
                continue
            diff_lines.append(line)
        if not diff_lines:
            return hv.header
        header = f"{hv.header}\n"
        return header + "".join(diff_lines)

    def _set_busy(self, busy: bool) -> None:
        actions = [
            self.action_choose_root,
            self.action_load_file,
            self.action_from_clip,
            self.action_from_text,
            self.action_analyze,
        ]
        for action in actions:
            action.setEnabled(not busy)

        widgets = [
            self.load_diff_button,
            self.btn_apply,
            self.btn_restore,
        ]
        for widget in widgets:
            widget.setEnabled(not busy)
        self.chk_dry.setEnabled(not busy)
        self.spin_thresh.setEnabled(not busy)
        self.text_diff.setReadOnly(busy)

    def apply_patch(self) -> None:
        if self._current_worker is not None and self._current_worker.isRunning():
            QtWidgets.QMessageBox.information(
                self,
                "Operazione in corso",
                "È già in corso un'applicazione di patch. Attendi il completamento.",
            )
            return
        if not self.patch:
            QtWidgets.QMessageBox.warning(
                self,
                "Analizza prima",
                "Esegui 'Analizza diff' prima di applicare.",
            )
            return
        if not self.project_root:
            QtWidgets.QMessageBox.warning(
                self,
                "Root mancante",
                "Seleziona la root del progetto.",
            )
            return
        dry = self.chk_dry.isChecked()
        thr = float(self.spin_thresh.value())
        excludes = self._current_exclude_dirs()
        self.exclude_dirs = excludes
        self._persist_config()
        started_at = time.time()
        backup_dir = prepare_backup_dir(
            self.project_root,
            dry_run=dry,
            backup_base=self.app_config.backup_base,
            started_at=started_at,
        )
        session = ApplySession(
            project_root=self.project_root,
            backup_dir=backup_dir,
            dry_run=dry,
            threshold=thr,
            exclude_dirs=excludes,
            started_at=started_at,
        )
        worker = PatchApplyWorker(self.patch, session)
        worker.progress.connect(self._on_worker_progress)
        worker.request_file_choice.connect(self._on_worker_request_file_choice)
        worker.request_hunk_choice.connect(self._on_worker_request_hunk_choice)
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._current_worker = worker
        self._set_busy(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setToolTip("")
        self.statusBar().showMessage("Applicazione diff in corso…")
        worker.start()

    @_qt_slot(str, int)
    def _on_worker_progress(
        self, message: str, percent: int
    ) -> None:  # pragma: no cover - UI feedback
        if not message:
            return
        self.log.appendPlainText(message)
        self.statusBar().showMessage(message[:100])
        clamped = max(0, min(int(percent), 100))
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(clamped)
        self.progress_bar.setToolTip(message)

    @_qt_slot(object)
    def _on_worker_finished(
        self, session: ApplySession
    ) -> None:  # pragma: no cover - UI feedback
        self._current_worker = None
        write_session_reports(
            session,
            report_json=None,
            report_txt=None,
            enable_reports=self.app_config.write_reports,
        )
        logger.info("\n=== RISULTATO ===\n%s", session.to_txt())
        self._set_busy(False)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.progress_bar.setToolTip("")
        if self.app_config.write_reports:
            completion_message = _(
                "Operazione terminata. Vedi log e report nella cartella di backup."
            )
        else:
            completion_message = _(
                "Operazione terminata. Report disabilitati nelle impostazioni."
            )
        QtWidgets.QMessageBox.information(
            self,
            "Completato",
            completion_message,
        )
        self.statusBar().showMessage(_("Operazione completata"))

    @_qt_slot(str)
    def _on_worker_error(self, message: str) -> None:  # pragma: no cover - UI feedback
        logger.error("Errore durante l'applicazione della patch: %s", message)
        self._set_busy(False)
        self._current_worker = None
        self.progress_bar.setVisible(False)
        self.progress_bar.setToolTip("")
        QtWidgets.QMessageBox.critical(self, "Errore", message)
        self.statusBar().showMessage("Errore durante l'applicazione della patch")

    @_qt_slot(str, object)
    def _on_worker_request_file_choice(
        self, rel_path: str, candidates: List[Path]
    ) -> None:  # pragma: no cover - UI feedback
        worker = self._current_worker
        if worker is None:
            return
        dlg = FileChoiceDialog(
            self,
            f"Seleziona file per {rel_path}",
            candidates,
            base=self.project_root,
        )
        choice: Optional[Path] = None
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.chosen:
            choice = dlg.chosen
        worker.provide_file_choice(choice)

    @_qt_slot(str, object, object)
    def _on_worker_request_hunk_choice(
        self, file_text: str, candidates: List[Tuple[int, float]], hv: HunkView
    ) -> None:  # pragma: no cover - UI feedback
        worker = self._current_worker
        if worker is None:
            return
        dlg = CandidateDialog(self, file_text, candidates, hv)
        if (
            dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted
            and dlg.selected_pos is not None
        ):
            worker.provide_hunk_choice(dlg.selected_pos)
        else:
            worker.provide_hunk_choice(None)

    def apply_file_patch(
        self, pf: "PatchedFile", rel_path: str, session: ApplySession
    ) -> FileResult:
        fr = FileResult(file_path=Path(), relative_to_root=rel_path)

        assert self.project_root is not None
        candidates = find_file_candidates(
            self.project_root,
            rel_path,
            exclude_dirs=session.exclude_dirs,
        )
        if not candidates:
            fr.skipped_reason = (
                "File non trovato nella root – salto per preferenza utente"
            )
            logger.warning("SKIP: %s non trovato.", rel_path)
            return fr
        if len(candidates) > 1:
            dlg = FileChoiceDialog(
                self,
                f"Seleziona file per {rel_path}",
                candidates,
                base=self.project_root,
            )
            if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted or not dlg.chosen:
                fr.skipped_reason = (
                    "Ambiguità sul file, operazione annullata dall'utente"
                )
                return fr
            path = dlg.chosen
        else:
            path = candidates[0]

        fr.file_path = path
        fr.relative_to_root = display_relative_path(path, self.project_root)
        fr.hunks_total = len(pf)

        try:
            raw = path.read_bytes()
        except Exception as e:
            fr.skipped_reason = f"Impossibile leggere file: {e}"
            return fr

        content_str, file_encoding, used_fallback = decode_bytes(raw)
        if used_fallback:
            logger.warning(
                "Decodifica del file %s eseguita con fallback UTF-8 (encoding %s); "
                "alcuni caratteri potrebbero essere sostituiti.",
                path,
                file_encoding,
            )
        orig_eol = "\r\n" if "\r\n" in content_str else "\n"
        lines = normalize_newlines(content_str).splitlines(keepends=True)

        if not session.dry_run:
            backup_file(self.project_root, path, session.backup_dir)

        lines, decisions, applied = apply_hunks(
            lines,
            pf,
            threshold=session.threshold,
            manual_resolver=self._dialog_hunk_choice,
        )

        fr.hunks_applied = applied
        fr.decisions.extend(decisions)

        if not session.dry_run and applied:
            new_text = "".join(lines)
            new_text = new_text.replace("\n", orig_eol)
            write_text_preserving_encoding(path, new_text, file_encoding)

        return fr

    def _dialog_hunk_choice(
        self,
        hv: HunkView,
        lines: List[str],
        candidates: List[Tuple[int, float]],
        decision: HunkDecision,
        reason: str,
    ) -> Optional[int]:
        file_text = "".join(lines)
        dlg = CandidateDialog(self, file_text, candidates, hv)
        if (
            dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted
            and dlg.selected_pos is not None
        ):
            return dlg.selected_pos
        decision.strategy = "failed"
        if reason == "context":
            decision.message = "Scelta annullata (solo contesto)"
        else:
            decision.message = "Scelta annullata dall'utente"
        return None

    def restore_from_backup(self) -> None:
        if not self.project_root:
            QtWidgets.QMessageBox.warning(
                self, "Root mancante", "Seleziona la root del progetto."
            )
            return
        base = self.project_root / BACKUP_DIR
        if not base.exists():
            QtWidgets.QMessageBox.information(
                self, "Nessun backup", "Cartella backup non trovata."
            )
            return
        stamps = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
        if not stamps:
            QtWidgets.QMessageBox.information(
                self, "Nessun backup", "Nessuna sessione di backup trovata."
            )
            return
        items = [str(p.name) for p in stamps]
        item, ok = QtWidgets.QInputDialog.getItem(
            self, "Seleziona backup", "Sessione:", items, 0, False
        )
        if not ok or not item:
            return
        chosen = base / item
        if (
            QtWidgets.QMessageBox.question(
                self,
                "Conferma ripristino",
                f"Ripristinare i file dalla sessione {item}?\n\nI file correnti saranno sovrascritti.",
            )
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
            return
        for src in chosen.rglob("*"):
            if src.is_file():
                dest = self.project_root / src.relative_to(chosen)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        QtWidgets.QMessageBox.information(
            self, "Ripristino completato", f"Backup {item} ripristinato."
        )


def main() -> None:
    app_config = load_config()
    configure_logging(level=app_config.log_level)
    _apply_platform_workarounds()
    app = QtWidgets.QApplication(sys.argv)
    apply_modern_theme(app)
    app.setApplicationName(APP_NAME)
    translators = install_translators(app)
    setattr(app, "_installed_translators", translators)
    w = MainWindow(app_config=app_config)
    w.show()
    sys.exit(app.exec())


__all__ = [
    "CandidateDialog",
    "FileChoiceDialog",
    "SettingsDialog",
    "GuiLogHandler",
    "MainWindow",
    "PatchApplyWorker",
    "configure_logging",
    "main",
]
