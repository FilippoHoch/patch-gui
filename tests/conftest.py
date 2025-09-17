"""Test configuration for avoiding GUI dependencies during imports."""

from __future__ import annotations

import sys
import types
from pathlib import Path

PACKAGE_NAME = "patch_gui"

if PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(Path(__file__).resolve().parents[1] / PACKAGE_NAME)]
    sys.modules[PACKAGE_NAME] = package
