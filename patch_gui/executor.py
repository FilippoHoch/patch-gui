"""Execution helpers for applying unified diff patches via the CLI."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from .patcher import (
    ApplySession,
    FileResult,
    HunkDecision,
    HunkView,
    apply_hunks,
    backup_file,
    find_file_candidates,
    prepare_backup_dir,
)
from .reporting import write_session_reports
from .utils import (
    decode_bytes,
    normalize_newlines,
    preprocess_patch_text,
    write_text_preserving_encoding,
)

__all__ = ["CLIError", "apply_patchset", "load_patch", "session_completed"]

logger = logging.getLogger(__name__)


class CLIError(Exception):
    """Raised for recoverable CLI usage errors."""


def load_patch(source: str) -> PatchSet:
    """Load and parse a diff/patch file from ``source`` (path or ``'-'`` for stdin)."""

    if source == "-":
        text = sys.stdin.read()
    else:
        path = Path(source)
        if not path.exists():
            raise CLIError(f"File diff non trovato: {path}")
        try:
            raw = path.read_bytes()
            text, encoding, used_fallback = decode_bytes(raw)
            if used_fallback:
                logger.warning(
                    "Decodifica del diff %s eseguita con fallback UTF-8 (encoding %s); "
                    "il contenuto potrebbe contenere caratteri sostituiti.",
                    path,
                    encoding,
                )
        except Exception as exc:  # pragma: no cover - extremely rare I/O error types
            raise CLIError(f"Impossibile leggere {path}: {exc}") from exc

    processed = preprocess_patch_text(text)
    try:
        patch = PatchSet(processed)
    except UnidiffParseError as exc:
        raise CLIError(f"Diff non valido: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive guard for unexpected errors
        raise CLIError(f"Errore imprevisto nel parsing del diff: {exc}") from exc
    return patch


def apply_patchset(
    patch: PatchSet,
    project_root: Path,
    *,
    dry_run: bool,
    threshold: float,
    backup_base: Optional[Path] = None,
    interactive: bool = True,
    report_json: Path | str | None = None,
    report_txt: Path | str | None = None,
    write_report_files: bool = True,
) -> ApplySession:
    """Apply ``patch`` to ``project_root`` and return the :class:`ApplySession`."""

    root = project_root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise CLIError(f"Root del progetto non valida: {project_root}")

    backup_dir = prepare_backup_dir(root, dry_run=dry_run, backup_base=backup_base)
    session = ApplySession(
        project_root=root,
        backup_dir=backup_dir,
        dry_run=dry_run,
        threshold=threshold,
        started_at=time.time(),
    )

    for pf in patch:
        rel = _relative_path_from_patch(pf)
        fr = _apply_file_patch(root, pf, rel, session, interactive=interactive)
        session.results.append(fr)

    if not dry_run:
        write_session_reports(
            session,
            report_json=report_json,
            report_txt=report_txt,
            enable_reports=write_report_files,
        )

    return session


def session_completed(session: ApplySession) -> bool:
    for fr in session.results:
        if fr.skipped_reason:
            return False
        if fr.hunks_total and fr.hunks_applied != fr.hunks_total:
            return False
    return True


def _relative_path_from_patch(pf: Any) -> str:
    rel = pf.path or pf.target_file or pf.source_file or ""
    return rel.strip()


def _apply_file_patch(
    project_root: Path,
    pf: Any,
    rel_path: str,
    session: ApplySession,
    *,
    interactive: bool,
) -> FileResult:
    fr = FileResult(file_path=Path(), relative_to_root=rel_path)
    fr.hunks_total = len(pf)

    if getattr(pf, "is_binary_file", False):
        fr.skipped_reason = "Patch binaria non supportata in modalità CLI"
        return fr

    candidates = find_file_candidates(project_root, rel_path)
    if not candidates:
        fr.skipped_reason = "File non trovato nella root del progetto"
        return fr
    if len(candidates) > 1:
        if not interactive:
            fr.skipped_reason = _ambiguous_paths_message(project_root, candidates)
            return fr
        selected = _prompt_candidate_selection(project_root, candidates)
        if selected is None:
            fr.skipped_reason = _ambiguous_paths_message(project_root, candidates)
            return fr
        path = selected
    else:
        path = candidates[0]
    fr.file_path = path
    try:
        fr.relative_to_root = str(path.relative_to(project_root))
    except ValueError:
        fr.relative_to_root = str(path)

    try:
        raw = path.read_bytes()
    except Exception as exc:
        fr.skipped_reason = f"Impossibile leggere il file: {exc}"
        return fr

    content, file_encoding, used_fallback = decode_bytes(raw)
    if used_fallback:
        logger.warning(
            "Decodifica del file %s eseguita con fallback UTF-8 (encoding %s); "
            "alcuni caratteri potrebbero essere sostituiti.",
            path,
            file_encoding,
        )
    orig_eol = "\r\n" if "\r\n" in content else "\n"
    lines = normalize_newlines(content).splitlines(keepends=True)

    if not session.dry_run:
        backup_file(project_root, path, session.backup_dir)

    lines, decisions, applied = apply_hunks(
        lines,
        pf,
        threshold=session.threshold,
        manual_resolver=_cli_manual_resolver,
    )

    fr.hunks_applied = applied
    fr.decisions.extend(decisions)

    if not session.dry_run and applied:
        new_text = "".join(lines).replace("\n", orig_eol)
        write_text_preserving_encoding(path, new_text, file_encoding)

    return fr


def _prompt_candidate_selection(project_root: Path, candidates: Sequence[Path]) -> Optional[Path]:
    display_paths: List[str] = []
    for path in candidates:
        try:
            display_paths.append(str(path.relative_to(project_root)))
        except ValueError:
            display_paths.append(str(path))

    print("Sono stati trovati più file che corrispondono al percorso della patch:")
    for idx, value in enumerate(display_paths, start=1):
        print(f"  {idx}) {value}")
    prompt = (
        f"Seleziona il numero del file da utilizzare (1-{len(candidates)}). "
        "Premi Invio o digita 's' per saltare: "
    )

    while True:
        try:
            choice = input(prompt)
        except EOFError:
            return None
        except KeyboardInterrupt:
            raise

        choice = choice.strip()
        if not choice or choice.lower() in {"s", "skip", "n", "no", "q", "quit"}:
            return None

        try:
            index = int(choice)
        except ValueError:
            print("Input non valido. Inserire un numero o lasciare vuoto per annullare.")
            continue

        if 1 <= index <= len(candidates):
            return candidates[index - 1]

        print("Numero fuori dall'intervallo indicato. Riprova.")


def _ambiguous_paths_message(project_root: Path, candidates: Sequence[Path]) -> str:
    max_display = 5
    shown: List[str] = []
    for path in candidates[:max_display]:
        try:
            shown.append(str(path.relative_to(project_root)))
        except ValueError:
            shown.append(str(path))
    remaining = len(candidates) - max_display
    if remaining > 0:
        shown.append(f"… (+{remaining} altri)")
    joined = ", ".join(shown)
    return (
        "Più file trovati per il percorso indicato; risolvi l'ambiguità manualmente. "
        f"Candidati: {joined}"
    )


def _cli_manual_resolver(
    hv: HunkView,
    lines: List[str],
    candidates: List[Tuple[int, float]],
    decision: HunkDecision,
    reason: str,
) -> Optional[int]:
    del hv, lines  # unused in CLI resolver
    decision.candidates = candidates
    decision.strategy = "ambiguous"
    if reason == "fuzzy":
        decision.message = (
            "Più posizioni trovate sopra la soglia. La CLI non può scegliere automaticamente."
        )
    else:
        decision.message = (
            "Solo il contesto coincide. Usa la GUI o regola la soglia per applicare questo hunk."
        )
    return None
