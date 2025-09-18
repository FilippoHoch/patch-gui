from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from patch_gui import diff_applier_gui
from patch_gui.config import AppConfig
from tests._pytest_typing import typed_fixture, typed_parametrize

try:  # pragma: no cover - environment-dependent
    from PySide6 import QtWidgets as _QtWidgets
except Exception as exc:  # pragma: no cover - optional dependency
    QtWidgets: Any | None = None
    _QT_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - exercised when bindings are available
    QtWidgets = _QtWidgets
    _QT_IMPORT_ERROR = None


GUI_RESULT = 42
CLI_RESULT = 17
CONFIG_RESULT = 7


@typed_fixture()
def qt_app() -> Any:
    if QtWidgets is None:
        pytest.skip(f"PySide6 non disponibile: {_QT_IMPORT_ERROR}")
    assert QtWidgets is not None
    qt_widgets = QtWidgets
    app = qt_widgets.QApplication.instance()
    if app is None:
        app = qt_widgets.QApplication([])
    return app


@typed_parametrize(
    "argv, expected_calls, expected_result",
    [
        ([], [("gui", ())], GUI_RESULT),
        (["apply", "patch.diff"], [("cli", ["patch.diff"])], CLI_RESULT),
        (["config", "show"], [("config", ["show"])], CONFIG_RESULT),
        (
            ["--root", ".", "patch.diff"],
            [("cli", ["--root", ".", "patch.diff"])],
            CLI_RESULT,
        ),
        (
            ["--non-interactive", "--root", ".", "patch.diff"],
            [("cli", ["--non-interactive", "--root", ".", "patch.diff"])],
            CLI_RESULT,
        ),
        (
            ["--no-report", "--root", ".", "patch.diff"],
            [("cli", ["--no-report", "--root", ".", "patch.diff"])],
            CLI_RESULT,
        ),
        (
            ["--report-json", "report.json", "--root", ".", "patch.diff"],
            [
                (
                    "cli",
                    ["--report-json", "report.json", "--root", ".", "patch.diff"],
                )
            ],
            CLI_RESULT,
        ),
        (
            ["--report-txt=report.txt", "--root", ".", "patch.diff"],
            [
                (
                    "cli",
                    ["--report-txt=report.txt", "--root", ".", "patch.diff"],
                )
            ],
            CLI_RESULT,
        ),
        (
            ["--encoding=utf-8", "--root", ".", "patch.diff"],
            [
                ("cli", ["--encoding=utf-8", "--root", ".", "patch.diff"]),
            ],
            CLI_RESULT,
        ),
        (
            ["--log-level", "debug", "--root", ".", "patch.diff"],
            [
                ("cli", ["--log-level", "debug", "--root", ".", "patch.diff"]),
            ],
            CLI_RESULT,
        ),
        (
            ["--exclude-dir=build", "--root", ".", "patch.diff"],
            [
                ("cli", ["--exclude-dir=build", "--root", ".", "patch.diff"]),
            ],
            CLI_RESULT,
        ),
    ],
)
def test_main_dispatches_between_gui_and_cli(
    argv: list[str],
    expected_calls: list[tuple[str, object]],
    expected_result: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    def fake_run_cli(args: list[str]) -> int:
        calls.append(("cli", args))
        return CLI_RESULT

    def fake_run_config(args: list[str]) -> int:
        calls.append(("config", args))
        return CONFIG_RESULT

    def fake_launch_gui() -> int:
        calls.append(("gui", ()))
        return GUI_RESULT

    module_cli = cast(Any, diff_applier_gui).cli
    monkeypatch.setattr(module_cli, "run_cli", fake_run_cli)
    monkeypatch.setattr(module_cli, "run_config", fake_run_config)
    monkeypatch.setattr(diff_applier_gui, "_launch_gui", fake_launch_gui)

    result = diff_applier_gui.main(argv)

    assert result == expected_result
    assert calls == expected_calls


def test_settings_dialog_gathers_config(qt_app: Any, tmp_path: Path) -> None:
    if QtWidgets is None:
        pytest.skip(f"PySide6 non disponibile: {_QT_IMPORT_ERROR}")

    from patch_gui import app as app_module

    base = tmp_path / "backups"
    config = AppConfig(
        threshold=0.75,
        exclude_dirs=("build", "dist"),
        backup_base=base,
        log_level="warning",
        dry_run_default=True,
        write_reports=True,
        log_file=tmp_path / "logs" / "app.log",
        log_max_bytes=1024,
        log_backup_count=2,
        backup_retention_days=4,
        ai_assistant_enabled=True,
        ai_auto_apply=False,
    )

    dialog = app_module.SettingsDialog(None, config=config)
    dialog.threshold_spin.setValue(0.91)
    dialog.exclude_edit.setText("one, two, two , three")
    new_backup = tmp_path / "custom"
    dialog.backup_edit.setText(str(new_backup))
    index = dialog.log_combo.findData("debug")
    if index >= 0:
        dialog.log_combo.setCurrentIndex(index)
    dialog.dry_run_check.setChecked(False)
    dialog.reports_check.setChecked(False)
    new_log_file = tmp_path / "logs" / "custom.log"
    dialog.log_file_edit.setText(str(new_log_file))
    dialog.log_max_edit.setText("8192")
    dialog.log_backup_edit.setText("5")
    dialog.backup_retention_edit.setText("7")
    dialog.ai_assistant_check.setChecked(False)
    dialog.ai_auto_check.setChecked(True)

    updated = dialog._gather_config()

    assert updated.threshold == pytest.approx(0.91)
    assert updated.exclude_dirs == ("one", "two", "three")
    assert updated.backup_base == new_backup
    assert updated.log_level == "debug"
    assert updated.dry_run_default is False
    assert updated.write_reports is False
    assert updated.log_file == new_log_file
    assert updated.log_max_bytes == 8192
    assert updated.log_backup_count == 5
    assert updated.backup_retention_days == 7
    assert updated.ai_assistant_enabled is False
    assert updated.ai_auto_apply is True


def test_main_window_applies_settings_dialog(
    qt_app: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if QtWidgets is None:
        pytest.skip(f"PySide6 non disponibile: {_QT_IMPORT_ERROR}")

    from patch_gui import app as app_module

    saved_configs: list[AppConfig] = []

    def fake_save(config: AppConfig, path: Path | None = None) -> Path:
        saved_configs.append(config)
        return tmp_path / "settings.toml"

    configured_invocations: list[dict[str, object]] = []

    def fake_configure_logging(
        *,
        level: str,
        log_file: object | None = None,
        max_bytes: object | None = None,
        backup_count: object | None = None,
    ) -> None:
        configured_invocations.append(
            {
                "level": level,
                "log_file": log_file,
                "max_bytes": max_bytes,
                "backup_count": backup_count,
            }
        )

    monkeypatch.setattr(app_module, "save_config", fake_save)
    monkeypatch.setattr(app_module, "configure_logging", fake_configure_logging)

    original = AppConfig(
        threshold=0.8,
        exclude_dirs=("a",),
        backup_base=tmp_path / "base",
        log_level="info",
        dry_run_default=True,
        write_reports=True,
        log_file=tmp_path / "logs" / "app.log",
        log_max_bytes=0,
        log_backup_count=0,
        ai_assistant_enabled=False,
        ai_auto_apply=False,
    )

    window = app_module.MainWindow(app_config=original)

    new_config = AppConfig(
        threshold=0.93,
        exclude_dirs=("one", "two"),
        backup_base=tmp_path / "next",
        log_level="error",
        dry_run_default=False,
        write_reports=False,
        log_file=tmp_path / "logs" / "custom.log",
        log_max_bytes=2048,
        log_backup_count=3,
        ai_assistant_enabled=True,
        ai_auto_apply=True,
    )

    class _FakeDialog:
        def __init__(self, result: AppConfig) -> None:
            self.result_config = result

        def exec(self) -> Any:
            assert QtWidgets is not None
            return QtWidgets.QDialog.DialogCode.Accepted

    fake_dialog = _FakeDialog(new_config)
    monkeypatch.setattr(window, "_create_settings_dialog", lambda: fake_dialog)

    window.open_settings_dialog()

    assert window.app_config == new_config
    assert window.chk_dry.isChecked() is new_config.dry_run_default
    assert window.exclude_edit.text() == ", ".join(new_config.exclude_dirs)
    assert window.reports_enabled is new_config.write_reports
    assert window.ai_assistant_enabled is new_config.ai_assistant_enabled
    assert window.ai_auto_apply is new_config.ai_auto_apply
    assert configured_invocations == [
        {
            "level": new_config.log_level,
            "log_file": new_config.log_file,
            "max_bytes": new_config.log_max_bytes,
            "backup_count": new_config.log_backup_count,
        }
    ]
    assert saved_configs[-1] == new_config

    window.close()
