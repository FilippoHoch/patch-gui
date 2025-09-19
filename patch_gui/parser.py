"""Helpers for building and handling the CLI argument parser."""

from __future__ import annotations

import argparse
from typing import List, Optional, Sequence

from ._version import __version__
from .config import AppConfig, load_config
from .localization import gettext as _
from .patcher import DEFAULT_EXCLUDE_DIRS
from .utils import (
    APP_NAME,
    REPORT_JSON,
    REPORT_TXT,
    display_path,
)

_LOG_LEVEL_CHOICES = ("critical", "error", "warning", "info", "debug")
# Minimum width dedicated to the help text itself (excluding the option column).
_MINIMUM_HELP_WIDTH = 80


class _HelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    """Help formatter that keeps ample width for long descriptions."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=36)
        minimum_total_width = self._max_help_position + _MINIMUM_HELP_WIDTH
        self._width = max(self._width, minimum_total_width)


REPORT_JSON_UNSET = object()
REPORT_TXT_UNSET = object()


__all__ = [
    "_LOG_LEVEL_CHOICES",
    "REPORT_JSON_UNSET",
    "REPORT_TXT_UNSET",
    "build_parser",
    "parse_exclude_dirs",
    "threshold_value",
]


def build_parser(
    parser: Optional[argparse.ArgumentParser] = None,
    *,
    config: AppConfig | None = None,
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
            formatter_class=_HelpFormatter,
        )
    else:
        parser.description = description
        parser.formatter_class = _HelpFormatter
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
        help=_("Show the version number and exit."),
    )
    parser.add_argument(
        "patch",
        help=_("Path to the diff file to apply ('-' reads from STDIN)."),
    )
    parser.add_argument(
        "--root",
        required=True,
        help=_("Project root where the patch should be applied."),
    )
    resolved_config = config or load_config()
    dry_run_group = parser.add_mutually_exclusive_group()
    dry_run_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help=(
            _(
                "Simulate the execution without modifying files or creating backups"
                " (default follows the configuration)."
            )
        ),
    )
    dry_run_group.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help=_(
            "Apply changes even when dry-run mode is enabled in the configuration."
        ),
    )
    parser.set_defaults(dry_run=resolved_config.dry_run_default)
    parser.add_argument(
        "--threshold",
        type=threshold_value,
        default=resolved_config.threshold,
        help=_("Matching threshold (0-1) for fuzzy context alignment."),
    )
    parser.add_argument(
        "--backup",
        help=_('Base directory for backups and reports; defaults to "{path}".').format(
            path=display_path(resolved_config.backup_base)
        ),
    )
    parser.add_argument(
        "--report-json",
        default=REPORT_JSON_UNSET,
        help=_("Path of the generated JSON report; defaults to '<backup>/%s'.")
        % REPORT_JSON,
    )
    parser.add_argument(
        "--report-txt",
        default=REPORT_TXT_UNSET,
        help=_("Path of the generated text report; defaults to '<backup>/%s'.")
        % REPORT_TXT,
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help=_("Do not create JSON/TXT report files."),
    )
    parser.add_argument(
        "--summary-format",
        action="append",
        choices=("text", "json", "none"),
        help=_(
            "Choose one or more summary formats to print on stdout (defaults to text). "
            "Repeat the option to combine formats; use 'none' to suppress summaries."
        ),
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
        "--auto-accept",
        action="store_true",
        help=_(
            "Automatically accept the best candidate when manual intervention would "
            "normally be required. Can be combined with --non-interactive to avoid "
            "prompts entirely."
        ),
    )
    ai_group = parser.add_mutually_exclusive_group()
    ai_group.add_argument(
        "--ai-assistant",
        dest="ai_assistant",
        action="store_true",
        help=_(
            "Enable the AI assistant when ranking ambiguous hunk candidates (overrides the configuration)."
        ),
    )
    ai_group.add_argument(
        "--no-ai-assistant",
        dest="ai_assistant",
        action="store_false",
        help=_(
            "Disable the AI assistant for candidate ranking (overrides the configuration)."
        ),
    )
    parser.set_defaults(ai_assistant=resolved_config.ai_assistant_enabled)
    ai_select_group = parser.add_mutually_exclusive_group()
    ai_select_group.add_argument(
        "--ai-select",
        dest="ai_select",
        action="store_true",
        help=_(
            "Automatically choose the candidate suggested by the assistant when manual selection is required."
        ),
    )
    ai_select_group.add_argument(
        "--no-ai-select",
        dest="ai_select",
        action="store_false",
        help=_("Disable automatic application of the assistant suggestion."),
    )
    parser.set_defaults(ai_select=resolved_config.ai_auto_apply)
    parser.add_argument(
        "--encoding",
        default=None,
        help=_(
            "Explicit encoding to use when reading the diff (default: auto-detect)."
        ),
    )
    parser.add_argument(
        "--log-level",
        default=resolved_config.log_level,
        choices=_LOG_LEVEL_CHOICES,
        help=_(
            "Logging level to emit on stdout (debug, info, warning, error, critical)."
        ),
    )
    resolved_exclude_defaults = tuple(
        resolved_config.exclude_dirs or DEFAULT_EXCLUDE_DIRS
    )
    resolved_exclude_defaults_text = ", ".join(resolved_exclude_defaults)
    parser.add_argument(
        "--exclude-dir",
        dest="exclude_dirs",
        action="append",
        metavar="NAME",
        help=_(
            "Directory (relative to the root) to ignore while searching for files. "
            "Specify the option multiple times to provide more than one. Defaults: %s."
        )
        % resolved_exclude_defaults_text,
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
    default_excludes: Sequence[str] | None = None,
) -> tuple[str, ...]:
    defaults = (
        tuple(default_excludes)
        if default_excludes is not None
        else DEFAULT_EXCLUDE_DIRS
    )
    if not values:
        return tuple() if ignore_default else defaults
    parsed: List[str] = []
    for raw in values:
        for item in raw.split(","):
            normalized = item.strip()
            if normalized:
                parsed.append(normalized)
    if not parsed:
        return tuple() if ignore_default else defaults
    # Remove duplicates preserving order
    return tuple(dict.fromkeys(parsed))
