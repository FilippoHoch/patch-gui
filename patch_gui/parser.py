"""Helpers for building and handling the CLI argument parser."""

from __future__ import annotations

import argparse
from typing import List, Optional, Sequence

from .localization import gettext as _
from .patcher import DEFAULT_EXCLUDE_DIRS
from .utils import (
    APP_NAME,
    REPORT_JSON,
    REPORT_TXT,
    default_backup_base,
    display_path,
)

_LOG_LEVEL_CHOICES = ("critical", "error", "warning", "info", "debug")

__all__ = [
    "_LOG_LEVEL_CHOICES",
    "build_parser",
    "parse_exclude_dirs",
    "threshold_value",
]


def build_parser(
    parser: Optional[argparse.ArgumentParser] = None,
) -> argparse.ArgumentParser:
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
        type=threshold_value,
        default=0.85,
        help=_("Matching threshold (0-1) for fuzzy context alignment."),
    )
    parser.add_argument(
        "--backup",
        help=_('Base directory for backups and reports; defaults to "{path}".').format(
            path=display_path(default_backup_base())
        ),
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
        "--encoding",
        default=None,
        help=_(
            "Explicit encoding to use when reading the diff (default: auto-detect)."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=_LOG_LEVEL_CHOICES,
        help=_(
            "Logging level to emit on stdout (debug, info, warning, error, critical)."
        ),
    )
    parser.add_argument(
        "--exclude-dir",
        dest="exclude_dirs",
        action="append",
        metavar="NAME",
        help=_(
            "Directory (relative to the root) to ignore while searching for files. "
            "Specify the option multiple times to provide more than one. Defaults: %s."
        )
        % ", ".join(DEFAULT_EXCLUDE_DIRS),
    )
    parser.add_argument(
        "--no-default-exclude",
        action="store_true",
        help=_(
            "Do not ignore the default directories (e.g. %s). Use together with "
            "--exclude-dir to specify an explicit allowlist."
        )
        % ", ".join(DEFAULT_EXCLUDE_DIRS),
    )
    return parser


def threshold_value(value: str) -> float:
    try:
        parsed = float(value)
    except (
        ValueError
    ) as exc:  # pragma: no cover - argparse already handles typical errors
        raise argparse.ArgumentTypeError(
            _("Threshold must be a decimal number.")
        ) from exc
    if not 0 < parsed <= 1:
        raise argparse.ArgumentTypeError(
            _("Threshold must be between 0 (exclusive) and 1 (inclusive).")
        )
    return parsed


def parse_exclude_dirs(
    values: Sequence[str] | None,
    *,
    ignore_default: bool = False,
) -> tuple[str, ...]:
    if not values:
        return tuple() if ignore_default else DEFAULT_EXCLUDE_DIRS
    parsed: List[str] = []
    for raw in values:
        for item in raw.split(","):
            normalized = item.strip()
            if normalized:
                parsed.append(normalized)
    if not parsed:
        return tuple() if ignore_default else DEFAULT_EXCLUDE_DIRS
    # Remove duplicates preserving order
    return tuple(dict.fromkeys(parsed))
