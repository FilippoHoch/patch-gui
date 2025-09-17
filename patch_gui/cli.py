"""Command-line helpers to apply unified diff patches without launching the GUI."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from .localization import gettext as _
from .patcher import (
    ApplySession,
    FileResult,
    HunkDecision,
    HunkView,
    DEFAULT_EXCLUDE_DIRS,
    apply_hunks,
    backup_file,
    find_file_candidates,
    prepare_backup_dir,
    write_reports,
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

    description = _(
        "{app_name}: apply a unified diff patch using the same heuristics as the GUI, "
        "but from the command line."
    ).format(app_name=APP_NAME)
    if parser is None:
        parser = argparse.ArgumentParser(
            prog="patch-gui apply",
            description=description,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
    else:
        parser.description = description
        parser.formatter_class = argparse.ArgumentDefaultsHelpFormatter
    parser.add_argument(
        "patch",
        help=_("Path to the diff file to apply ('-' reads from STDIN)."),
    )
    parser.add_argument(
        "--root",
        required=True,
        help=_("Project root where the patch should be applied."),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=_("Simulate the execution without modifying files or creating backups."),
    )
    parser.add_argument(
        "--threshold",
        type=_threshold_value,
        default=0.85,
        help=_("Matching threshold (0-1) for fuzzy context alignment."),
    )
    parser.add_argument(
        "--backup",
        help=_("Base directory for backups and reports; defaults to '<root>/%s'.")
        % BACKUP_DIR,
    )
    parser.add_argument(
        "--report-json",
        help=_("Path of the generated JSON report; defaults to '<backup>/%s'.")
        % REPORT_JSON,
    )
    parser.add_argument(
        "--report-txt",
        help=_("Path of the generated text report; defaults to '<backup>/%s'.")
        % REPORT_TXT,
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help=_("Do not create JSON/TXT report files."),
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help=(
            _(
                "Disable interactive prompts on STDIN and keep the historical behaviour "
                "when multiple matches exist."
            )
        ),
    )
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=_LOG_LEVEL_CHOICES,
        help=_("Logging level to emit on stdout (debug, info, warning, error, critical)."),
    )
    parser.add_argument(
        "--exclude-dir",
        dest="exclude_dirs",
        action="append",
        metavar="NAME",
        help=(
            "Directory (relative alla root) da ignorare durante la ricerca dei file. "
            "Specificare l'opzione più volte per indicarne più di una. Predefinite: %s."
            % ", ".join(DEFAULT_EXCLUDE_DIRS)
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
            raise CLIError(_("Diff file not found: {path}").format(path=path))
        try:
            raw = path.read_bytes()
            text, encoding, used_fallback = decode_bytes(raw)
            if used_fallback:
                logger.warning(
                    _(
                        "Decoded diff %s using fallback UTF-8 (original encoding %s); "
                        "the content may contain substituted characters."
                    ),
                    path,
                    encoding,
                )
        except Exception as exc:  # pragma: no cover - extremely rare I/O error types
            raise CLIError(_("Cannot read {path}: {error}").format(path=path, error=exc)) from exc

    processed = preprocess_patch_text(text)
    try:
        patch = PatchSet(processed)
    except UnidiffParseError as exc:
        raise CLIError(_("Invalid diff: {error}").format(error=exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guard for unexpected errors
        raise CLIError(_("Unexpected error while parsing the diff: {error}").format(error=exc)) from exc
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
    exclude_dirs: Sequence[str] | None = None,
) -> ApplySession:
    """Apply ``patch`` to ``project_root`` and return the :class:`ApplySession`."""

    root = project_root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise CLIError(_("Invalid project root: {path}").format(path=project_root))

    backup_dir = prepare_backup_dir(root, dry_run=dry_run, backup_base=backup_base)
    resolved_excludes = tuple(exclude_dirs) if exclude_dirs is not None else DEFAULT_EXCLUDE_DIRS

    session = ApplySession(
        project_root=root,
        backup_dir=backup_dir,
        dry_run=dry_run,
        threshold=threshold,
        exclude_dirs=resolved_excludes,
        started_at=time.time(),
    )

    for pf in patch:
        rel = _relative_path_from_patch(pf)
        fr = _apply_file_patch(root, pf, rel, session, interactive=interactive)
        session.results.append(fr)

    _write_reports(
        session,
        report_json=report_json,
        report_txt=report_txt,
        enable_reports=write_report_files,
    )

    return session


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and execute the CLI workflow."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.no_report and (args.report_json or args.report_txt):
        parser.error(
            _("The --report-json/--report-txt options are incompatible with --no-report.")
        )

    level_name = args.log_level.upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.WARNING),
        format="%(levelname)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )

    try:
        patch = load_patch(args.patch)
        raw_backup = args.backup
        backup_base = (
            Path(raw_backup).expanduser() if isinstance(raw_backup, str) and raw_backup else None
        )
        exclude_dirs = _parse_exclude_dirs(args.exclude_dirs)
        session = apply_patchset(
            patch,
            Path(args.root),
            dry_run=args.dry_run,
            threshold=args.threshold,
            backup_base=backup_base,
            interactive=not args.non_interactive,
            report_json=args.report_json,
            report_txt=args.report_txt,
            write_report_files=not args.no_report,
            exclude_dirs=exclude_dirs,
        )
    except CLIError as exc:
        parser.exit(1, _("Error: {message}\n").format(message=exc))

    print(session.to_txt())
    if args.dry_run:
        print(_("\nDry-run mode: no files were modified and no backups were created."))
    else:
        print(_("\nBackups saved to: {path}").format(path=session.backup_dir))
        if session.report_json_path or session.report_txt_path:
            details = []
            if session.report_json_path:
                details.append(
                    _("JSON: {path}").format(path=session.report_json_path)
                )
            if session.report_txt_path:
                details.append(_("Text: {path}").format(path=session.report_txt_path))
            print(_("Reports saved to: {details}").format(details=", ".join(details)))
        else:
            print(_("Reports disabled (--no-report)"))

    return 0 if _session_completed(session) else 1


def _threshold_value(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:  # pragma: no cover - argparse already handles typical errors
        raise argparse.ArgumentTypeError(_("Threshold must be a decimal number.")) from exc
    if not 0 < parsed <= 1:
        raise argparse.ArgumentTypeError(
            _("Threshold must be between 0 (exclusive) and 1 (inclusive).")
        )
    return parsed


def _parse_exclude_dirs(values: Sequence[str] | None) -> tuple[str, ...]:
    if not values:
        return DEFAULT_EXCLUDE_DIRS
    parsed: List[str] = []
    for raw in values:
        for item in raw.split(","):
            normalized = item.strip()
            if normalized:
                parsed.append(normalized)
    if not parsed:
        return DEFAULT_EXCLUDE_DIRS
    # Remove duplicates preserving order
    return tuple(dict.fromkeys(parsed))


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
        fr.skipped_reason = _("Binary patches are not supported in CLI mode")
        return fr

    candidates = find_file_candidates(
        project_root,
        rel_path,
        exclude_dirs=session.exclude_dirs,
    )
    if not candidates:
        fr.skipped_reason = _("File not found in the project root")
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
        fr.skipped_reason = _("Cannot read the file: {error}").format(error=exc)
        return fr

    content, file_encoding, used_fallback = decode_bytes(raw)
    if used_fallback:
        logger.warning(
            _(
                "Decoded file %s using fallback UTF-8 (original encoding %s); "
                "some characters may be substituted."
            ),
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

    print(_("Multiple files match the patch path:"))
    for idx, value in enumerate(display_paths, start=1):
        print(f"  {idx}) {value}")
    prompt = _(
        "Select the number of the file to use (1-{count}). Press Enter or type 's' to skip: "
    ).format(count=len(candidates))

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
            print(_("Invalid input. Enter a number or leave empty to cancel."))
            continue

        if 1 <= index <= len(candidates):
            return candidates[index - 1]

        print(_("Number out of range. Try again."))


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
        shown.append(_("… (+{count} more)").format(count=remaining))
    joined = ", ".join(shown)
    return _(
        "Multiple files found for the provided path; resolve the ambiguity manually. "
        "Candidates: {candidates}"
    ).format(candidates=joined)


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
        decision.message = _(
            "Multiple candidate positions scored above the threshold. The CLI cannot "
            "choose automatically."
        )
    else:
        decision.message = _(
            "Only the context matches. Use the GUI or adjust the threshold to apply this "
            "hunk."
        )
    return None


def _session_completed(session: ApplySession) -> bool:
    for fr in session.results:
        if fr.skipped_reason:
            return False
        if fr.hunks_total and fr.hunks_applied != fr.hunks_total:
            return False
    return True


def _write_reports(
    session: ApplySession,
    *,
    report_json: Path | str | None,
    report_txt: Path | str | None,
    enable_reports: bool,
) -> tuple[Optional[Path], Optional[Path]]:
    if not enable_reports:
        session.report_json_path = None
        session.report_txt_path = None
        return None, None

    json_path = _coerce_report_path(report_json)
    txt_path = _coerce_report_path(report_txt)

    written = write_reports(
        session,
        json_path=json_path,
        txt_path=txt_path,
        write_json=True,
        write_txt=True,
    )
    session.report_json_path, session.report_txt_path = written
    return written


def _coerce_report_path(value: Path | str | None) -> Optional[Path]:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.expanduser()
    cleaned = value.strip()
    if not cleaned:
        return None
    return Path(cleaned).expanduser()
