"""Shared logging helpers used by both the GUI and CLI entry-points."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

from .config import (
    DEFAULT_LOG_BACKUP_COUNT,
    DEFAULT_LOG_FILE,
    DEFAULT_LOG_MAX_BYTES,
)


LOG_FILE_ENV_VAR: Final[str] = "PATCH_GUI_LOG_FILE"
LOG_LEVEL_ENV_VAR: Final[str] = "PATCH_GUI_LOG_LEVEL"
LOG_MAX_BYTES_ENV_VAR: Final[str] = "PATCH_GUI_LOG_MAX_BYTES"
LOG_BACKUP_COUNT_ENV_VAR: Final[str] = "PATCH_GUI_LOG_BACKUP_COUNT"
LOG_TIMESTAMP_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"

__all__ = [
    "LOG_BACKUP_COUNT_ENV_VAR",
    "LOG_FILE_ENV_VAR",
    "LOG_LEVEL_ENV_VAR",
    "LOG_MAX_BYTES_ENV_VAR",
    "LOG_TIMESTAMP_FORMAT",
    "configure_logging",
]


def _resolve_log_level(level: str | int | None) -> int:
    """Convert ``level`` to a ``logging`` level integer."""

    if level is None:
        level = os.getenv(LOG_LEVEL_ENV_VAR, "INFO")

    if isinstance(level, int):
        return level

    if isinstance(level, str):
        candidate = level.strip()
        if not candidate:
            return logging.INFO
        if candidate.isdigit():
            return int(candidate)
        numeric = logging.getLevelName(candidate.upper())
        if isinstance(numeric, int):
            return numeric

    return logging.INFO


def _coerce_non_negative_int(value: int | str | None) -> int | None:
    if value is None:
        return None

    if isinstance(value, int):
        numeric = value
    else:
        candidate = str(value).strip()
        if not candidate:
            return None
        try:
            numeric = int(candidate)
        except ValueError:
            return None

    return numeric if numeric >= 0 else None


def _resolve_rotation_setting(
    value: int | str | None, *, env_var: str, default: int
) -> int:
    direct_value = _coerce_non_negative_int(value)
    if direct_value is not None:
        return direct_value

    env_value = _coerce_non_negative_int(os.getenv(env_var))
    if env_value is not None:
        return env_value

    return default


def configure_logging(
    *,
    level: str | int | None = None,
    log_file: str | Path | None = None,
    max_bytes: int | str | None = None,
    backup_count: int | str | None = None,
) -> Path:
    """Configure the global logging setup with a rotating file handler."""

    resolved_level = _resolve_log_level(level)
    file_path = Path(
        os.getenv(LOG_FILE_ENV_VAR, log_file or DEFAULT_LOG_FILE)
    ).expanduser()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_max_bytes = _resolve_rotation_setting(
        max_bytes, env_var=LOG_MAX_BYTES_ENV_VAR, default=DEFAULT_LOG_MAX_BYTES
    )
    resolved_backup_count = _resolve_rotation_setting(
        backup_count,
        env_var=LOG_BACKUP_COUNT_ENV_VAR,
        default=DEFAULT_LOG_BACKUP_COUNT,
    )

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt=LOG_TIMESTAMP_FORMAT,
    )

    file_handler = RotatingFileHandler(
        file_path,
        encoding="utf-8",
        maxBytes=resolved_max_bytes,
        backupCount=resolved_backup_count,
    )
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
            handler.close()

    root_logger.addHandler(file_handler)
    return file_path
