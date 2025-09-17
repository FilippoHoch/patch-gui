"""Command-line helpers to apply unified diff patches without launching the GUI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Sequence

from .executor import CLIError, apply_patchset, load_patch, session_completed
from .localization import gettext as _
from .parser import build_parser, parse_exclude_dirs

__all__ = [
    "CLIError",
    "apply_patchset",
    "build_parser",
    "load_patch",
    "run_cli",
]


logger = logging.getLogger(__name__)


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and execute the CLI workflow."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.no_report and (args.report_json or args.report_txt):
        parser.error(
            _(
                "The --report-json/--report-txt options are incompatible with --no-report."
            )
        )

    level_name = args.log_level.upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.WARNING),
        format="%(levelname)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )

    try:
        patch = load_patch(args.patch, encoding=args.encoding)
        raw_backup = args.backup
        backup_base = (
            Path(raw_backup).expanduser()
            if isinstance(raw_backup, str) and raw_backup
            else None
        )
        exclude_dirs = parse_exclude_dirs(
            args.exclude_dirs, ignore_default=args.no_default_exclude
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
                details.append(_("JSON: {path}").format(path=session.report_json_path))
            if session.report_txt_path:
                details.append(_("Text: {path}").format(path=session.report_txt_path))
            print(_("Reports saved to: {details}").format(details=", ".join(details)))
        else:
            print(_("Reports disabled (--no-report)"))

    return 0 if session_completed(session) else 1
