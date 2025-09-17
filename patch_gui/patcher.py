"""Patch application data structures and helper routines."""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Iterable, Iterator, List, Optional, Protocol, Sequence, Tuple

from .utils import APP_NAME, BACKUP_DIR, REPORT_JSON, REPORT_TXT


class _HunkLine(Protocol):
    line_type: str
    value: str


class _HunkLike(Protocol):
    def __iter__(self) -> Iterator[_HunkLine]:
        ...

    def __str__(self) -> str:
        ...


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
    report_json_path: Optional[Path] = None
    report_txt_path: Optional[Path] = None

    def to_json(self) -> dict[str, object]:
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


ManualResolver = Callable[["HunkView", List[str], List[Tuple[int, float]], HunkDecision, str], Optional[int]]


logger = logging.getLogger(__name__)


def build_hunk_view(hunk: _HunkLike) -> HunkView:
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


def find_candidates(
    file_lines: Sequence[str], before_lines: Sequence[str], threshold: float
) -> List[Tuple[int, float]]:
    """Return candidate start positions with similarity >= threshold, sorted by score desc."""

    logger.debug(
        "find_candidates: searching window of %s lines within file of %s lines (threshold %.2f)",
        len(before_lines),
        len(file_lines),
        threshold,
    )
    candidates: List[Tuple[int, float]] = []
    if not before_lines:
        logger.debug("find_candidates: empty before_lines, returning 0 candidates")
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
            logger.debug("find_candidates: found exact candidate at position %s", candidates[0][0])
            return candidates

    for i in range(0, len(file_lines) - window_len + 1):
        window_text = "".join(file_lines[i: i + window_len])
        score = text_similarity(window_text, target_text)
        if score >= threshold:
            candidates.append((i, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    logger.debug(
        "find_candidates: returning %s candidate(s) meeting threshold %.2f",
        len(candidates),
        threshold,
    )
    return candidates


def apply_hunk_at_position(file_lines: Sequence[str], hv: HunkView, pos: int) -> List[str]:
    """Apply the hunk at the given starting line index."""

    window_len = len(hv.before_lines)
    end = pos + window_len
    if end > len(file_lines):
        raise IndexError("Hunk window beyond end of file")

    new_chunk: List[str] = hv.after_lines
    return list(file_lines[:pos]) + list(new_chunk) + list(file_lines[end:])


def apply_hunks(
    file_lines: List[str],
    hunks: Iterable[_HunkLike],
    *,
    threshold: float,
    manual_resolver: Optional[ManualResolver] = None,
) -> Tuple[List[str], List[HunkDecision], int]:
    """Apply ``hunks`` to ``file_lines`` returning the modified lines and decisions."""

    current_lines = file_lines
    decisions: List[HunkDecision] = []
    applied_count = 0
    logger.debug(
        "apply_hunks: starting with threshold %.2f (manual_resolver=%s)",
        threshold,
        manual_resolver is not None,
    )

    def _apply(
        lines: List[str],
        hv: HunkView,
        decision: HunkDecision,
        pos: int,
        similarity: Optional[float],
        strategy: Optional[str],
    ) -> Tuple[List[str], bool]:
        try:
            new_lines = apply_hunk_at_position(lines, hv, pos)
        except Exception as exc:
            decision.strategy = "failed"
            decision.message = f"Errore durante l'applicazione del hunk: {exc}"
            logger.exception(
                "apply_hunks: error applying hunk '%s' at position %s",
                hv.header,
                pos,
            )
            return lines, False
        if strategy:
            decision.strategy = strategy
        decision.selected_pos = pos
        if similarity is not None:
            decision.similarity = similarity
        logger.debug(
            "apply_hunks: applied hunk '%s' at position %s with strategy %s (similarity=%s)",
            hv.header,
            pos,
            strategy or decision.strategy,
            None if similarity is None else f"{similarity:.3f}",
        )
        return new_lines, True

    total_hunks = 0
    for total_hunks, hunk in enumerate(hunks, 1):
        hv = build_hunk_view(hunk)
        decision = HunkDecision(hunk_header=hv.header, strategy="")
        logger.debug("apply_hunks: processing hunk #%s '%s'", total_hunks, hv.header)

        exact_candidates = find_candidates(current_lines, hv.before_lines, threshold=1.0)
        if exact_candidates:
            pos, score = exact_candidates[0]
            current_lines, success = _apply(current_lines, hv, decision, pos, score, "exact")
            if success:
                applied_count += 1
                logger.info(
                    "apply_hunks: hunk '%s' applied via exact match at line %s",
                    hv.header,
                    pos,
                )
            decisions.append(decision)
            continue

        fuzzy_candidates = find_candidates(current_lines, hv.before_lines, threshold=threshold)
        if len(fuzzy_candidates) == 1:
            pos, score = fuzzy_candidates[0]
            current_lines, success = _apply(current_lines, hv, decision, pos, score, "fuzzy")
            if success:
                applied_count += 1
                logger.info(
                    "apply_hunks: hunk '%s' applied via fuzzy match at line %s (similarity %.3f)",
                    hv.header,
                    pos,
                    score,
                )
            decisions.append(decision)
            continue
        if len(fuzzy_candidates) > 1:
            decision.strategy = "manual"
            decision.candidates = fuzzy_candidates
            chosen: Optional[int] = None
            if manual_resolver is not None:
                logger.info(
                    "apply_hunks: hunk '%s' requires manual resolution for %s fuzzy candidates",
                    hv.header,
                    len(fuzzy_candidates),
                )
                chosen = manual_resolver(hv, current_lines, fuzzy_candidates, decision, "fuzzy")
            if chosen is not None:
                similarity = next((score for pos_, score in fuzzy_candidates if pos_ == chosen), None)
                current_lines, success = _apply(current_lines, hv, decision, chosen, similarity, None)
                if success:
                    applied_count += 1
                    logger.info(
                        "apply_hunks: hunk '%s' applied after manual fuzzy selection at line %s",
                        hv.header,
                        chosen,
                    )
                decisions.append(decision)
                continue
            if decision.strategy == "manual" and not decision.message:
                decision.strategy = "failed"
                decision.message = "Applicazione annullata per ambiguità fuzzy."
            logger.info("apply_hunks: hunk '%s' skipped due to fuzzy ambiguity", hv.header)
            decisions.append(decision)
            continue

        context_lines = [ln for ln in hv.before_lines if not ln.startswith(("+", "-"))]
        context_candidates: List[Tuple[int, float]] = []
        if context_lines:
            context_candidates = find_candidates(current_lines, context_lines, threshold=threshold)
        if context_candidates:
            decision.strategy = "manual"
            decision.candidates = context_candidates
            chosen = None
            if manual_resolver is not None:
                logger.info(
                    "apply_hunks: hunk '%s' requires manual resolution (context-only) with %s candidates",
                    hv.header,
                    len(context_candidates),
                )
                chosen = manual_resolver(hv, current_lines, context_candidates, decision, "context")
            if chosen is not None:
                similarity = next((score for pos_, score in context_candidates if pos_ == chosen), None)
                current_lines, success = _apply(current_lines, hv, decision, chosen, similarity, None)
                if success:
                    applied_count += 1
                    logger.info(
                        "apply_hunks: hunk '%s' applied after manual context selection at line %s",
                        hv.header,
                        chosen,
                    )
                decisions.append(decision)
                continue
            if decision.strategy == "manual" and not decision.message:
                decision.strategy = "failed"
                decision.message = "Applicazione annullata (solo contesto)."
            logger.info("apply_hunks: hunk '%s' skipped after context-only ambiguity", hv.header)
            decisions.append(decision)
            continue

        decision.strategy = "failed"
        if not decision.message:
            decision.message = "Nessun candidato compatibile trovato sopra la soglia impostata."
        logger.info("apply_hunks: hunk '%s' failed – no candidates", hv.header)
        decisions.append(decision)

    logger.info(
        "apply_hunks: completed with %s/%s hunks applied",
        applied_count,
        total_hunks,
    )
    return current_lines, decisions, applied_count


def find_file_candidates(project_root: Path, rel_path: str) -> List[Path]:
    """Return possible file matches for ``rel_path`` relative to ``project_root``."""

    rel = rel_path.strip()
    if rel.startswith("a/") or rel.startswith("b/"):
        rel = rel[2:]
    if not rel:
        logger.debug("find_file_candidates: empty relative path")
        return []

    exact = project_root / rel
    if exact.exists():
        logger.debug("find_file_candidates: found exact path match for '%s'", rel)
        return [exact]

    name = Path(rel).name
    logger.debug("find_file_candidates: searching recursively for '%s' (basename '%s')", rel, name)
    matches = [p for p in project_root.rglob(name) if p.is_file()]
    if not matches:
        logger.info("find_file_candidates: no candidates found for '%s'", rel)
        return []

    suffix_matches = []
    for path in matches:
        try:
            relative = path.relative_to(project_root)
        except ValueError:
            logger.debug(
                "find_file_candidates: skipping path '%s' outside project root '%s'",
                path,
                project_root,
            )
            continue
        if str(relative).endswith(rel):
            suffix_matches.append(path)
    if len(suffix_matches) == 1:
        logger.debug(
            "find_file_candidates: selected suffix match '%s' for '%s'",
            suffix_matches[0],
            rel,
        )
        return suffix_matches

    sorted_matches = sorted(matches)
    logger.debug(
        "find_file_candidates: returning %s candidate(s) for '%s'",
        len(sorted_matches),
        rel,
    )
    return sorted_matches


def prepare_backup_dir(
    project_root: Path,
    *,
    dry_run: bool,
    backup_base: Optional[Path] = None,
) -> Path:
    """Return a timestamped backup directory for the session."""

    base = backup_base.expanduser() if backup_base is not None else project_root / BACKUP_DIR
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = base / timestamp
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def backup_file(project_root: Path, path: Path, backup_root: Path) -> None:
    """Copy ``path`` inside ``backup_root`` preserving the relative structure."""

    rel = path.relative_to(project_root)
    dest = backup_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def write_reports(
    session: ApplySession,
    *,
    json_path: Path | str | None = None,
    txt_path: Path | str | None = None,
    write_json: bool = True,
    write_txt: bool = True,
) -> tuple[Optional[Path], Optional[Path]]:
    """Persist JSON and text reports for ``session`` and return written paths."""

    if not write_json and not write_txt:
        return None, None

    session.backup_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(raw: Path | str | None, default: Path) -> Path:
        if raw is None:
            return default
        if isinstance(raw, str):
            cleaned = raw.strip()
            if not cleaned:
                return default
            return Path(cleaned).expanduser()
        return raw.expanduser()

    json_target: Optional[Path] = None
    txt_target: Optional[Path] = None

    if write_json:
        json_target = _resolve_path(json_path, session.backup_dir / REPORT_JSON)
        json_target.parent.mkdir(parents=True, exist_ok=True)
        json_target.write_text(
            json.dumps(session.to_json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if write_txt:
        txt_target = _resolve_path(txt_path, session.backup_dir / REPORT_TXT)
        txt_target.parent.mkdir(parents=True, exist_ok=True)
        txt_target.write_text(session.to_txt(), encoding="utf-8")

    return json_target, txt_target


__all__ = [
    "ApplySession",
    "FileResult",
    "HunkDecision",
    "HunkView",
    "ManualResolver",
    "apply_hunk_at_position",
    "apply_hunks",
    "backup_file",
    "build_hunk_view",
    "find_file_candidates",
    "find_candidates",
    "prepare_backup_dir",
    "text_similarity",
    "write_reports",
]
