"""Patch application data structures and helper routines."""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import (
    Callable,
    Iterable,
    Iterator,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

from .localization import gettext as _
from .utils import (
    APP_NAME,
    REPORT_JSON,
    REPORT_TXT,
    default_backup_base,
    default_session_report_dir,
    format_session_timestamp,
)


logger = logging.getLogger(__name__)


DEFAULT_EXCLUDE_DIRS: tuple[str, ...] = (
    ".git",
    ".venv",
    "node_modules",
    ".diff_backups",
)


class _HunkLine(Protocol):
    line_type: str
    value: str


class _HunkLike(Protocol):
    def __iter__(self) -> Iterator[_HunkLine]: ...

    def __str__(self) -> str: ...


@dataclass
class HunkDecision:
    """Record how a single hunk was resolved.

    Attributes:
        hunk_header: The header line that identifies the hunk inside the diff.
        strategy: The approach used to apply the hunk (exact, context, fuzzy, etc.).
        selected_pos: Index of the chosen insertion point in the target file, if any.
        similarity: Similarity score for the selected position when a fuzzy match was used.
        candidates: Possible target positions with their similarity scores for review.
        message: Additional notes describing manual adjustments or failure details.
    """

    hunk_header: str
    strategy: str  # exact | context | fuzzy | manual | failed | skipped
    selected_pos: Optional[int] = None
    similarity: Optional[float] = None
    candidates: List[Tuple[int, float]] = field(default_factory=list)  # (pos, score)
    message: str = ""


@dataclass
class FileResult:
    """Track the application result for a single file.

    Attributes:
        file_path: Absolute path to the file that was processed.
        relative_to_root: Path to display relative to the project root for reporting.
        hunks_applied: Number of hunks successfully written to the file.
        hunks_total: Total number of hunks that were attempted on the file.
        decisions: Detailed decision records for each hunk that was processed.
        skipped_reason: Explanation when the file is skipped instead of being patched.
    """

    file_path: Path
    relative_to_root: str
    file_type: str = "text"
    hunks_applied: int = 0
    hunks_total: int = 0
    decisions: List[HunkDecision] = field(default_factory=list)
    skipped_reason: Optional[str] = None


@dataclass
class ApplySession:
    """Aggregate the patch application run across all files.

    Attributes:
        project_root: Root directory in which the patch is being applied.
        backup_dir: Location where backups are stored before modification.
        dry_run: Flag indicating whether changes were only simulated.
        threshold: Similarity threshold used for fuzzy hunk matching.
        started_at: UNIX timestamp for when the session began.
        results: Per-file records describing how each hunk was handled.
        report_json_path: Location of the generated JSON report, if written.
        report_txt_path: Location of the generated text report, if written.
    """

    project_root: Path
    backup_dir: Path
    dry_run: bool
    threshold: float
    started_at: float
    exclude_dirs: Sequence[str] = field(default_factory=lambda: DEFAULT_EXCLUDE_DIRS)
    results: List[FileResult] = field(default_factory=list)
    report_json_path: Optional[Path] = None
    report_txt_path: Optional[Path] = None

    def to_json(self) -> dict[str, object]:
        return {
            "project_root": str(self.project_root),
            "backup_dir": str(self.backup_dir),
            "dry_run": self.dry_run,
            "threshold": self.threshold,
            "exclude_dirs": list(self.exclude_dirs),
            "started_at": datetime.fromtimestamp(self.started_at).isoformat(),
            "files": [
                {
                    "file": fr.relative_to_root,
                    "abs_path": str(fr.file_path),
                    "file_type": fr.file_type,
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
        lines.append(_("Report – {app_name}").format(app_name=APP_NAME))
        lines.append(
            _("Started: {timestamp}").format(
                timestamp=datetime.fromtimestamp(self.started_at)
            )
        )
        lines.append(
            _("Project root: {project_root}").format(project_root=self.project_root)
        )
        lines.append(
            _("Backup directory: {backup_dir}").format(backup_dir=self.backup_dir)
        )
        lines.append(_("Dry-run: {dry_run}").format(dry_run=self.dry_run))
        lines.append(_("Fuzzy threshold: {threshold}").format(threshold=self.threshold))
        excludes = ", ".join(self.exclude_dirs) if self.exclude_dirs else _("(none)")
        lines.append(
            _("Excluded directories: {directories}").format(directories=excludes)
        )
        total_files = len(self.results)
        total_hunks = sum(fr.hunks_total for fr in self.results)
        applied_hunks = sum(fr.hunks_applied for fr in self.results)
        changed_files = sum(1 for fr in self.results if fr.hunks_applied > 0)
        skipped_files = sum(1 for fr in self.results if fr.skipped_reason)
        lines.append(_("Summary:"))
        lines.append(_("  Files processed: {count}").format(count=total_files))
        lines.append(_("  Files with changes: {count}").format(count=changed_files))
        if skipped_files:
            lines.append(_("  Files skipped: {count}").format(count=skipped_files))
        lines.append(
            _("  Hunks applied: {applied}/{total}").format(
                applied=applied_hunks, total=total_hunks
            )
        )
        if not total_hunks or not applied_hunks:
            lines.append(_("  No changes were applied to the files."))
        lines.append("")
        for fr in self.results:
            lines.append(_("File: {path}").format(path=fr.relative_to_root))
            if fr.skipped_reason:
                lines.append(_("  SKIPPED: {reason}").format(reason=fr.skipped_reason))
            lines.append(_("  File type: {file_type}").format(file_type=fr.file_type))
            lines.append(
                _("  Hunks: {applied}/{total}").format(
                    applied=fr.hunks_applied, total=fr.hunks_total
                )
            )
            for d in fr.decisions:
                lines.append(
                    _("    Hunk {header} -> {strategy}").format(
                        header=d.hunk_header, strategy=d.strategy
                    )
                )
                if d.selected_pos is not None:
                    lines.append(
                        _("      Position: {position}").format(position=d.selected_pos)
                    )
                if d.similarity is not None:
                    lines.append(
                        _("      Similarity: {similarity:.3f}").format(
                            similarity=d.similarity
                        )
                    )
                if d.candidates:
                    max_display = 5
                    displayed = [
                        _("(position {position}, similarity {similarity:.3f})").format(
                            position=p, similarity=s
                        )
                        for p, s in d.candidates[:max_display]
                    ]
                    remaining = len(d.candidates) - max_display
                    if remaining > 0:
                        displayed.append(_("… (+{count} more)").format(count=remaining))
                    cand_str = ", ".join(displayed)
                    lines.append(
                        _("      Candidates: {candidates}").format(candidates=cand_str)
                    )
                if d.message:
                    lines.append(_("      Notes: {notes}").format(notes=d.message))
            lines.append("")
        return "\n".join(lines)


@dataclass
class HunkView:
    header: str
    before_lines: List[str]
    after_lines: List[str]
    context_lines: List[str] = field(default_factory=list)


ManualResolver = Callable[
    ["HunkView", List[str], List[Tuple[int, float]], HunkDecision, str], Optional[int]
]


def build_hunk_view(hunk: _HunkLike) -> HunkView:
    """Construct lists of strings for the "before" and "after" sequences for a hunk."""

    before: List[str] = []
    after: List[str] = []
    context: List[str] = []
    for line in hunk:
        tag = line.line_type  # ' ', '+', '-', '\\'
        value = line.value
        if tag == " ":
            before.append(value)
            after.append(value)
            context.append(value)
        elif tag == "-":
            before.append(value)
        elif tag == "+":
            after.append(value)
        else:
            # "\\ No newline at end of file" markers – ignore in content
            pass
    header = str(hunk).split("\n")[0]
    return HunkView(
        header=header,
        before_lines=before,
        after_lines=after,
        context_lines=context,
    )


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_candidates(
    file_lines: Sequence[str], before_lines: Sequence[str], threshold: float
) -> List[Tuple[int, float]]:
    """Return candidate start positions with similarity >= threshold, sorted by score desc."""

    candidates: List[Tuple[int, float]] = []
    if not before_lines:
        logger.debug("Nessuna linea 'before' fornita, nessun candidato generato")
        return candidates
    window_len = len(before_lines)
    target_text = "".join(before_lines)

    file_text = "".join(file_lines)
    logger.debug(
        "Ricerca candidati: window_len=%d, threshold=%.3f, testo_target=%d char",
        window_len,
        threshold,
        len(target_text),
    )
    idx = file_text.find(target_text)
    if idx != -1:
        cumulative = 0
        for i, line in enumerate(file_lines):
            if cumulative == idx:
                candidates.append((i, 1.0))
                break
            cumulative += len(line)
        if candidates:
            logger.debug("Candidato esatto trovato in posizione %d", candidates[0][0])
            return candidates

    for i in range(0, len(file_lines) - window_len + 1):
        window_text = "".join(file_lines[i : i + window_len])
        score = text_similarity(window_text, target_text)
        if score >= threshold:
            candidates.append((i, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    logger.debug("Trovati %d candidati con soglia %.3f", len(candidates), threshold)
    return candidates


def apply_hunk_at_position(
    file_lines: Sequence[str], hv: HunkView, pos: int
) -> List[str]:
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

    hunks = list(hunks)
    logger.debug(
        "Inizio applicazione hunk: totale=%d, soglia=%.3f",
        len(hunks),
        threshold,
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
            logger.exception("Errore applicando l'hunk %s in pos %d", hv.header, pos)
            return lines, False
        if strategy:
            decision.strategy = strategy
        decision.selected_pos = pos
        if similarity is not None:
            decision.similarity = similarity
        logger.debug(
            "Hunk %s applicato con strategia %s (pos=%d, sim=%s)",
            hv.header,
            decision.strategy,
            pos,
            f"{similarity:.3f}" if similarity is not None else "-",
        )
        return new_lines, True

    for hunk in hunks:
        hv = build_hunk_view(hunk)
        decision = HunkDecision(hunk_header=hv.header, strategy="")
        logger.debug("Processo hunk: %s", hv.header)

        if not current_lines and not hv.before_lines:
            logger.debug(
                "File vuoto: applico l'hunk %s come nuova creazione", hv.header
            )
            current_lines, success = _apply(
                current_lines,
                hv,
                decision,
                0,
                None,
                "new-file",
            )
            if success:
                applied_count += 1
            decisions.append(decision)
            continue

        exact_candidates = find_candidates(
            current_lines, hv.before_lines, threshold=1.0
        )
        if exact_candidates:
            pos, score = exact_candidates[0]
            logger.debug("Match esatto trovato (pos=%d)", pos)
            current_lines, success = _apply(
                current_lines, hv, decision, pos, score, "exact"
            )
            if success:
                applied_count += 1
            decisions.append(decision)
            continue

        fuzzy_candidates = find_candidates(
            current_lines, hv.before_lines, threshold=threshold
        )
        if len(fuzzy_candidates) == 1:
            pos, score = fuzzy_candidates[0]
            logger.debug("Match fuzzy singolo trovato (pos=%d, score=%.3f)", pos, score)
            current_lines, success = _apply(
                current_lines, hv, decision, pos, score, "fuzzy"
            )
            if success:
                applied_count += 1
            decisions.append(decision)
            continue
        if len(fuzzy_candidates) > 1:
            decision.strategy = "manual"
            decision.candidates = fuzzy_candidates
            logger.info(
                "Ambiguità fuzzy per hunk %s: %d candidati",
                hv.header,
                len(fuzzy_candidates),
            )
            chosen: Optional[int] = None
            if manual_resolver is not None:
                chosen = manual_resolver(
                    hv, current_lines, fuzzy_candidates, decision, "fuzzy"
                )
            if chosen is not None:
                similarity = next(
                    (score for pos_, score in fuzzy_candidates if pos_ == chosen), None
                )
                current_lines, success = _apply(
                    current_lines, hv, decision, chosen, similarity, None
                )
                if success:
                    applied_count += 1
                decisions.append(decision)
                continue
            if decision.strategy == "manual" and not decision.message:
                decision.strategy = "failed"
                decision.message = "Applicazione annullata per ambiguità fuzzy."
            decisions.append(decision)
            continue

        context_lines = hv.context_lines
        context_candidates: List[Tuple[int, float]] = []
        if context_lines:
            context_candidates = find_candidates(
                current_lines, context_lines, threshold=threshold
            )
        if context_candidates:
            decision.strategy = "manual"
            decision.candidates = context_candidates
            chosen = None
            if manual_resolver is not None:
                chosen = manual_resolver(
                    hv, current_lines, context_candidates, decision, "context"
                )
            if chosen is not None:
                similarity = next(
                    (score for pos_, score in context_candidates if pos_ == chosen),
                    None,
                )
                current_lines, success = _apply(
                    current_lines, hv, decision, chosen, similarity, None
                )
                if success:
                    applied_count += 1
                decisions.append(decision)
                continue
            if decision.strategy == "manual" and not decision.message:
                decision.strategy = "failed"
                decision.message = "Applicazione annullata (solo contesto)."
                logger.info(
                    "Applicazione annullata per hunk %s: solo contesto", hv.header
                )
            decisions.append(decision)
            continue

        if not hv.before_lines and not context_candidates:
            fallback_pos: Optional[int] = None
            target_start = getattr(hunk, "target_start", None)
            source_start = getattr(hunk, "source_start", None)
            if isinstance(target_start, int):
                fallback_pos = max(0, min(len(current_lines), target_start - 1))
            elif isinstance(source_start, int):
                fallback_pos = max(0, min(len(current_lines), source_start - 1))
            if fallback_pos is not None:
                logger.debug(
                    "Uso metadati del hunk per determinare la posizione di inserimento: %d",
                    fallback_pos,
                )
                current_lines, success = _apply(
                    current_lines,
                    hv,
                    decision,
                    fallback_pos,
                    None,
                    "metadata",
                )
                if success:
                    applied_count += 1
                decisions.append(decision)
                continue

        decision.strategy = "failed"
        if not decision.message:
            decision.message = (
                "Nessun candidato compatibile trovato sopra la soglia impostata."
            )
        logger.info("Hunk %s fallito: %s", hv.header, decision.message)
        decisions.append(decision)

    logger.debug(
        "Applicazione hunk completata: %d/%d applicati", applied_count, len(hunks)
    )
    return current_lines, decisions, applied_count


def find_file_candidates(
    project_root: Path,
    rel_path: str,
    *,
    exclude_dirs: Sequence[str] = DEFAULT_EXCLUDE_DIRS,
) -> List[Path]:
    """Return possible file matches for ``rel_path`` relative to ``project_root``."""

    rel = rel_path.strip()
    if rel.startswith("a/") or rel.startswith("b/"):
        rel = rel[2:]
    if not rel:
        logger.debug("Percorso relativo vuoto, nessun candidato")
        return []

    root_resolved = project_root.resolve()

    exact_candidate = project_root / rel
    if exact_candidate.exists():
        try:
            resolved = exact_candidate.resolve()
        except FileNotFoundError:  # pragma: no cover - race condition on deletion
            resolved = exact_candidate.resolve(strict=False)

        if not resolved.is_file():
            logger.debug("Il percorso %s non è un file, ignorato", resolved)
        else:
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                logger.warning(
                    "Percorso fuori dalla radice del progetto ignorato: %s", resolved
                )
            else:
                logger.debug("Corrispondenza esatta trovata per %s", rel)
                return [resolved]

    name = Path(rel).name

    normalized_excludes: List[Tuple[str, ...]] = []
    for raw in exclude_dirs:
        if not raw:
            continue
        parts = tuple(part for part in Path(raw).parts if part not in (".", ""))
        if parts:
            normalized_excludes.append(parts)

    def should_exclude(path: Path) -> bool:
        try:
            relative = path.relative_to(project_root)
        except ValueError:
            return False
        rel_parts = relative.parts[:-1]
        if not rel_parts or not normalized_excludes:
            return False
        for pattern in normalized_excludes:
            if len(pattern) == 1:
                if pattern[0] in rel_parts:
                    return True
            else:
                window = len(pattern)
                for idx in range(len(rel_parts) - window + 1):
                    if rel_parts[idx : idx + window] == pattern:
                        return True
        return False

    matches = [
        p for p in project_root.rglob(name) if p.is_file() and not should_exclude(p)
    ]
    if not matches:
        logger.info("Nessun file trovato per %s", rel)
        return []

    suffix_matches = []
    for path in matches:
        try:
            relative = path.relative_to(project_root)
        except ValueError:
            continue
        if str(relative).endswith(rel):
            suffix_matches.append(path)
    if len(suffix_matches) == 1:
        logger.debug("Match per suffisso unico trovato: %s", suffix_matches[0])
        return suffix_matches

    logger.debug("Trovati %d candidati per %s", len(matches), rel)
    return sorted(matches)


def prepare_backup_dir(
    project_root: Path,
    *,
    dry_run: bool,
    backup_base: Optional[Path] = None,
    started_at: Optional[float] = None,
) -> Path:
    """Return a timestamped backup directory for the session.

    When ``started_at`` is provided the directory will match the session timestamp.
    Otherwise the current time is used with millisecond precision to avoid
    collisions between multiple runs that start within the same second.
    """

    base = (
        backup_base.expanduser() if backup_base is not None else default_backup_base()
    )
    timestamp = format_session_timestamp(
        started_at if started_at is not None else time.time()
    )
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

    default_report_dir = default_session_report_dir(session.started_at)

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
    resolved_targets: list[Path] = []

    if write_json:
        json_target = _resolve_path(json_path, default_report_dir / REPORT_JSON)
        resolved_targets.append(json_target)
    if write_txt:
        txt_target = _resolve_path(txt_path, default_report_dir / REPORT_TXT)
        resolved_targets.append(txt_target)

    def _is_within_directory(path: Path, directory: Path) -> bool:
        try:
            resolved_path = path.expanduser().resolve()
            resolved_directory = directory.expanduser().resolve()
        except (RuntimeError, OSError):
            return False
        try:
            resolved_path.relative_to(resolved_directory)
        except ValueError:
            return False
        return True

    if (not session.dry_run) or any(
        _is_within_directory(target, session.backup_dir) for target in resolved_targets
    ):
        session.backup_dir.mkdir(parents=True, exist_ok=True)

    if json_target is not None:
        json_target.parent.mkdir(parents=True, exist_ok=True)
        json_target.write_text(
            json.dumps(session.to_json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if txt_target is not None:
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
