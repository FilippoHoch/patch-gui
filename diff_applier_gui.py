#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch GUI – PySide6 Diff Applier

Funzioni principali:
- Carica diff (file, incolla, appunti). Supporta unified diff e formato *** Begin Patch / *** Update File.
- Selezione root progetto e risoluzione automatica dei percorsi (ricorsiva). In caso di multipli, chiede conferma.
- Dry-run con anteprima delle modifiche applicate per file/hunk.
- Applicazione patch con matching: esatto -> contestuale -> fuzzy (threshold configurabile).
- Gestione ambiguità: mostra i candidati e chiede all'utente quale applicare.
- Backup automatico (./.diff_backups/<timestamp>) e report (JSON + TXT).
- Ripristino da backup.

Dipendenze:
- PySide6
- unidiff

Esecuzione:
  python diff_applier_gui.py

Nota: testato su Linux/WSL. Su Windows via WSLg dovrebbe aprire la GUI.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# 3rd-party
from unidiff import PatchSet
from PySide6 import QtCore, QtGui, QtWidgets

from difflib import SequenceMatcher

APP_NAME = "Patch GUI – Diff Applier"
BACKUP_DIR = ".diff_backups"
REPORT_JSON = "apply-report.json"
REPORT_TXT = "apply-report.txt"

# ------------------------
# Utilities & data models
# ------------------------

@dataclass
class HunkDecision:
    hunk_header: str
    strategy: str  # exact | context | fuzzy | manual | failed | skipped
    selected_pos: Optional[int] = None
    similarity: Optional[float] = None
    candidates: List[Tuple[int, float]] = field(default_factory=list)  # (pos, score)
    message: str = ""

@dataclass
class FileResult:
    file_path: Path
    relative_to_root: str
    hunks_applied: int = 0
    hunks_total: int = 0
    decisions: List[HunkDecision] = field(default_factory=list)
    skipped_reason: Optional[str] = None

@dataclass
class ApplySession:
    project_root: Path
    backup_dir: Path
    dry_run: bool
    threshold: float
    started_at: float
    results: List[FileResult] = field(default_factory=list)

    def to_json(self) -> Dict:
        return {
            "project_root": str(self.project_root),
            "backup_dir": str(self.backup_dir),
            "dry_run": self.dry_run,
            "threshold": self.threshold,
            "started_at": datetime.fromtimestamp(self.started_at).isoformat(),
            "files": [
                {
                    "file": fr.relative_to_root,
                    "abs_path": str(fr.file_path),
                    "hunks_applied": fr.hunks_applied,
                    "hunks_total": fr.hunks_total,
                    "skipped_reason": fr.skipped_reason,
                    "decisions": [
                        {
                            "hunk": d.hunk_header,
                            "strategy": d.strategy,
                            "pos": d.selected_pos,
                            "similarity": d.similarity,
                            "candidates": d.candidates,
                            "message": d.message,
                        }
                        for d in fr.decisions
                    ],
                }
                for fr in self.results
            ],
        }

    def to_txt(self) -> str:
        lines = []
        lines.append(f"Report – {APP_NAME}")
        lines.append(f"Avviato: {datetime.fromtimestamp(self.started_at)}")
        lines.append(f"Root progetto: {self.project_root}")
        lines.append(f"Backup: {self.backup_dir}")
        lines.append(f"Dry-run: {self.dry_run}")
        lines.append(f"Soglia fuzzy: {self.threshold}")
        lines.append("")
        for fr in self.results:
            lines.append(f"File: {fr.relative_to_root}")
            if fr.skipped_reason:
                lines.append(f"  SKIPPED: {fr.skipped_reason}")
            lines.append(f"  Hunks: {fr.hunks_applied}/{fr.hunks_total}")
            for d in fr.decisions:
                lines.append(f"    Hunk {d.hunk_header} -> {d.strategy}")
                if d.selected_pos is not None:
                    lines.append(f"      Pos: {d.selected_pos}")
                if d.similarity is not None:
                    lines.append(f"      Similarità: {d.similarity:.3f}")
                if d.candidates:
                    cand_str = ", ".join([f"(pos {p}, sim {s:.3f})" for p, s in d.candidates])
                    lines.append(f"      Candidati: {cand_str}")
                if d.message:
                    lines.append(f"      Note: {d.message}")
            lines.append("")
        return "\n".join(lines)

# ------------------------
# Diff parsing & preprocessing
# ------------------------

BEGIN_PATCH_RE = re.compile(r"^\*\*\* Begin Patch", re.MULTILINE)
END_PATCH_RE = re.compile(r"^\*\*\* End Patch", re.MULTILINE)
UPDATE_FILE_RE = re.compile(r"^\*\*\* Update File: (.+)$", re.MULTILINE)
HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@.*$")


def normalize_newlines(text: str) -> str:
    # Keep original detection for writing back, but normalize internally to \n
    return text.replace("\r\n", "\n").replace("\r", "\n")


def preprocess_patch_text(raw_text: str) -> str:
    """Accept either standard unified diff or "*** Begin Patch" format and
    return unified diff text (with ---/+++ headers). Multiple files supported.
    """
    text = normalize_newlines(raw_text)

    if not BEGIN_PATCH_RE.search(text):
        # looks like unified diff already – return as is
        return text

    # Convert custom block format into standard unified diff
    parts = []
    pos = 0
    while True:
        m_begin = BEGIN_PATCH_RE.search(text, pos)
        if not m_begin:
            break
        m_end = END_PATCH_RE.search(text, m_begin.end())
        if not m_end:
            # No end – take rest
            block = text[m_begin.end():]
            pos = len(text)
        else:
            block = text[m_begin.end(): m_end.start()]
            pos = m_end.end()

        # Split block by *** Update File
        files = [m for m in UPDATE_FILE_RE.finditer(block)]
        for i, m_up in enumerate(files):
            start = m_up.end()
            end = files[i + 1].start() if i + 1 < len(files) else len(block)
            filename = m_up.group(1).strip()
            hunks = block[start:end].strip("\n")
            if not hunks:
                continue
            # Ensure hunks start with @@ lines; we synthesize headers
            header = f"--- a/{filename}\n+++ b/{filename}\n"
            # Keep only hunk lines ('@@', ' ', '+', '-', '\\')
            raw_lines = []
            for line in hunks.splitlines():
                if line.startswith("@@") or line.startswith(("+", "-", " ", "\\")):
                    raw_lines.append(line)
            if not raw_lines:
                continue

            def finalize_hunk(lines: List[str]) -> List[str]:
                if not lines:
                    return []
                header_line = lines[0]
                body = lines[1:]
                if not HUNK_HEADER_RE.match(header_line):
                    suffix = lines[0][2:].strip()
                    removed = sum(1 for l in body if l.startswith((" ", "-")))
                    added = sum(1 for l in body if l.startswith((" ", "+")))
                    old_start = 1 if removed > 0 else 0
                    new_start = 1 if added > 0 else 0
                    header_line = f"@@ -{old_start},{removed} +{new_start},{added} @@"
                    if suffix:
                        header_line += f" {suffix}"
                return [header_line, *body]

            normalized_lines: List[str] = []
            current_hunk: List[str] = []
            for line in raw_lines:
                if line.startswith("@@"):
                    if current_hunk:
                        normalized_lines.extend(finalize_hunk(current_hunk))
                    current_hunk = [line]
                else:
                    if not current_hunk:
                        continue
                    current_hunk.append(line)
            if current_hunk:
                normalized_lines.extend(finalize_hunk(current_hunk))

            if normalized_lines:
                parts.append(header + "\n".join(normalized_lines) + "\n")

    return "".join(parts)


# ------------------------
# Hunk application logic (exact/context/fuzzy)
# ------------------------

@dataclass
class HunkView:
    header: str
    before_lines: List[str]  # lines expected in source (context + removed)
    after_lines: List[str]   # lines resulting (context + added)


def build_hunk_view(hunk) -> HunkView:
    """Construct lists of strings for the 'before' and 'after' sequences for a hunk.
    We preserve newlines for join/compare convenience.
    """
    before: List[str] = []
    after: List[str] = []
    for line in hunk:
        tag = line.line_type  # ' ', '+', '-', '\\'
        value = line.value
        if tag == ' ':
            before.append(value)
            after.append(value)
        elif tag == '-':
            before.append(value)
        elif tag == '+':
            after.append(value)
        else:
            # "\\ No newline at end of file" markers – ignore in content
            pass
    header = str(hunk).split("\\n")[0]
    return HunkView(header=header, before_lines=before, after_lines=after)


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_candidates(file_lines: List[str], before_lines: List[str], threshold: float) -> List[Tuple[int, float]]:
    """Return candidate start positions with similarity >= threshold, sorted by score desc.
    If exact match exists, it will have score 1.0.
    """
    candidates: List[Tuple[int, float]] = []
    if not before_lines:
        return candidates
    window_len = len(before_lines)
    target_text = "".join(before_lines)

    # Fast path: exact search
    file_text = "".join(file_lines)
    idx = file_text.find(target_text)
    if idx != -1:
        # Map char index to line index
        cumulative = 0
        for i, line in enumerate(file_lines):
            if cumulative == idx:
                candidates.append((i, 1.0))
                break
            cumulative += len(line)
        if candidates:
            return candidates

    # Sliding window similarity
    for i in range(0, len(file_lines) - window_len + 1):
        window_text = "".join(file_lines[i: i + window_len])
        score = text_similarity(window_text, target_text)
        if score >= threshold:
            candidates.append((i, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates


def apply_hunk_at_position(file_lines: List[str], hv: HunkView, pos: int) -> List[str]:
    """Apply the hunk at the given starting line index, assuming hv.before_lines
    corresponds to the current content around pos (exact or fuzzy approved).

    Returns new list of lines.
    """
    window_len = len(hv.before_lines)
    # Defensive: ensure the window is within file length
    end = pos + window_len
    if end > len(file_lines):
        raise IndexError("Hunk window beyond end of file")

    # Build replaced chunk: start with before -> after transformation
    # We trust the diff sequence: remove '-' lines and add '+' lines in order, keeping ' ' lines.
    new_chunk: List[str] = hv.after_lines
    # Replace the slice
    return file_lines[:pos] + new_chunk + file_lines[end:]


# ------------------------
# GUI components
# ------------------------

class CandidateDialog(QtWidgets.QDialog):
    def __init__(self, parent, file_text: str, candidates: List[Tuple[int, float]], hv: HunkView):
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

        # Left: list of candidates with preview
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

        # Right: hunk 'before'
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.addWidget(QtWidgets.QLabel("Hunk – contenuto atteso (prima):"))
        self.preview_right = QtWidgets.QPlainTextEdit("".join(hv.before_lines))
        self.preview_right.setReadOnly(True)
        right_layout.addWidget(self.preview_right, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        layout.addWidget(splitter, 1)

        # Buttons
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        # Update preview when selection changes
        def on_row_changed():
            row = self.list.currentRow()
            if row < 0:
                return
            pos, _ = candidates[row]
            # Show ~30 lines context around the candidate
            file_lines = file_text.splitlines(keepends=True)
            start = max(0, pos - 15)
            end = min(len(file_lines), pos + len(hv.before_lines) + 15)
            snippet = "".join(file_lines[start:end])
            self.preview_left.setPlainText(snippet)
        self.list.currentRowChanged.connect(on_row_changed)
        on_row_changed()

    def accept(self):
        row = self.list.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Selezione obbligatoria", "Seleziona una posizione dalla lista.")
            return
        # Extract pos from item text
        text = self.list.currentItem().text()
        m = re.search(r"Linea (\d+)", text)
        if m:
            self.selected_pos = int(m.group(1)) - 1
        super().accept()


class FileChoiceDialog(QtWidgets.QDialog):
    def __init__(self, parent, title: str, choices: List[Path]):
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

    def accept(self):
        row = self.list.currentRow()
        if row >= 0:
            self.chosen = Path(self.list.item(row).text())
        super().accept()


# ------------------------
# Main Window
# ------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)

        self.project_root: Optional[Path] = None
        self.settings = QtCore.QSettings("Work", "PatchDiffApplier")
        self.diff_text: str = ""
        self.patch: Optional[PatchSet] = None

        self.threshold = 0.85

        # Central UI
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # Top controls
        top = QtWidgets.QHBoxLayout()
        layout.addLayout(top)

        self.root_edit = QtWidgets.QLineEdit()
        self.root_edit.setPlaceholderText("Root del progetto (seleziona cartella)")
        btn_root = QtWidgets.QPushButton("Scegli root…")
        btn_root.clicked.connect(self.choose_root)

        btn_load_file = QtWidgets.QPushButton("Apri .diff…")
        btn_load_file.clicked.connect(self.load_diff_file)

        btn_from_clip = QtWidgets.QPushButton("Incolla da appunti")
        btn_from_clip.clicked.connect(self.load_from_clipboard)

        btn_from_text = QtWidgets.QPushButton("Analizza testo diff")
        btn_from_text.clicked.connect(self.parse_from_textarea)

        self.btn_analyze = QtWidgets.QPushButton("Analizza diff")
        self.btn_analyze.clicked.connect(self.analyze_diff)

        top.addWidget(self.root_edit, 1)
        top.addWidget(btn_root)
        top.addSpacing(20)
        top.addWidget(btn_load_file)
        top.addWidget(btn_from_clip)
        top.addWidget(btn_from_text)
        top.addWidget(self.btn_analyze)

        # Threshold + dry run
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

        # Splitter: left tree (files/hunks), right diff text area
        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["File / Hunk", "Stato"]) 
        left_layout.addWidget(self.tree, 1)

        btn_apply = QtWidgets.QPushButton("Applica patch")
        btn_apply.clicked.connect(self.apply_patch)

        btn_restore = QtWidgets.QPushButton("Ripristina da backup…")
        btn_restore.clicked.connect(self.restore_from_backup)

        left_btns = QtWidgets.QHBoxLayout()
        left_btns.addWidget(btn_apply)
        left_btns.addWidget(btn_restore)
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

        self.statusBar().showMessage("Pronto")

        self.restore_last_project_root()

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
        last_root = self.settings.value("last_project_root", type=str)
        if not last_root:
            return
        path = Path(last_root).expanduser()
        if path.exists() and path.is_dir():
            self.set_project_root(path, persist=False)
        else:
            self.settings.remove("last_project_root")
            self.settings.sync()

    # --------- UI actions ---------
    def choose_root(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Seleziona root del progetto")
        if d:
            self.set_project_root(Path(d))

    def load_diff_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Apri file .diff", filter="Diff files (*.diff *.patch *.txt);;Tutti (*.*)")
        if not path:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            self.diff_text = f.read()
        self.text_diff.setPlainText(self.diff_text)
        self.log_append(f"Caricato diff da file: {path}")

    def load_from_clipboard(self):
        cb = QtGui.QGuiApplication.clipboard()
        text = cb.text()
        if not text:
            QtWidgets.QMessageBox.information(self, "Appunti vuoti", "La clipboard non contiene testo.")
            return
        self.diff_text = text
        self.text_diff.setPlainText(self.diff_text)
        self.log_append("Diff caricato dagli appunti.")

    def parse_from_textarea(self):
        self.diff_text = self.text_diff.toPlainText()
        if not self.diff_text.strip():
            QtWidgets.QMessageBox.warning(self, "Nessun testo", "Inserisci del testo diff nella textarea.")
            return
        self.log_append("Testo diff pronto per analisi.")

    def analyze_diff(self):
        if not self.project_root:
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
            node = QtWidgets.QTreeWidgetItem([rel, ""])  # file node
            node.setData(0, QtCore.Qt.ItemDataRole.UserRole, rel)
            self.tree.addTopLevelItem(node)
            for h in pf:
                hv = build_hunk_view(h)
                child = QtWidgets.QTreeWidgetItem([hv.header, ""])  # hunk node
                node.addChild(child)
        self.tree.expandAll()
        self.log_append(f"Analisi completata. File nel diff: {len(self.patch)}")

    def apply_patch(self):
        if not self.patch:
            QtWidgets.QMessageBox.warning(self, "Analizza prima", "Esegui 'Analizza diff' prima di applicare.")
            return
        if not self.project_root:
            QtWidgets.QMessageBox.warning(self, "Root mancante", "Seleziona la root del progetto.")
            return
        dry = self.chk_dry.isChecked()
        thr = float(self.spin_thresh.value())
        session = ApplySession(
            project_root=self.project_root,
            backup_dir=self.ensure_backup_dir(),
            dry_run=dry,
            threshold=thr,
            started_at=time.time(),
        )

        for pf in self.patch:
            rel = pf.path or pf.target_file or pf.source_file or ""
            file_result = self.apply_file_patch(pf, rel, session)
            session.results.append(file_result)

        # Write report
        self.write_report(session)

        # Update UI
        self.log_append("\n=== RISULTATO ===\n" + session.to_txt())
        QtWidgets.QMessageBox.information(self, "Completato", "Operazione terminata. Vedi log e report nella cartella di backup.")

    def apply_file_patch(self, pf, rel_path: str, session: ApplySession) -> FileResult:
        fr = FileResult(file_path=Path(), relative_to_root=rel_path)

        # Resolve candidate paths in project
        candidates = self.find_files_in_project(rel_path)
        if not candidates:
            fr.skipped_reason = "File non trovato nella root – salto per preferenza utente"
            self.log_append(f"SKIP: {rel_path} non trovato.")
            return fr
        if len(candidates) > 1:
            dlg = FileChoiceDialog(self, f"Seleziona file per {rel_path}", candidates)
            if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted or not dlg.chosen:
                fr.skipped_reason = "Ambiguità sul file, operazione annullata dall'utente"
                return fr
            path = dlg.chosen
        else:
            path = candidates[0]

        fr.file_path = path
        fr.relative_to_root = str(path.relative_to(self.project_root))
        fr.hunks_total = len(pf)

        # Read file
        try:
            raw = path.read_bytes()
        except Exception as e:
            fr.skipped_reason = f"Impossibile leggere file: {e}"
            return fr

        # Detect EOL
        content_str = raw.decode("utf-8", errors="replace")
        orig_eol = "\r\n" if "\r\n" in content_str else "\n"
        lines = normalize_newlines(content_str).splitlines(keepends=True)

        # Backup
        if not session.dry_run:
            self.backup_file(path, session.backup_dir)

        # Apply hunks sequentially; after each application, file content changes
        for h in pf:
            hv = build_hunk_view(h)
            decision = HunkDecision(hunk_header=hv.header, strategy="")

            # Strategy 1: exact
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

            # Strategy 2: fuzzy >= threshold. Collect candidates
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
                # Ask user which one
                decision.strategy = "manual"
                decision.candidates = cand
                file_text = "".join(lines)
                dlg = CandidateDialog(self, file_text, cand, hv)
                if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selected_pos is not None:
                    pos = dlg.selected_pos
                    if not session.dry_run:
                        lines = apply_hunk_at_position(lines, hv, pos)
                    decision.selected_pos = pos
                    # compute similarity of chosen
                    chosen_score = next((s for p, s in cand if p == pos), None)
                    decision.similarity = chosen_score
                    fr.hunks_applied += 1
                else:
                    decision.strategy = "failed"
                    decision.message = "Scelta annullata dall'utente"
                fr.decisions.append(decision)
                continue

            # Strategy 3: context-only (use lines with ' ' only) – more permissive
            before_ctx = [l for l in hv.before_lines if not l.startswith(('+', '-'))]
            cand = find_candidates(lines, before_ctx, threshold=session.threshold)
            if cand:
                # Present dialog since context-only is risky
                decision.strategy = "manual"
                decision.candidates = cand
                file_text = "".join(lines)
                dlg = CandidateDialog(self, file_text, cand, hv)
                if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.selected_pos is not None:
                    pos = dlg.selected_pos
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

            # No candidates
            decision.strategy = "failed"
            decision.message = "Nessun candidato trovato sopra la soglia"
            fr.decisions.append(decision)

        # Write file back
        if not session.dry_run:
            new_text = "".join(lines)
            # restore EOL
            new_text = new_text.replace("\n", orig_eol)
            path.write_text(new_text, encoding="utf-8")

        return fr

    def ensure_backup_dir(self) -> Path:
        base = self.project_root / BACKUP_DIR
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        full = base / stamp
        full.mkdir(parents=True, exist_ok=True)
        return full

    def backup_file(self, path: Path, backup_root: Path) -> None:
        rel = path.relative_to(self.project_root)
        dst = backup_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)

    def write_report(self, session: ApplySession) -> None:
        # JSON
        (session.backup_dir / REPORT_JSON).write_text(json.dumps(session.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        # TXT
        (session.backup_dir / REPORT_TXT).write_text(session.to_txt(), encoding="utf-8")

    # ---- restore ----
    def restore_from_backup(self):
        if not self.project_root:
            QtWidgets.QMessageBox.warning(self, "Root mancante", "Seleziona la root del progetto.")
            return
        base = self.project_root / BACKUP_DIR
        if not base.exists():
            QtWidgets.QMessageBox.information(self, "Nessun backup", "Cartella backup non trovata.")
            return
        # Choose a timestamp folder
        stamps = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)
        if not stamps:
            QtWidgets.QMessageBox.information(self, "Nessun backup", "Nessuna sessione di backup trovata.")
            return
        items = [str(p.name) for p in stamps]
        item, ok = QtWidgets.QInputDialog.getItem(self, "Seleziona backup", "Sessione:", items, 0, False)
        if not ok or not item:
            return
        chosen = base / item
        # Confirm
        if QtWidgets.QMessageBox.question(
            self,
            "Conferma ripristino",
            f"Ripristinare i file dalla sessione {item}?\n\nI file correnti saranno sovrascritti.",
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        # Copy all files back
        for src in chosen.rglob("*"):
            if src.is_file():
                dest = self.project_root / src.relative_to(chosen)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        QtWidgets.QMessageBox.information(self, "Ripristino completato", f"Backup {item} ripristinato.")

    # ---- helpers ----
    def find_files_in_project(self, rel_path: str) -> List[Path]:
        """Find files matching the basename and/or relative path within project root.
        Strategy: try exact relative path; else, search by basename recursively.
        """
        assert self.project_root
        rel_path = rel_path.strip()
        if rel_path.startswith("a/") or rel_path.startswith("b/"):
            rel_path = rel_path[2:]
        exact = self.project_root / rel_path
        if exact.exists():
            return [exact]
        # Fallback: by basename
        name = Path(rel_path).name
        matches = [p for p in self.project_root.rglob(name) if p.is_file()]
        return matches

    def log_append(self, msg: str):
        self.log.appendPlainText(msg)
        self.statusBar().showMessage(msg[:100])


# ------------------------
# Entry point
# ------------------------

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
