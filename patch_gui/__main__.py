"""Command-line entry point for Patch GUI."""

from .diff_applier_gui import main


def run() -> None:
    """Launch the Patch GUI application."""
    main()


if __name__ == "__main__":
    run()
