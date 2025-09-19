from pathlib import Path

import pytest

import patch_gui.config as config_module
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
    assert loaded.backup_retention_days == defaults.backup_retention_days
    assert loaded.ai_assistant_enabled == defaults.ai_assistant_enabled
    assert loaded.ai_auto_apply == defaults.ai_auto_apply
    assert loaded.theme == defaults.theme


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
        backup_retention_days=14,
        ai_assistant_enabled=True,
        ai_auto_apply=True,
        theme="light",
    )

    save_config(original, path=config_path)
    loaded = load_config(path=config_path)

    assert loaded == original


def test_save_config_atomic_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "settings.toml"
    original = AppConfig(threshold=0.9)
    save_config(original, path=config_path)

    attempted = AppConfig(threshold=0.5)

    def failing_replace(src: object, dst: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(config_module.os, "replace", failing_replace)

    with pytest.raises(RuntimeError):
        save_config(attempted, path=config_path)

    loaded = load_config(path=config_path)
    assert loaded == original
    assert {path for path in config_path.parent.iterdir()} == {config_path}


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
                "backup_retention_days = -10",
                'ai_assistant_enabled = "maybe"',
                'ai_auto_apply = """',
                'theme = 123',
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
    assert loaded.backup_retention_days == defaults.backup_retention_days
    assert loaded.ai_assistant_enabled == defaults.ai_assistant_enabled
    assert loaded.ai_auto_apply == defaults.ai_auto_apply
    assert loaded.theme == defaults.theme


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
                "backup_retention_days = 30",
                "ai_assistant_enabled = true",
                "ai_auto_apply = true",
                'theme = "light"',
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
    assert loaded.backup_retention_days == 30
    assert loaded.ai_assistant_enabled is True
    assert loaded.ai_auto_apply is True
    assert loaded.theme == "light"
