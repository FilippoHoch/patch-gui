"""Command-line entry point for Patch GUI."""

from __future__ import annotations

import sys

from .diff_applier_gui import main


def run() -> None:
    """Entry point used by the ``patch-gui`` console script."""

    sys.exit(main())


if __name__ == "__main__":
    run()
