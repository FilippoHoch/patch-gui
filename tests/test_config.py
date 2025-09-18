from pathlib import Path

import pytest

from patch_gui.config import AppConfig, load_config, save_config


def test_load_config_returns_defaults_when_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.toml"

    loaded = load_config(path=config_path)
    defaults = AppConfig()

    assert loaded.threshold == defaults.threshold
    assert loaded.exclude_dirs == defaults.exclude_dirs
    assert loaded.backup_base == defaults.backup_base
    assert loaded.log_level == defaults.log_level
    assert loaded.dry_run_default == defaults.dry_run_default
    assert loaded.write_reports == defaults.write_reports
    assert loaded.log_file == defaults.log_file
    assert loaded.log_max_bytes == defaults.log_max_bytes
    assert loaded.log_backup_count == defaults.log_backup_count


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.toml"
    custom_backup = tmp_path / "backups"

    original = AppConfig(
        threshold=0.9,
        exclude_dirs=("one", "two"),
        backup_base=custom_backup,
        log_level="debug",
        dry_run_default=False,
        write_reports=False,
        log_file=tmp_path / "custom.log",
        log_max_bytes=1048576,
        log_backup_count=3,
    )

    save_config(original, path=config_path)
    loaded = load_config(path=config_path)

    assert loaded == original


def test_load_config_invalid_values_fallback(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.toml"
    config_path.write_text(
        "\n".join(
            [
                "[patch_gui]",
                "threshold = 5",
                'exclude_dirs = ""',
                'backup_base = "   "',
                "log_level = 123",
                'dry_run_default = "maybe"',
                'write_reports = "sometimes"',
                'log_file = "   "',
                "log_max_bytes = -1",
                "log_backup_count = -5",
                "",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_config(path=config_path)
    defaults = AppConfig()

    assert loaded.threshold == defaults.threshold
    assert loaded.exclude_dirs == defaults.exclude_dirs
    assert loaded.backup_base == defaults.backup_base
    assert loaded.log_level == defaults.log_level
    assert loaded.dry_run_default == defaults.dry_run_default
    assert loaded.write_reports == defaults.write_reports
    assert loaded.log_file == defaults.log_file
    assert loaded.log_max_bytes == defaults.log_max_bytes
    assert loaded.log_backup_count == defaults.log_backup_count


def test_load_config_accepts_empty_exclude_list(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.toml"
    config_path.write_text(
        "\n".join(
            [
                "[patch_gui]",
                "threshold = 0.85",
                "exclude_dirs = []",
                'backup_base = "' + str(tmp_path / "backups") + '"',
                'log_level = "warning"',
                "dry_run_default = false",
                "write_reports = true",
                'log_file = "' + str(tmp_path / "log.txt") + '"',
                "log_max_bytes = 1024",
                "log_backup_count = 4",
                "",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_config(path=config_path)

    assert loaded.exclude_dirs == tuple()
    assert loaded.threshold == pytest.approx(0.85)
    assert loaded.log_level == "warning"
    assert loaded.backup_base == (tmp_path / "backups")
    assert loaded.dry_run_default is False
    assert loaded.write_reports is True
    assert loaded.log_file == (tmp_path / "log.txt")
    assert loaded.log_max_bytes == 1024
    assert loaded.log_backup_count == 4
