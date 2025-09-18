"""Tests for platform-specific helpers in :mod:`patch_gui.platform`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from patch_gui import platform
from tests._pytest_typing import typed_parametrize

MODULE_PLATFORM = cast(Any, platform)


@typed_parametrize("env_value", ["Ubuntu", "Debian"])
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

    monkeypatch.setattr(MODULE_PLATFORM.Path, "read_text", fake_read_text)
    assert platform.running_under_wsl()


def test_running_under_wsl_returns_false_when_no_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    def fake_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        raise OSError

    monkeypatch.setattr(MODULE_PLATFORM.Path, "read_text", fake_read_text)
    assert not platform.running_under_wsl()


@typed_parametrize("platform_value", ["win32", "win64", "cygwin"])
def test_running_on_windows_native_detects_windows(
    monkeypatch: pytest.MonkeyPatch, platform_value: str
) -> None:
    monkeypatch.setattr(MODULE_PLATFORM.sys, "platform", platform_value)
    assert platform.running_on_windows_native()


@typed_parametrize("platform_value", ["linux", "darwin", "freebsd12"])
def test_running_on_windows_native_returns_false_elsewhere(
    monkeypatch: pytest.MonkeyPatch, platform_value: str
) -> None:
    monkeypatch.setattr(MODULE_PLATFORM.sys, "platform", platform_value)
    assert not platform.running_on_windows_native()
