"""Tests for platform-specific helpers in :mod:`patch_gui.platform`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from patch_gui import platform


@pytest.mark.parametrize("env_value", ["Ubuntu", "Debian"])
def test_running_under_wsl_detects_env(
    monkeypatch: pytest.MonkeyPatch, env_value: str
) -> None:
    monkeypatch.setenv("WSL_DISTRO_NAME", env_value)
    assert platform.running_under_wsl()
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)


def test_running_under_wsl_detects_kernel_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    def fake_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if str(self) == "/proc/sys/kernel/osrelease":
            return "5.15.133.1-microsoft-standard-WSL2"
        raise OSError

    monkeypatch.setattr(platform.Path, "read_text", fake_read_text)  # type: ignore[attr-defined]
    assert platform.running_under_wsl()


def test_running_under_wsl_returns_false_when_no_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    def fake_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        raise OSError

    monkeypatch.setattr(platform.Path, "read_text", fake_read_text)  # type: ignore[attr-defined]
    assert not platform.running_under_wsl()
