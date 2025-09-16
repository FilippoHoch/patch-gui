"""Command-line helpers to apply unified diff patches without launching the GUI."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

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

_LOG_LEVEL_CHOICES = ("critical", "error", "warning", "info", "debug")

__all__ = [
    "CLIError",
    "apply_patchset",
    "build_parser",
    "load_patch",
    "run_cli",
]


logger = logging.getLogger(__name__)


class CLIError(Exception):
    """Raised for recoverable CLI usage errors."""


def build_parser(parser: Optional[argparse.ArgumentParser] = None) -> argparse.ArgumentParser:
    """Create or enrich an ``ArgumentParser`` with CLI options."""

    if parser is None:
        parser = argparse.ArgumentParser(
            prog="patch-gui apply",
            description=(
                f"{APP_NAME}: applica una patch unified diff usando le stesse euristiche "
                "della GUI, ma dalla riga di comando."
            ),
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
    else:
        parser.description = (
            f"{APP_NAME}: applica una patch unified diff usando le stesse euristiche "
            "della GUI, ma dalla riga di comando."
        )
        parser.formatter_class = argparse.ArgumentDefaultsHelpFormatter
    parser.add_argument(
        "patch",
        help="Percorso del file diff da applicare (usa '-' per leggere da STDIN).",
    )
    parser.add_argument(
        "--root",
        required=True,
        help="Root del progetto su cui applicare la patch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula l'applicazione senza modificare i file o creare backup.",
    )
    parser.add_argument(
        "--threshold",
        type=_threshold_value,
        default=0.85,
        help="Soglia (0-1) per il matching fuzzy del contesto.",
    )
    parser.add_argument(
        "--backup",
        help=(
            "Cartella base per backup e report; di default viene utilizzato "
            "'<root>/%s'." % BACKUP_DIR
        ),
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help=(
            "Disabilita le richieste interattive su STDIN e mantiene il "
            "comportamento precedente in caso di ambiguità."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=_LOG_LEVEL_CHOICES,
        help=(
            "Livello di logging da inviare su stdout (debug, info, warning, error, critical)."
        ),
    )
    return parser


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
) -> ApplySession:
    """Apply ``patch`` to ``project_root`` and return the :class:`ApplySession`."""

    root = project_root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise CLIError(f"Root del progetto non valida: {project_root}")

    backup_dir = _prepare_backup_dir(root, backup_base, dry_run)
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
        _write_reports(session)

    return session


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and execute the CLI workflow."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    level_name = args.log_level.upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.WARNING),
        format="%(levelname)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )

    try:
        patch = load_patch(args.patch)
        backup_base = Path(args.backup).expanduser() if args.backup else None
        session = apply_patchset(
            patch,
            Path(args.root),
            dry_run=args.dry_run,
            threshold=args.threshold,
            backup_base=backup_base,
            interactive=not args.non_interactive,
        )
    except CLIError as exc:
        parser.exit(1, f"Errore: {exc}\n")

    print(session.to_txt())
    if args.dry_run:
        print("\nModalità dry-run: nessun file è stato modificato e non sono stati creati backup.")
    else:
        print(f"\nBackup e report salvati in: {session.backup_dir}")

    return 0 if _session_completed(session) else 1


def _threshold_value(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:  # pragma: no cover - argparse already handles typical errors
        raise argparse.ArgumentTypeError("La soglia deve essere un numero decimale.") from exc
    if not 0 < parsed <= 1:
        raise argparse.ArgumentTypeError("La soglia deve essere compresa tra 0 (escluso) e 1 (incluso).")
    return parsed


def _prepare_backup_dir(project_root: Path, backup_base: Optional[Path], dry_run: bool) -> Path:
    base = backup_base if backup_base is not None else project_root / BACKUP_DIR
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = base / timestamp
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def _relative_path_from_patch(pf) -> str:
    rel = pf.path or pf.target_file or pf.source_file or ""
    return rel.strip()


def _apply_file_patch(
    project_root: Path,
    pf,
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

    candidates = list(_locate_candidates(project_root, rel_path))
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
        _backup_file(project_root, path, session.backup_dir)

    modified = False

    for hunk in pf:
        hv = build_hunk_view(hunk)
        decision = HunkDecision(hunk_header=hv.header, strategy="")

        applied = _try_apply_hunk(lines, hv, decision, session, exact_threshold=1.0)
        if applied is not None:
            lines, success = applied
            if success:
                fr.hunks_applied += 1
                modified = True
            fr.decisions.append(decision)
            continue

        applied = _try_apply_hunk(lines, hv, decision, session, exact_threshold=session.threshold)
        if applied is not None:
            lines, success = applied
            if success:
                fr.hunks_applied += 1
                modified = True
            fr.decisions.append(decision)
            continue

        context_lines = [ln for ln in hv.before_lines if not ln.startswith(("+", "-"))]
        cand = find_candidates(lines, context_lines, threshold=session.threshold)
        if cand:
            decision.strategy = "ambiguous"
            decision.candidates = cand
            decision.message = (
                "Solo il contesto coincide. Usa la GUI o regola la soglia per applicare questo hunk."
            )
            fr.decisions.append(decision)
            continue

        decision.strategy = "failed"
        decision.message = "Nessun candidato compatibile trovato sopra la soglia impostata."
        fr.decisions.append(decision)

    if not session.dry_run and modified:
        new_text = "".join(lines).replace("\n", orig_eol)
        write_text_preserving_encoding(path, new_text, file_encoding)

    return fr


def _try_apply_hunk(
    lines: List[str],
    hv: HunkView,
    decision: HunkDecision,
    session: ApplySession,
    *,
    exact_threshold: float,
) -> Optional[Tuple[List[str], bool]]:
    candidates = find_candidates(lines, hv.before_lines, threshold=exact_threshold)
    if not candidates:
        return None
    if len(candidates) > 1 and exact_threshold < 1.0:
        decision.strategy = "ambiguous"
        decision.candidates = candidates
        decision.message = (
            "Più posizioni trovate sopra la soglia. La CLI non può scegliere automaticamente."
        )
        return (lines, False)

    pos, score = candidates[0]
    try:
        new_lines = apply_hunk_at_position(lines, hv, pos)
    except Exception as exc:  # pragma: no cover - safeguard against unexpected errors
        decision.strategy = "failed"
        decision.message = f"Errore durante l'applicazione del hunk: {exc}"
        return (lines, False)

    decision.strategy = "exact" if exact_threshold == 1.0 else "fuzzy"
    decision.selected_pos = pos
    decision.similarity = score
    return (new_lines, True)


def _locate_candidates(project_root: Path, rel_path: str) -> Iterable[Path]:
    rel = rel_path.strip()
    if rel.startswith("a/") or rel.startswith("b/"):
        rel = rel[2:]
    if not rel:
        return []

    exact = project_root / rel
    if exact.exists():
        return [exact]

    name = Path(rel).name
    matches = [p for p in project_root.rglob(name) if p.is_file()]
    if not matches:
        return []

    suffix_matches = [p for p in matches if str(p.relative_to(project_root)).endswith(rel)]
    if len(suffix_matches) == 1:
        return suffix_matches
    return sorted(matches)


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


def _backup_file(project_root: Path, path: Path, backup_root: Path) -> None:
    rel = path.relative_to(project_root)
    dest = backup_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def _write_reports(session: ApplySession) -> None:
    session.backup_dir.mkdir(parents=True, exist_ok=True)
    (session.backup_dir / REPORT_JSON).write_text(
        json.dumps(session.to_json(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (session.backup_dir / REPORT_TXT).write_text(session.to_txt(), encoding="utf-8")


def _session_completed(session: ApplySession) -> bool:
    for fr in session.results:
        if fr.skipped_reason:
            return False
        if fr.hunks_total and fr.hunks_applied != fr.hunks_total:
            return False
    return True
