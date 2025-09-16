"""Patch application data structures and helper routines."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .utils import APP_NAME


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


@dataclass
class HunkView:
    header: str
    before_lines: List[str]
    after_lines: List[str]


def build_hunk_view(hunk) -> HunkView:
    """Construct lists of strings for the "before" and "after" sequences for a hunk."""

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
    header = str(hunk).split("\n")[0]
    return HunkView(header=header, before_lines=before, after_lines=after)


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_candidates(file_lines: List[str], before_lines: List[str], threshold: float) -> List[Tuple[int, float]]:
    """Return candidate start positions with similarity >= threshold, sorted by score desc."""

    candidates: List[Tuple[int, float]] = []
    if not before_lines:
        return candidates
    window_len = len(before_lines)
    target_text = "".join(before_lines)

    file_text = "".join(file_lines)
    idx = file_text.find(target_text)
    if idx != -1:
        cumulative = 0
        for i, line in enumerate(file_lines):
            if cumulative == idx:
                candidates.append((i, 1.0))
                break
            cumulative += len(line)
        if candidates:
            return candidates

    for i in range(0, len(file_lines) - window_len + 1):
        window_text = "".join(file_lines[i: i + window_len])
        score = text_similarity(window_text, target_text)
        if score >= threshold:
            candidates.append((i, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates


def apply_hunk_at_position(file_lines: List[str], hv: HunkView, pos: int) -> List[str]:
    """Apply the hunk at the given starting line index."""

    window_len = len(hv.before_lines)
    end = pos + window_len
    if end > len(file_lines):
        raise IndexError("Hunk window beyond end of file")

    new_chunk: List[str] = hv.after_lines
    return file_lines[:pos] + new_chunk + file_lines[end:]


__all__ = [
    "ApplySession",
    "FileResult",
    "HunkDecision",
    "HunkView",
    "apply_hunk_at_position",
    "build_hunk_view",
    "find_candidates",
    "text_similarity",
]
