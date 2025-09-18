"""Persistent configuration handling for Patch GUI."""

from __future__ import annotations

import ast
import json
import os
import sys
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Protocol, cast

from .patcher import DEFAULT_EXCLUDE_DIRS
from .utils import default_backup_base


class _TomllibModule(Protocol):
    def loads(self, __data: str, /) -> Any:  # pragma: no cover - protocol definition
        ...


def _import_tomllib() -> _TomllibModule | None:
    for name in ("tomllib", "tomli"):
        try:
            module = import_module(name)
        except ModuleNotFoundError:
            continue
        return cast("_TomllibModule", module)
    return None


_tomllib: _TomllibModule | None = _import_tomllib()


_CONFIG_SECTION = "patch_gui"
_CONFIG_FILENAME = "settings.toml"
_DEFAULT_THRESHOLD = 0.85
_DEFAULT_LOG_LEVEL = "warning"
_DEFAULT_DRY_RUN = True
_DEFAULT_WRITE_REPORTS = True
_DEFAULT_LOG_FILE_NAME = ".patch_gui.log"
_DEFAULT_LOG_MAX_BYTES = 0
_DEFAULT_LOG_BACKUP_COUNT = 0
_DEFAULT_BACKUP_RETENTION_DAYS = 0


def _default_log_file() -> Path:
    return Path.home() / _DEFAULT_LOG_FILE_NAME


DEFAULT_LOG_FILE: Path = _default_log_file()
DEFAULT_LOG_MAX_BYTES: int = _DEFAULT_LOG_MAX_BYTES
DEFAULT_LOG_BACKUP_COUNT: int = _DEFAULT_LOG_BACKUP_COUNT
DEFAULT_BACKUP_RETENTION_DAYS: int = _DEFAULT_BACKUP_RETENTION_DAYS


__all__ = [
    "AppConfig",
    "DEFAULT_BACKUP_RETENTION_DAYS",
    "DEFAULT_LOG_BACKUP_COUNT",
    "DEFAULT_LOG_FILE",
    "DEFAULT_LOG_MAX_BYTES",
    "default_config_dir",
    "default_config_path",
    "load_config",
    "save_config",
]


@dataclass
class AppConfig:
    """Dataclass representing the persisted configuration values."""

    threshold: float = _DEFAULT_THRESHOLD
    exclude_dirs: tuple[str, ...] = field(
        default_factory=lambda: tuple(DEFAULT_EXCLUDE_DIRS)
    )
    backup_base: Path = field(default_factory=default_backup_base)
    log_level: str = _DEFAULT_LOG_LEVEL
    dry_run_default: bool = _DEFAULT_DRY_RUN
    write_reports: bool = _DEFAULT_WRITE_REPORTS
    log_file: Path = field(default_factory=_default_log_file)
    log_max_bytes: int = DEFAULT_LOG_MAX_BYTES
    log_backup_count: int = DEFAULT_LOG_BACKUP_COUNT
    backup_retention_days: int = DEFAULT_BACKUP_RETENTION_DAYS

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AppConfig":
        """Create an :class:`AppConfig` instance from ``data``."""

        base = cls()

        threshold = _coerce_threshold(data.get("threshold"), base.threshold)
        exclude_dirs = _coerce_exclude_dirs(data.get("exclude_dirs"), base.exclude_dirs)
        backup_base = _coerce_backup_base(data.get("backup_base"), base.backup_base)
        log_level = _coerce_log_level(data.get("log_level"), base.log_level)
        dry_run_default = _coerce_bool(
            data.get("dry_run_default"), base.dry_run_default
        )
        write_reports = _coerce_bool(data.get("write_reports"), base.write_reports)
        log_file = _coerce_path(data.get("log_file"), base.log_file)
        log_max_bytes = _coerce_non_negative_int(
            data.get("log_max_bytes"), base.log_max_bytes
        )
        log_backup_count = _coerce_non_negative_int(
            data.get("log_backup_count"), base.log_backup_count
        )
        backup_retention_days = _coerce_non_negative_int(
            data.get("backup_retention_days"), base.backup_retention_days
        )

        return cls(
            threshold=threshold,
            exclude_dirs=exclude_dirs,
            backup_base=backup_base,
            log_level=log_level,
            dry_run_default=dry_run_default,
            write_reports=write_reports,
            log_file=log_file,
            log_max_bytes=log_max_bytes,
            log_backup_count=log_backup_count,
            backup_retention_days=backup_retention_days,
        )

    def to_mapping(self) -> MutableMapping[str, Any]:
        """Return a mutable mapping suitable for serialization."""

        return {
            "threshold": float(self.threshold),
            "exclude_dirs": list(self.exclude_dirs),
            "backup_base": str(self.backup_base),
            "log_level": str(self.log_level),
            "dry_run_default": bool(self.dry_run_default),
            "write_reports": bool(self.write_reports),
            "log_file": str(self.log_file),
            "log_max_bytes": int(self.log_max_bytes),
            "log_backup_count": int(self.log_backup_count),
            "backup_retention_days": int(self.backup_retention_days),
        }


def default_config_dir() -> Path:
    """Return the default directory that stores the configuration file."""

    if sys.platform.startswith("win"):
        base = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
        if base:
            return Path(base) / "Patch GUI"
        return Path.home() / "AppData" / "Roaming" / "Patch GUI"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Patch GUI"
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "patch-gui"
    return Path.home() / ".config" / "patch-gui"


def default_config_path() -> Path:
    """Return the fully-qualified configuration file path."""

    return default_config_dir() / _CONFIG_FILENAME


def load_config(path: Path | None = None) -> AppConfig:
    """Load the configuration from ``path`` or the default location."""

    target = Path(path) if path is not None else default_config_path()
    if not target.exists():
        return AppConfig()
    try:
        raw_data = target.read_bytes()
    except OSError:
        return AppConfig()

    parsed = _load_toml(raw_data)
    section = parsed.get(_CONFIG_SECTION)
    if isinstance(section, Mapping):
        data = section
    else:
        data = parsed if isinstance(parsed, Mapping) else {}

    if not isinstance(data, Mapping):
        return AppConfig()

    return AppConfig.from_mapping(data)


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    """Persist ``config`` to ``path`` or the default location."""

    target = Path(path) if path is not None else default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    mapping = config.to_mapping()
    threshold_repr = _format_float(mapping["threshold"])
    exclude_repr = ", ".join(json.dumps(item) for item in mapping["exclude_dirs"])
    log_level_repr = json.dumps(mapping["log_level"])
    dry_run_repr = json.dumps(mapping["dry_run_default"])
    write_reports_repr = json.dumps(mapping["write_reports"])
    backup_repr = json.dumps(mapping["backup_base"])
    log_file_repr = json.dumps(mapping["log_file"])
    log_max_bytes_repr = json.dumps(mapping["log_max_bytes"])
    log_backup_count_repr = json.dumps(mapping["log_backup_count"])
    backup_retention_repr = json.dumps(mapping["backup_retention_days"])

    content_lines = [
        f"[{_CONFIG_SECTION}]",
        f"threshold = {threshold_repr}",
        f"exclude_dirs = [{exclude_repr}]",
        f"backup_base = {backup_repr}",
        f"log_level = {log_level_repr}",
        f"dry_run_default = {dry_run_repr}",
        f"write_reports = {write_reports_repr}",
        f"log_file = {log_file_repr}",
        f"log_max_bytes = {log_max_bytes_repr}",
        f"log_backup_count = {log_backup_count_repr}",
        f"backup_retention_days = {backup_retention_repr}",
        "",
    ]

    target.write_text("\n".join(content_lines), encoding="utf-8")
    return target


def _format_float(value: float) -> str:
    return format(value, ".6g")


def _load_toml(data: bytes) -> MutableMapping[str, Any]:
    if _tomllib is not None:  # pragma: no cover - exercised in Python 3.11+
        try:
            parsed = _tomllib.loads(data.decode("utf-8"))
        except Exception:
            return {}
        if isinstance(parsed, MutableMapping):
            return dict(parsed)
        return {}

    text = data.decode("utf-8", errors="replace")
    result: MutableMapping[str, Any] = {}
    current_table: MutableMapping[str, Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            table_name = line[1:-1].strip()
            if not table_name:
                current_table = None
                continue
            table = result.setdefault(table_name, {})
            if isinstance(table, MutableMapping):
                current_table = table
            else:
                current_table = None
            continue
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        try:
            parsed_value = ast.literal_eval(value)
        except Exception:
            parsed_value = value.strip().strip('"')
        target = current_table if current_table is not None else result
        if isinstance(target, MutableMapping):
            target[key] = parsed_value
    return result


def _coerce_threshold(value: Any, default: float) -> float:
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return default
    if 0 < candidate <= 1:
        return candidate
    return default


def _coerce_exclude_dirs(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return tuple(default)
    candidates: list[str] = []
    fallback_to_default = False
    if isinstance(value, (list, tuple, set)):
        iterator = value
    elif isinstance(value, str):
        iterator = [part.strip() for part in value.split(",")]
        fallback_to_default = True
    else:
        return tuple(default)
    for item in iterator:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized:
            continue
        if normalized not in candidates:
            candidates.append(normalized)
    if candidates:
        return tuple(candidates)
    return tuple(default) if fallback_to_default else tuple()


def _coerce_backup_base(value: Any, default: Path) -> Path:
    if isinstance(value, Path):
        return value.expanduser()
    if isinstance(value, os.PathLike):
        return Path(value).expanduser()
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return Path(cleaned).expanduser()
    return default


def _coerce_path(value: Any, default: Path) -> Path:
    return _coerce_backup_base(value, default)


def _coerce_log_level(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    candidate = value.strip()
    return candidate.lower() if candidate else default


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _coerce_non_negative_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if value >= 0 else default
    if isinstance(value, float) and value.is_integer():
        candidate = int(value)
        return candidate if candidate >= 0 else default
    if isinstance(value, str):
        candidate = str(value).strip()  # type: ignore[assignment]
        if not candidate:
            return default
        try:
            parsed = int(candidate)
        except ValueError:
            return default
        return parsed if parsed >= 0 else default
    return default
