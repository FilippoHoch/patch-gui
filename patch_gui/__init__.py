"""Patch GUI package initialization."""

from __future__ import annotations

from typing import Sequence

from . import _version

__all__ = ["main", "__version__"]

__version__ = _version.__version__


def __getattr__(name: str):
    if name == "__version__":
        return _version.__version__
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point that dispatches to the CLI/GUI implementation."""

    from .diff_applier_gui import main as _main

    return _main(argv)
