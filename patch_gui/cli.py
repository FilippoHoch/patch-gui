"""Command-line helpers to apply unified diff patches without launching the GUI."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import IO, Callable, Sequence, cast

from .config import AppConfig, load_config, save_config
from .downloader import (
    DEFAULT_ASSET_NAME,
    DEFAULT_REPO,
    DownloadError,
    download_latest_release_exe,
)
from .executor import CLIError, apply_patchset, load_patch, session_completed
from .localization import gettext as _
from .logging_utils import configure_logging
from .parser import (
    _LOG_LEVEL_CHOICES,
    REPORT_JSON_UNSET,
    REPORT_TXT_UNSET,
    build_parser,
    parse_exclude_dirs,
    threshold_value,
)

__all__ = [
    "CLIError",
    "apply_patchset",
    "build_parser",
    "build_config_parser",
    "build_download_parser",
    "load_patch",
    "run_cli",
    "run_config",
    "run_download_exe",
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
    "log_file",
    "log_max_bytes",
    "log_backup_count",
    "backup_retention_days",
    "ai_assistant_enabled",
    "ai_auto_apply",
    "ai_diff_notes_enabled",
)


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv`` and execute the CLI workflow."""

    argument_list = list(argv) if argv is not None else sys.argv[1:]

    bootstrap_parser = argparse.ArgumentParser(add_help=False)
    bootstrap_parser.add_argument("--config-path", type=Path, default=None)
    bootstrap_args, _remaining = bootstrap_parser.parse_known_args(argument_list)
    config_path = bootstrap_args.config_path

    config = load_config(config_path)
    parser = build_parser(config=config, config_path=config_path)
    args = parser.parse_args(argument_list)

    raw_summary_formats = list(args.summary_format) if args.summary_format else None
    if raw_summary_formats and "none" in raw_summary_formats:
        if len(raw_summary_formats) > 1:
            parser.error(_("The 'none' summary format cannot be combined with others."))
        summary_formats: list[str] = []
        summary_controlled = True
    elif raw_summary_formats:
        summary_formats = []
        for fmt in raw_summary_formats:
            if fmt not in summary_formats:
                summary_formats.append(fmt)
        summary_controlled = True
    else:
        summary_formats = ["text"]
        summary_controlled = False

    if (not args.write_reports) and (
        (args.report_json is not REPORT_JSON_UNSET and args.report_json is not None)
        or (args.report_txt is not REPORT_TXT_UNSET and args.report_txt is not None)
    ):
        parser.error(
            _(
                "The --report-json/--report-txt options are incompatible with --no-report."
            )
        )

    report_json_arg = (
        None if args.report_json is REPORT_JSON_UNSET else args.report_json
    )
    report_txt_arg = None if args.report_txt is REPORT_TXT_UNSET else args.report_txt

    requested_report_formats: set[str]
    if summary_controlled:
        requested_report_formats = {
            fmt for fmt in summary_formats if fmt in {"json", "text"}
        }
    else:
        requested_report_formats = {"json", "text"}
    if args.report_json is not REPORT_JSON_UNSET:
        if report_json_arg is None:
            requested_report_formats.discard("json")
        else:
            requested_report_formats.add("json")
    if args.report_txt is not REPORT_TXT_UNSET:
        if report_txt_arg is None:
            requested_report_formats.discard("text")
        else:
            requested_report_formats.add("text")

    configure_logging(
        level=args.log_level,
        log_file=config.log_file,
        max_bytes=config.log_max_bytes,
        backup_count=config.log_backup_count,
    )

    root_logger = logging.getLogger()
    console_level = root_logger.getEffectiveLevel()
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)

    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            root_logger.removeHandler(handler)

    root_logger.addHandler(console_handler)

    interactive = not args.non_interactive
    if args.auto_accept:
        interactive = True

    ai_assistant_enabled = bool(getattr(args, "ai_assistant", False))
    ai_auto_select = bool(getattr(args, "ai_select", False))
    if ai_auto_select:
        ai_assistant_enabled = True

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
            interactive=interactive,
            auto_accept=args.auto_accept,
            report_json=report_json_arg,
            report_txt=report_txt_arg,
            write_report_files=args.write_reports,
            write_report_json="json" in requested_report_formats,
            write_report_txt="text" in requested_report_formats,
            exclude_dirs=exclude_dirs,
            config=config,
            ai_assistant=ai_assistant_enabled,
            ai_auto_select=ai_auto_select,
        )
    except CLIError as exc:
        parser.exit(1, _("Error: {message}\n").format(message=exc))

    def _emit_text_summary() -> None:
        print(session.to_txt())
        if args.dry_run:
            print(
                _("\nDry-run mode: no files were modified and no backups were created.")
            )
        else:
            print(_("\nBackups saved to: {path}").format(path=session.backup_dir))
            if session.report_json_path or session.report_txt_path:
                details = []
                if session.report_json_path:
                    details.append(
                        _("JSON: {path}").format(path=session.report_json_path)
                    )
                if session.report_txt_path:
                    details.append(
                        _("Text: {path}").format(path=session.report_txt_path)
                    )
                print(
                    _("Reports saved to: {details}").format(details=", ".join(details))
                )
            else:
                print(_("Reports disabled (--no-report or configuration)"))

    emitted_text = False
    for fmt in summary_formats:
        if fmt == "text" and not emitted_text:
            _emit_text_summary()
            emitted_text = True
        elif fmt == "json":
            json_output = json.dumps(session.to_json(), ensure_ascii=False)
            print(json_output)

    if not summary_formats:
        if args.dry_run:
            logger.info(
                _("Dry-run mode: no files were modified and no backups were created.")
            )
        else:
            logger.info(_("Backups saved to: %s"), session.backup_dir)
            if session.report_json_path or session.report_txt_path:
                details = []
                if session.report_json_path:
                    details.append(
                        _("JSON: {path}").format(path=session.report_json_path)
                    )
                if session.report_txt_path:
                    details.append(
                        _("Text: {path}").format(path=session.report_txt_path)
                    )
                logger.info(
                    _("Reports saved to: %s"),
                    ", ".join(details),
                )
            else:
                logger.info(_("Reports disabled (--no-report or configuration)"))

    return 0 if session_completed(session) else 1


def run_download_exe(argv: Sequence[str] | None = None) -> int:
    """Download the Windows executable distributed with the project releases."""

    parser = build_download_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        destination = download_latest_release_exe(
            repo=args.repo,
            asset_name=args.asset_name,
            destination=args.output,
            overwrite=args.force,
            token=args.token,
            tag=args.tag,
        )
    except DownloadError as exc:
        parser.exit(1, _("Error: {message}\n").format(message=exc))

    print(
        _("Downloaded {asset} to {path}.").format(
            asset=args.asset_name, path=destination
        )
    )
    return 0


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


def build_download_parser() -> argparse.ArgumentParser:
    """Return an ``ArgumentParser`` configured for the ``download-exe`` command."""

    parser = argparse.ArgumentParser(
        prog="patch-gui download-exe",
        description=_(
            "Download the Windows executable published with the project's releases."
        ),
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=_(
            "GitHub repository in the form 'owner/name' from which the asset will be downloaded."
        ),
    )
    parser.add_argument(
        "--asset-name",
        default=DEFAULT_ASSET_NAME,
        help=_("Name of the executable asset to download."),
    )
    parser.add_argument(
        "--tag",
        default=None,
        help=_(
            "Specific release tag to retrieve instead of the latest published release."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=_(
            "Destination file or directory where the executable will be stored (default: current directory)."
        ),
    )
    parser.add_argument(
        "--token",
        default=None,
        help=_("GitHub token used for authenticated requests (optional)."),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=_("Overwrite the destination file if it already exists."),
    )
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
        elif key == "log_file":
            config.log_file = defaults.log_file
        elif key == "log_max_bytes":
            config.log_max_bytes = defaults.log_max_bytes
        elif key == "log_backup_count":
            config.log_backup_count = defaults.log_backup_count
        elif key == "backup_retention_days":
            config.backup_retention_days = defaults.backup_retention_days
        elif key == "ai_assistant_enabled":
            config.ai_assistant_enabled = defaults.ai_assistant_enabled
        elif key == "ai_auto_apply":
            config.ai_auto_apply = defaults.ai_auto_apply
        elif key == "ai_diff_notes_enabled":
            config.ai_diff_notes_enabled = defaults.ai_diff_notes_enabled
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

    if key in {"ai_assistant_enabled", "ai_auto_apply", "ai_diff_notes_enabled"}:
        if len(values) != 1:
            raise ConfigCommandError(
                _("The {key} key expects exactly one value.").format(key=key),
            )
        config_value = _parse_bool(values[0])
        if key == "ai_assistant_enabled":
            config.ai_assistant_enabled = config_value
        elif key == "ai_auto_apply":
            config.ai_auto_apply = config_value
        else:
            config.ai_diff_notes_enabled = config_value
        return

    if key == "log_file":
        if len(values) != 1:
            raise ConfigCommandError(
                _("The log_file key expects exactly one value."),
            )
        config.log_file = Path(values[0]).expanduser()
        return

    if key in {"log_max_bytes", "log_backup_count", "backup_retention_days"}:
        if len(values) != 1:
            raise ConfigCommandError(
                _("The {key} key expects exactly one value.").format(key=key),
            )
        numeric = _parse_non_negative_int(values[0], key=key)
        if key == "log_max_bytes":
            config.log_max_bytes = numeric
        elif key == "log_backup_count":
            config.log_backup_count = numeric
        else:
            config.backup_retention_days = numeric
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


def _parse_non_negative_int(value: str, *, key: str) -> int:
    candidate = value.strip()
    if not candidate:
        raise ConfigCommandError(
            _("The {key} key expects a non-negative integer.").format(key=key)
        )
    try:
        parsed = int(candidate)
    except ValueError as exc:
        raise ConfigCommandError(
            _("The {key} key expects a non-negative integer.").format(key=key)
        ) from exc
    if parsed < 0:
        raise ConfigCommandError(
            _("The {key} key expects a non-negative integer.").format(key=key)
        )
    return parsed
