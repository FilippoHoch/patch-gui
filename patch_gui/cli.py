"""Command-line helpers to apply unified diff patches without launching the GUI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Sequence

from .executor import CLIError, apply_patchset, load_patch, session_completed
from .parser import build_parser, threshold_value

__all__ = [
    "CLIError",
    "apply_patchset",
    "build_parser",
    "load_patch",
    "run_cli",
    "session_completed",
]

# Backwards-compatibility aliases for private helpers referenced in tests or scripts.
_threshold_value = threshold_value
_session_completed = session_completed


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and execute the CLI workflow."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.no_report and (args.report_json or args.report_txt):
        parser.error(
            "Le opzioni --report-json/--report-txt non sono compatibili con --no-report."
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
        )
    except CLIError as exc:
        parser.exit(1, f"Errore: {exc}\n")

    print(session.to_txt())
    if args.dry_run:
        print("\nModalità dry-run: nessun file è stato modificato e non sono stati creati backup.")
    else:
        print(f"\nBackup salvati in: {session.backup_dir}")
        if session.report_json_path or session.report_txt_path:
            details = []
            if session.report_json_path:
                details.append(f"JSON: {session.report_json_path}")
            if session.report_txt_path:
                details.append(f"Testo: {session.report_txt_path}")
            print("Report salvati in: " + ", ".join(details))
        else:
            print("Report disattivati (--no-report)")

    return 0 if session_completed(session) else 1
