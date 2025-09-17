from __future__ import annotations

from typing import Any, cast

import pytest

from patch_gui import diff_applier_gui
from tests.typing_helpers import parametrize


GUI_RESULT = 42
CLI_RESULT = 17


@parametrize(
    "argv, expected_calls, expected_result",
    [
        ([], [("gui", ())], GUI_RESULT),
        (["apply", "patch.diff"], [("cli", ["patch.diff"])], CLI_RESULT),
        (
            ["--root", ".", "patch.diff"],
            [("cli", ["--root", ".", "patch.diff"])],
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

    def fake_launch_gui() -> int:
        calls.append(("gui", ()))
        return GUI_RESULT

    module_cli = cast(Any, diff_applier_gui).cli
    monkeypatch.setattr(module_cli, "run_cli", fake_run_cli)
    monkeypatch.setattr(diff_applier_gui, "_launch_gui", fake_launch_gui)

    result = diff_applier_gui.main(argv)

    assert result == expected_result
    assert calls == expected_calls
