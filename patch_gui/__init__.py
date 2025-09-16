"""Patch GUI package initialization."""

from __future__ import annotations

from typing import Sequence

__all__ = ["main", "__version__"]

__version__ = "0.1.0"


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point that dispatches to the CLI/GUI implementation."""

    from .diff_applier_gui import main as _main

    return _main(argv)
