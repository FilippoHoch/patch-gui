from __future__ import annotations

from typing import Any, cast

import pytest

from patch_gui import diff_applier_gui
from tests._pytest_typing import typed_parametrize


GUI_RESULT = 42
CLI_RESULT = 17
CONFIG_RESULT = 7


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
