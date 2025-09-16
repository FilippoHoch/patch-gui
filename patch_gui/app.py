"""GUI application logic for the Patch GUI diff applier."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from unidiff.patch import PatchedFile

from PySide6 import QtCore, QtGui, QtWidgets
from unidiff import PatchSet

from .i18n import install_translators
from .logo_widgets import LogoWidget, WordmarkWidget, create_logo_pixmap
from .patcher import (
    ApplySession,
    FileResult,
    HunkDecision,
    HunkView,
    apply_hunk_at_position,
    build_hunk_view,
    find_candidates,
)
from .utils import (
    APP_NAME,
    BACKUP_DIR,
    REPORT_JSON,
    REPORT_TXT,
    decode_bytes,
    normalize_newlines,
    preprocess_patch_text,
    write_text_preserving_encoding,
)


LOG_FILE_ENV_VAR = "PATCH_GUI_LOG_FILE"
LOG_LEVEL_ENV_VAR = "PATCH_GUI_LOG_LEVEL"
DEFAULT_LOG_FILE = Path.home() / ".patch_gui.log"
LOG_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


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


def configure_logging(*, level: str | int | None = None, log_file: str | Path | None = None) -> Path:
    """Configure the global logging setup with a file handler."""

    resolved_level = _resolve_log_level(level)
    file_path = Path(os.getenv(LOG_FILE_ENV_VAR, log_file or DEFAULT_LOG_FILE)).expanduser()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt=LOG_TIMESTAMP_FORMAT,
    )

    file_handler = logging.FileHandler(file_path, encoding="utf-8")
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


class _QtLogEmitter(QtCore.QObject):
    """Helper ``QObject`` used to forward log messages to the GUI thread."""

    message = QtCore.Signal(str, int)


class GuiLogHandler(logging.Handler):
    """Logging handler that forwards messages to a Qt callback."""

    def __init__(self, callback: Callable[[str, int], None]):
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


class CandidateDialog(QtWidgets.QDialog):
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
        self.list = QtWidgets.QListWidget()
        for pos, score in candidates:
            self.list.addItem(f"Linea {pos+1} – similarità {score:.3f}")
        self.list.setCurrentRow(0)
        left_layout.addWidget(self.list)

        self.preview_left = QtWidgets.QPlainTextEdit()
        self.preview_left.setReadOnly(True)
        left_layout.addWidget(self.preview_left, 1)

        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.addWidget(QtWidgets.QLabel("Hunk – contenuto atteso (prima):"))
        self.preview_right = QtWidgets.QPlainTextEdit("".join(hv.before_lines))
        self.preview_right.setReadOnly(True)
        right_layout.addWidget(self.preview_right, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        layout.addWidget(splitter, 1)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        def on_row_changed(row: int) -> None:
            if row < 0:
                return
            pos, _ = candidates[row]
            file_lines = file_text.splitlines(keepends=True)
            start = max(0, pos - 15)
            end = min(len(file_lines), pos + len(hv.before_lines) + 15)
            snippet = "".join(file_lines[start:end])
            self.preview_left.setPlainText(snippet)

        self.list.currentRowChanged.connect(on_row_changed)
        on_row_changed(self.list.currentRow())

    def accept(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Selezione obbligatoria", "Seleziona una posizione dalla lista.")
            return
        current = self.list.currentItem()
        if current is None:
            QtWidgets.QMessageBox.warning(self, "Selezione obbligatoria", "Seleziona una posizione dalla lista.")
            return
        text = current.text()
        match = re.search(r"Linea (\d+)", text)
        if match:
            self.selected_pos = int(match.group(1)) - 1
        super().accept()


class FileChoiceDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None, title: str, choices: List[Path]) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(700, 400)
        self.chosen: Optional[Path] = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Sono stati trovati più file con lo stesso nome. Seleziona quello corretto:"))
        self.list = QtWidgets.QListWidget()
        for p in choices:
            self.list.addItem(str(p))
        self.list.setCurrentRow(0)
        layout.addWidget(self.list, 1)
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def accept(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            item = self.list.item(row)
            if item is not None:
                self.chosen = Path(item.text())
        super().accept()


class PatchApplyWorker(QtCore.QThread):
    progress = QtCore.Signal(str)
    finished = QtCore.Signal(object)
    error = QtCore.Signal(str)
    request_file_choice = QtCore.Signal(str, object)
    request_hunk_choice = QtCore.Signal(str, object, object)

    def __init__(self, patch: PatchSet, session: ApplySession) -> None:
        super().__init__()
        self.patch = patch
        self.session = session
        self._file_choice_event = threading.Event()
        self._file_choice_result: Optional[Path] = None
        self._hunk_choice_event = threading.Event()
        self._hunk_choice_result: Optional[int] = None

    def provide_file_choice(self, choice: Optional[Path]) -> None:
        self._file_choice_result = choice
        self._file_choice_event.set()

    def provide_hunk_choice(self, choice: Optional[int]) -> None:
        self._hunk_choice_result = choice
        self._hunk_choice_event.set()

    def run(self) -> None:  # pragma: no cover - thread orchestration
        try:
            for pf in self.patch:
                rel = pf.path or pf.target_file or pf.source_file or ""
                self.progress.emit(f"Applicazione file: {rel}")
                file_result = self.apply_file_patch(pf, rel)
                self.session.results.append(file_result)
            self.progress.emit("Applicazione diff completata.")
            self.finished.emit(self.session)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Errore durante l'applicazione della patch: %s", exc)
            self.error.emit(str(exc))

    def apply_file_patch(self, pf: PatchedFile, rel_path: str) -> FileResult:
        fr = FileResult(file_path=Path(), relative_to_root=rel_path)

        candidates = self.find_files_in_project(rel_path)
        if not candidates:
            fr.skipped_reason = "File non trovato nella root – salto per preferenza utente"
            logger.warning("SKIP: %s non trovato.", rel_path)
            return fr
        if len(candidates) > 1:
            selected = self._wait_for_file_choice(rel_path, candidates)
            if selected is None:
                fr.skipped_reason = "Ambiguità sul file, operazione annullata dall'utente"
                return fr
            path = selected
        else:
            path = candidates[0]

        fr.file_path = path
        fr.relative_to_root = str(path.relative_to(self.session.project_root))
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
            self.backup_file(path)

        for h in pf:
            hv = build_hunk_view(h)
            decision = HunkDecision(hunk_header=hv.header, strategy="")

            cand = find_candidates(lines, hv.before_lines, threshold=1.0)
            if cand:
                pos = cand[0][0]
                if not self.session.dry_run:
                    lines = apply_hunk_at_position(lines, hv, pos)
                decision.strategy = "exact"
                decision.selected_pos = pos
                decision.similarity = 1.0
                fr.hunks_applied += 1
                fr.decisions.append(decision)
                continue

            cand = find_candidates(lines, hv.before_lines, threshold=self.session.threshold)
            if len(cand) == 1:
                pos, score = cand[0]
                if not self.session.dry_run:
                    lines = apply_hunk_at_position(lines, hv, pos)
                decision.strategy = "fuzzy"
                decision.selected_pos = pos
                decision.similarity = score
                fr.hunks_applied += 1
                fr.decisions.append(decision)
                continue
            elif len(cand) > 1:
                decision.strategy = "manual"
                decision.candidates = cand
                selected_pos = self._wait_for_hunk_choice(hv, lines, cand)
                if selected_pos is not None:
                    if not self.session.dry_run:
                        lines = apply_hunk_at_position(lines, hv, selected_pos)
                    decision.selected_pos = selected_pos
                    chosen_score = next((s for p, s in cand if p == selected_pos), None)
                    decision.similarity = chosen_score
                    fr.hunks_applied += 1
                else:
                    decision.strategy = "failed"
                    decision.message = "Scelta annullata dall'utente"
                fr.decisions.append(decision)
                continue

            before_ctx = [l for l in hv.before_lines if not l.startswith(("+", "-"))]
            cand = find_candidates(lines, before_ctx, threshold=self.session.threshold)
            if cand:
                decision.strategy = "manual"
                decision.candidates = cand
                selected_pos = self._wait_for_hunk_choice(hv, lines, cand)
                if selected_pos is not None:
                    if not self.session.dry_run:
                        lines = apply_hunk_at_position(lines, hv, selected_pos)
                    decision.selected_pos = selected_pos
                    chosen_score = next((s for p, s in cand if p == selected_pos), None)
                    decision.similarity = chosen_score
                    fr.hunks_applied += 1
                else:
                    decision.strategy = "failed"
                    decision.message = "Scelta annullata (solo contesto)"
                fr.decisions.append(decision)
                continue

            decision.strategy = "failed"
            decision.message = "Nessun candidato trovato sopra la soglia"
            fr.decisions.append(decision)

        if not self.session.dry_run:
            new_text = "".join(lines)
            new_text = new_text.replace("\n", orig_eol)
            write_text_preserving_encoding(path, new_text, file_encoding)

        return fr

    def _wait_for_file_choice(self, rel_path: str, candidates: List[Path]) -> Optional[Path]:
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

    def find_files_in_project(self, rel_path: str) -> List[Path]:
        rel_path = rel_path.strip()
        if rel_path.startswith("a/") or rel_path.startswith("b/"):
            rel_path = rel_path[2:]
        exact = self.session.project_root / rel_path
        if exact.exists():
            return [exact]
        name = Path(rel_path).name
        return [p for p in self.session.project_root.rglob(name) if p.is_file()]

    def backup_file(self, path: Path) -> None:
        rel = path.relative_to(self.session.project_root)
        dst = self.session.backup_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)

        icon_pixmap = create_logo_pixmap(256)
        self._window_icon = QtGui.QIcon(icon_pixmap)
        self.setWindowIcon(self._window_icon)

        self.project_root: Optional[Path] = None
        self.settings = QtCore.QSettings("Work", "PatchDiffApplier")
        self.diff_text: str = ""
        self.patch: Optional[PatchSet] = None

        self.threshold = 0.85
        self._qt_log_handler: Optional[GuiLogHandler] = None
        self._current_worker: Optional[PatchApplyWorker] = None

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        banner = QtWidgets.QHBoxLayout()
        banner.setContentsMargins(0, 0, 0, 0)
        banner.setSpacing(12)
        layout.addLayout(banner)

        self.logo_widget = LogoWidget()
        banner.addWidget(self.logo_widget)
        banner.addSpacing(12)

        self.wordmark_widget = WordmarkWidget()
        banner.addWidget(self.wordmark_widget)
        banner.addStretch(1)

        layout.addSpacing(6)

        top = QtWidgets.QHBoxLayout()
        layout.addLayout(top)

        self.root_edit = QtWidgets.QLineEdit()
        self.root_edit.setPlaceholderText("Root del progetto (seleziona cartella)")
        self.btn_root = QtWidgets.QPushButton("Scegli root…")
        self.btn_root.clicked.connect(self.choose_root)

        self.btn_load_file = QtWidgets.QPushButton("Apri .diff…")
        self.btn_load_file.clicked.connect(self.load_diff_file)

        self.btn_from_clip = QtWidgets.QPushButton("Incolla da appunti")
        self.btn_from_clip.clicked.connect(self.load_from_clipboard)

        self.btn_from_text = QtWidgets.QPushButton("Analizza testo diff")
        self.btn_from_text.clicked.connect(self.parse_from_textarea)

        self.btn_analyze = QtWidgets.QPushButton("Analizza diff")
        self.btn_analyze.clicked.connect(self.analyze_diff)

        top.addWidget(self.root_edit, 1)
        top.addWidget(self.btn_root)
        top.addSpacing(20)
        top.addWidget(self.btn_load_file)
        top.addWidget(self.btn_from_clip)
        top.addWidget(self.btn_from_text)
        top.addWidget(self.btn_analyze)

        second = QtWidgets.QHBoxLayout()
        layout.addLayout(second)
        self.chk_dry = QtWidgets.QCheckBox("Dry-run / anteprima")
        self.chk_dry.setChecked(True)
        second.addWidget(self.chk_dry)

        second.addSpacing(20)
        second.addWidget(QtWidgets.QLabel("Soglia fuzzy"))
        self.spin_thresh = QtWidgets.QDoubleSpinBox()
        self.spin_thresh.setRange(0.5, 1.0)
        self.spin_thresh.setSingleStep(0.01)
        self.spin_thresh.setDecimals(2)
        self.spin_thresh.setValue(self.threshold)
        second.addWidget(self.spin_thresh)
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
        right_layout.addWidget(QtWidgets.QLabel("Incolla/edita diff (opzionale):"))
        self.text_diff = QtWidgets.QPlainTextEdit()
        self.text_diff.setPlaceholderText("Incolla qui il diff se non stai aprendo un file…")
        right_layout.addWidget(self.text_diff, 1)

        right_layout.addWidget(QtWidgets.QLabel("Log:"))
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        right_layout.addWidget(self.log, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([400, 800])

        self._setup_gui_logging()

        self.statusBar().showMessage("Pronto")

        self.restore_last_project_root()

    def _setup_gui_logging(self) -> None:
        handler = GuiLogHandler(self._handle_log_message)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.setLevel(logging.NOTSET)
        logging.getLogger().addHandler(handler)
        self._qt_log_handler = handler

    @QtCore.Slot(str, int)
    def _handle_log_message(self, message: str, level: int) -> None:  # pragma: no cover - UI feedback
        self.log.appendPlainText(message)
        lines = [line for line in message.strip().splitlines() if line]
        if lines:
            self.statusBar().showMessage(lines[0][:100])

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._qt_log_handler is not None:
            logging.getLogger().removeHandler(self._qt_log_handler)
            self._qt_log_handler.close()
            self._qt_log_handler = None
        super().closeEvent(event)

    def set_project_root(self, path: Path, persist: bool = True) -> bool:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            QtWidgets.QMessageBox.warning(self, "Root non valida", "La cartella selezionata non esiste.")
            return False
        self.project_root = resolved
        self.root_edit.setText(str(resolved))
        if persist:
            self.settings.setValue("last_project_root", str(resolved))
            self.settings.sync()
        return True

    def restore_last_project_root(self) -> None:
        last_root_obj = self.settings.value("last_project_root", type=str)
        if not isinstance(last_root_obj, str) or not last_root_obj:
            return
        path = Path(last_root_obj).expanduser()
        if path.exists() and path.is_dir():
            self.set_project_root(path, persist=False)
        else:
            self.settings.remove("last_project_root")
            self.settings.sync()

    def choose_root(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Seleziona root del progetto")
        if directory:
            self.set_project_root(Path(directory))

    def load_diff_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Apri file .diff", filter="Diff files (*.diff *.patch *.txt);;Tutti (*.*)"
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
            QtWidgets.QMessageBox.information(self, "Appunti vuoti", "La clipboard non contiene testo.")
            return
        self.diff_text = text
        self.text_diff.setPlainText(self.diff_text)
        logger.info("Diff caricato dagli appunti.")

    def parse_from_textarea(self) -> None:
        self.diff_text = self.text_diff.toPlainText()
        if not self.diff_text.strip():
            QtWidgets.QMessageBox.warning(self, "Nessun testo", "Inserisci del testo diff nella textarea.")
            return
        logger.info("Testo diff pronto per analisi.")

    def analyze_diff(self) -> None:
        project_root = self.project_root
        if project_root is None:
            QtWidgets.QMessageBox.warning(self, "Root mancante", "Seleziona la root del progetto.")
            return
        self.diff_text = self.text_diff.toPlainText() or self.diff_text
        if not self.diff_text.strip():
            QtWidgets.QMessageBox.warning(self, "Diff mancante", "Carica o incolla un diff prima di analizzare.")
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
        for pf in patch:
            rel = pf.path or pf.target_file or pf.source_file or "<sconosciuto>"
            node = QtWidgets.QTreeWidgetItem([rel, ""])
            node.setData(0, QtCore.Qt.ItemDataRole.UserRole, rel)
            self.tree.addTopLevelItem(node)
            for h in pf:
                hv = build_hunk_view(h)
                child = QtWidgets.QTreeWidgetItem([hv.header, ""])
                node.addChild(child)
        self.tree.expandAll()
        logger.info("Analisi completata. File nel diff: %s", len(patch))

    def _set_busy(self, busy: bool) -> None:
        controls = [
            self.btn_root,
            self.btn_load_file,
            self.btn_from_clip,
            self.btn_from_text,
            self.btn_analyze,
            self.btn_apply,
            self.btn_restore,
        ]
        for widget in controls:
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
        patch = self.patch
        if patch is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Analizza prima",
                "Esegui 'Analizza diff' prima di applicare.",
            )
            return
        project_root = self.project_root
        if project_root is None:
            QtWidgets.QMessageBox.warning(
                self,
                "Root mancante",
                "Seleziona la root del progetto.",
            )
            return
        dry = self.chk_dry.isChecked()
        thr = float(self.spin_thresh.value())
        session = ApplySession(
            project_root=project_root,
            backup_dir=self.ensure_backup_dir(),
            dry_run=dry,
            threshold=thr,
            started_at=time.time(),
        )
        worker = PatchApplyWorker(patch, session)
        worker.progress.connect(self._on_worker_progress)
        worker.request_file_choice.connect(self._on_worker_request_file_choice)
        worker.request_hunk_choice.connect(self._on_worker_request_hunk_choice)
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._current_worker = worker
        self._set_busy(True)
        self.statusBar().showMessage("Applicazione diff in corso…")
        worker.start()

    @QtCore.Slot(str)
    def _on_worker_progress(self, message: str) -> None:  # pragma: no cover - UI feedback
        if not message:
            return
        self.log.appendPlainText(message)
        self.statusBar().showMessage(message[:100])

    @QtCore.Slot(object)
    def _on_worker_finished(self, session: ApplySession) -> None:  # pragma: no cover - UI feedback
        self._current_worker = None
        self.write_report(session)
        logger.info("\n=== RISULTATO ===\n%s", session.to_txt())
        self._set_busy(False)
        QtWidgets.QMessageBox.information(
            self,
            "Completato",
            "Operazione terminata. Vedi log e report nella cartella di backup.",
        )
        self.statusBar().showMessage("Operazione completata")

    @QtCore.Slot(str)
    def _on_worker_error(self, message: str) -> None:  # pragma: no cover - UI feedback
        logger.error("Errore durante l'applicazione della patch: %s", message)
        self._set_busy(False)
        self._current_worker = None
        QtWidgets.QMessageBox.critical(self, "Errore", message)
        self.statusBar().showMessage("Errore durante l'applicazione della patch")

    @QtCore.Slot(str, object)
    def _on_worker_request_file_choice(self, rel_path: str, candidates: List[Path]) -> None:  # pragma: no cover - UI feedback
        worker = self._current_worker
        if worker is None:
            return
        dlg = FileChoiceDialog(self, f"Seleziona file per {rel_path}", candidates)
        choice: Optional[Path] = None
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.chosen:
            choice = dlg.chosen
        worker.provide_file_choice(choice)

    @QtCore.Slot(str, object, object)
    def _on_worker_request_hunk_choice(
        self, file_text: str, candidates: List[Tuple[int, float]], hv: HunkView
    ) -> None:  # pragma: no cover - UI feedback
        worker = self._current_worker
        if worker is None:
            return
        dlg = CandidateDialog(self, file_text, candidates, hv)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selected_pos is not None:
            worker.provide_hunk_choice(dlg.selected_pos)
        else:
            worker.provide_hunk_choice(None)

    def apply_file_patch(self, pf: PatchedFile, rel_path: str, session: ApplySession) -> FileResult:
        fr = FileResult(file_path=Path(), relative_to_root=rel_path)

        candidates = self.find_files_in_project(rel_path)
        if not candidates:
            fr.skipped_reason = "File non trovato nella root – salto per preferenza utente"
            logger.warning("SKIP: %s non trovato.", rel_path)
            return fr
        if len(candidates) > 1:
            choice_dialog = FileChoiceDialog(self, f"Seleziona file per {rel_path}", candidates)
            if choice_dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted or not choice_dialog.chosen:
                fr.skipped_reason = "Ambiguità sul file, operazione annullata dall'utente"
                return fr
            path = choice_dialog.chosen
        else:
            path = candidates[0]

        fr.file_path = path
        project_root = self.project_root
        if project_root is None:
            raise RuntimeError("Project root must be set before applying a patch")
        fr.relative_to_root = str(path.relative_to(project_root))
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
            self.backup_file(path, session.backup_dir)

        for h in pf:
            hv = build_hunk_view(h)
            decision = HunkDecision(hunk_header=hv.header, strategy="")

            cand = find_candidates(lines, hv.before_lines, threshold=1.0)
            if cand:
                pos = cand[0][0]
                if not session.dry_run:
                    lines = apply_hunk_at_position(lines, hv, pos)
                decision.strategy = "exact"
                decision.selected_pos = pos
                decision.similarity = 1.0
                fr.hunks_applied += 1
                fr.decisions.append(decision)
                continue

            cand = find_candidates(lines, hv.before_lines, threshold=session.threshold)
            if len(cand) == 1:
                pos, score = cand[0]
                if not session.dry_run:
                    lines = apply_hunk_at_position(lines, hv, pos)
                decision.strategy = "fuzzy"
                decision.selected_pos = pos
                decision.similarity = score
                fr.hunks_applied += 1
                fr.decisions.append(decision)
                continue
            elif len(cand) > 1:
                decision.strategy = "manual"
                decision.candidates = cand
                file_text = "".join(lines)
                candidate_dialog = CandidateDialog(self, file_text, cand, hv)
                if (
                    candidate_dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
                    and candidate_dialog.selected_pos is not None
                ):
                    pos = candidate_dialog.selected_pos
                    if not session.dry_run:
                        lines = apply_hunk_at_position(lines, hv, pos)
                    decision.selected_pos = pos
                    chosen_score = next((s for p, s in cand if p == pos), None)
                    decision.similarity = chosen_score
                    fr.hunks_applied += 1
                else:
                    decision.strategy = "failed"
                    decision.message = "Scelta annullata dall'utente"
                fr.decisions.append(decision)
                continue

            before_ctx = [l for l in hv.before_lines if not l.startswith(("+", "-"))]
            cand = find_candidates(lines, before_ctx, threshold=session.threshold)
            if cand:
                decision.strategy = "manual"
                decision.candidates = cand
                file_text = "".join(lines)
                candidate_dialog = CandidateDialog(self, file_text, cand, hv)
                if (
                    candidate_dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
                    and candidate_dialog.selected_pos is not None
                ):
                    pos = candidate_dialog.selected_pos
                    if not session.dry_run:
                        lines = apply_hunk_at_position(lines, hv, pos)
                    decision.selected_pos = pos
                    chosen_score = next((s for p, s in cand if p == pos), None)
                    decision.similarity = chosen_score
                    fr.hunks_applied += 1
                else:
                    decision.strategy = "failed"
                    decision.message = "Scelta annullata (solo contesto)"
                fr.decisions.append(decision)
                continue

            decision.strategy = "failed"
            decision.message = "Nessun candidato trovato sopra la soglia"
            fr.decisions.append(decision)

        if not session.dry_run:
            new_text = "".join(lines)
            new_text = new_text.replace("\n", orig_eol)
            write_text_preserving_encoding(path, new_text, file_encoding)

        return fr

    def ensure_backup_dir(self) -> Path:
        project_root = self.project_root
        if project_root is None:
            raise RuntimeError("Project root must be set before creating backups")
        base = project_root / BACKUP_DIR
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        full = base / stamp
        full.mkdir(parents=True, exist_ok=True)
        return full

    def backup_file(self, path: Path, backup_root: Path) -> None:
        project_root = self.project_root
        if project_root is None:
            raise RuntimeError("Project root must be set before creating backups")
        rel = path.relative_to(project_root)
        dst = backup_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)

    def write_report(self, session: ApplySession) -> None:
        (session.backup_dir / REPORT_JSON).write_text(
            json.dumps(session.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (session.backup_dir / REPORT_TXT).write_text(session.to_txt(), encoding="utf-8")

    def restore_from_backup(self) -> None:
        project_root = self.project_root
        if project_root is None:
            QtWidgets.QMessageBox.warning(self, "Root mancante", "Seleziona la root del progetto.")
            return
        base = project_root / BACKUP_DIR
        if not base.exists():
            QtWidgets.QMessageBox.information(self, "Nessun backup", "Cartella backup non trovata.")
            return
        stamps = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
        if not stamps:
            QtWidgets.QMessageBox.information(self, "Nessun backup", "Nessuna sessione di backup trovata.")
            return
        items = [str(p.name) for p in stamps]
        item, ok = QtWidgets.QInputDialog.getItem(self, "Seleziona backup", "Sessione:", items, 0, False)
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
                dest = project_root / src.relative_to(chosen)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        QtWidgets.QMessageBox.information(self, "Ripristino completato", f"Backup {item} ripristinato.")

    def find_files_in_project(self, rel_path: str) -> List[Path]:
        project_root = self.project_root
        if project_root is None:
            raise RuntimeError("Project root is not configured")
        rel_path = rel_path.strip()
        if rel_path.startswith("a/") or rel_path.startswith("b/"):
            rel_path = rel_path[2:]
        exact = project_root / rel_path
        if exact.exists():
            return [exact]
        name = Path(rel_path).name
        matches = [p for p in project_root.rglob(name) if p.is_file()]
        return matches

def main() -> None:
    configure_logging()
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    translators = install_translators(app)
    setattr(app, "_installed_translators", translators)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


__all__ = ["CandidateDialog", "FileChoiceDialog", "GuiLogHandler", "MainWindow", "PatchApplyWorker", "configure_logging", "main"]
