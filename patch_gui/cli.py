"""Command-line helpers to apply unified diff patches without launching the GUI."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import IO, Callable, Sequence, cast

from .config import AppConfig, load_config, save_config
from .executor import CLIError, apply_patchset, load_patch, session_completed
from .localization import gettext as _
from .parser import (
    _LOG_LEVEL_CHOICES,
    build_parser,
    parse_exclude_dirs,
    threshold_value,
)

__all__ = [
    "CLIError",
    "apply_patchset",
    "build_parser",
    "build_config_parser",
    "load_patch",
    "run_cli",
    "run_config",
    "config_show",
    "config_set",
    "config_reset",
]


logger = logging.getLogger(__name__)


class ConfigCommandError(Exception):
    """Raised when a configuration sub-command cannot be completed."""


_CONFIG_KEYS = (
    "threshold",
    "exclude_dirs",
    "backup_base",
    "log_level",
    "dry_run_default",
    "write_reports",
)


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and execute the CLI workflow."""

    config = load_config()
    parser = build_parser(config=config)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.no_report and (args.report_json or args.report_txt):
        parser.error(
            _(
                "The --report-json/--report-txt options are incompatible with --no-report."
            )
        )

    requested_formats = args.summary_format or []
    normalized_formats = [fmt.lower() for fmt in requested_formats]
    if not normalized_formats:
        normalized_formats = ["text"]
    summary_formats = list(dict.fromkeys(normalized_formats))
    print_text_summary = "text" in summary_formats
    print_json_summary = "json" in summary_formats

    level_name = args.log_level.upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.WARNING),
        format="%(levelname)s: %(message)s",
        stream=sys.stderr if print_json_summary else sys.stdout,
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
            args.exclude_dirs,
            ignore_default=args.no_default_exclude,
            default_excludes=config.exclude_dirs,
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
            write_json_report=print_json_summary,
            write_txt_report=print_text_summary,
            exclude_dirs=exclude_dirs,
            config=config,
        )
    except CLIError as exc:
        parser.exit(1, _("Error: {message}\n").format(message=exc))

    if print_text_summary:
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

    if print_json_summary:
        if print_text_summary:
            print()
        json_summary = json.dumps(session.to_json(), ensure_ascii=False, indent=2)
        print(json_summary)

    return 0 if session_completed(session) else 1


def run_config(argv: Sequence[str] | None = None) -> int:
    """Entry-point for ``patch-gui config`` sub-commands."""

    parser = build_config_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        func = cast("Callable[[argparse.Namespace], int]", getattr(args, "func"))
        return func(args)
    except ConfigCommandError as exc:
        parser.exit(1, _("Error: {message}\n").format(message=str(exc)))


def build_config_parser() -> argparse.ArgumentParser:
    """Return an ``ArgumentParser`` configured for the ``config`` commands."""

    parser = argparse.ArgumentParser(
        prog="patch-gui config",
        description=_("Inspect or modify the persistent configuration."),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser(
        "show",
        help=_("Display the current configuration values."),
    )
    show_parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help=_(
            "Override the configuration file path (default: use the standard location)."
        ),
    )
    show_parser.set_defaults(func=_run_config_show)

    set_parser = subparsers.add_parser(
        "set",
        help=_("Update a configuration key."),
    )
    set_parser.add_argument("key", choices=_CONFIG_KEYS)
    set_parser.add_argument(
        "values",
        nargs="+",
        help=_("New value for the key. Provide multiple values for exclude_dirs."),
    )
    set_parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help=_(
            "Override the configuration file path (default: use the standard location)."
        ),
    )
    set_parser.set_defaults(func=_run_config_set)

    reset_parser = subparsers.add_parser(
        "reset",
        help=_("Reset one key or the entire configuration to the defaults."),
    )
    reset_parser.add_argument("key", choices=_CONFIG_KEYS, nargs="?")
    reset_parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help=_(
            "Override the configuration file path (default: use the standard location)."
        ),
    )
    reset_parser.set_defaults(func=_run_config_reset)

    return parser


def config_show(
    *,
    path: Path | None = None,
    stream: IO[str] | None = None,
) -> int:
    """Print the current configuration in JSON format."""

    config = load_config(path)
    mapping = config.to_mapping()
    output = stream or sys.stdout
    json.dump(mapping, output, indent=2, sort_keys=True)
    output.write("\n")
    return 0


def config_set(
    key: str,
    values: Sequence[str],
    *,
    path: Path | None = None,
    stream: IO[str] | None = None,
) -> int:
    """Update ``key`` with ``values`` and persist the configuration."""

    config = load_config(path)

    try:
        _apply_config_value(config, key, values)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ConfigCommandError(str(exc)) from exc

    save_config(config, path)
    output = stream or sys.stdout
    output.write(_("{key} updated.\n").format(key=key))
    return 0


def config_reset(
    key: str | None = None,
    *,
    path: Path | None = None,
    stream: IO[str] | None = None,
) -> int:
    """Reset ``key`` (or the entire configuration) to the default values."""

    if key is None:
        config = AppConfig()
        save_config(config, path)
        message = _("Configuration reset to defaults.")
    else:
        config = load_config(path)
        defaults = AppConfig()
        if key not in _CONFIG_KEYS:
            raise ConfigCommandError(
                _("Unknown configuration key: {key}").format(key=key)
            )
        if key == "threshold":
            config.threshold = defaults.threshold
        elif key == "log_level":
            config.log_level = defaults.log_level
        elif key == "backup_base":
            config.backup_base = defaults.backup_base
        elif key == "exclude_dirs":
            config.exclude_dirs = defaults.exclude_dirs
        elif key == "dry_run_default":
            config.dry_run_default = defaults.dry_run_default
        elif key == "write_reports":
            config.write_reports = defaults.write_reports
        save_config(config, path)
        message = _("{key} reset to default.").format(key=key)

    output = stream or sys.stdout
    output.write(f"{message}\n")
    return 0


def _run_config_show(namespace: argparse.Namespace) -> int:
    return config_show(path=namespace.config_path)


def _run_config_set(namespace: argparse.Namespace) -> int:
    return config_set(namespace.key, namespace.values, path=namespace.config_path)


def _run_config_reset(namespace: argparse.Namespace) -> int:
    return config_reset(namespace.key, path=namespace.config_path)


def _apply_config_value(
    config: AppConfig,
    key: str,
    values: Sequence[str],
) -> None:
    if key not in _CONFIG_KEYS:
        raise ValueError(_("Unknown configuration key: {key}").format(key=key))

    if key == "threshold":
        if len(values) != 1:
            raise ConfigCommandError(
                _("The threshold key expects exactly one value."),
            )
        config.threshold = threshold_value(values[0])
        return

    if key == "log_level":
        if len(values) != 1:
            raise ConfigCommandError(
                _("The log_level key expects exactly one value."),
            )
        choice = values[0].lower()
        if choice not in _LOG_LEVEL_CHOICES:
            raise ConfigCommandError(
                _("Unsupported log level: {value}.").format(value=values[0])
            )
        config.log_level = choice
        return

    if key == "backup_base":
        if len(values) != 1:
            raise ConfigCommandError(
                _("The backup_base key expects exactly one value."),
            )
        config.backup_base = Path(values[0]).expanduser()
        return

    if key == "exclude_dirs":
        parsed = parse_exclude_dirs(values, ignore_default=True)
        config.exclude_dirs = parsed
        return

    if key in {"dry_run_default", "write_reports"}:
        if len(values) != 1:
            raise ConfigCommandError(
                _("The {key} key expects exactly one value.").format(key=key),
            )
        config_value = _parse_bool(values[0])
        if key == "dry_run_default":
            config.dry_run_default = config_value
        else:
            config.write_reports = config_value
        return

    raise ValueError(_("Unknown configuration key: {key}").format(key=key))


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ConfigCommandError(
        _("Unsupported boolean value: {value}.").format(value=value)
    )
