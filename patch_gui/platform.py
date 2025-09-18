"""Platform detection helpers used by the GUI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = ["running_on_windows_native", "running_under_wsl"]

_WSL_INDICATOR_FILES = (
    Path("/proc/sys/kernel/osrelease"),
    Path("/proc/version"),
)


def running_under_wsl() -> bool:
    """Return ``True`` when executing inside a Windows Subsystem for Linux distro."""

    if os.getenv("WSL_DISTRO_NAME"):
        return True

    for marker in _WSL_INDICATOR_FILES:
        try:
            contents = marker.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if "microsoft" in contents or "wsl" in contents:
            return True

    return False


def running_on_windows_native() -> bool:
    """Return ``True`` when running on a Windows host outside of WSL."""

    return sys.platform.startswith(("win", "cygwin"))
