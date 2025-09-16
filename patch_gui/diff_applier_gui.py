"""Entry point that dispatches between the GUI and CLI workflows."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import cli
from .utils import APP_NAME

__all__ = ["main"]

CLI_FLAGS = {"--dry-run", "--threshold", "--backup", "--root"}
CLI_PREFIXES = ("--threshold=", "--backup=")


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch to the GUI or CLI depending on the provided arguments."""

    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        return _launch_gui()

    if args[0] == "gui":
        if any(opt in {"-h", "--help"} for opt in args[1:]):
            _print_gui_help()
            return 0
        return _launch_gui()

    if args[0] == "apply":
        return cli.run_cli(args[1:])

    if any(opt in {"-h", "--help"} for opt in args):
        _print_help()
        return 0

    if _looks_like_cli(args):
        return cli.run_cli(args)

    return _launch_gui()


def _looks_like_cli(args: Sequence[str]) -> bool:
    if not args:
        return False
    first = args[0]
    if not first.startswith("-"):
        return True
    for opt in args:
        if opt in CLI_FLAGS:
            return True
        if opt.startswith(CLI_PREFIXES):
            return True
    return False


def _launch_gui() -> int:
    from .app import main as gui_main

    gui_main()
    return 0


def _print_gui_help() -> None:
    print("Uso: patch-gui gui", file=sys.stdout)
    print("Apre l'interfaccia grafica dell'applicazione.", file=sys.stdout)


def _print_help() -> None:
    parser = argparse.ArgumentParser(
        prog="patch-gui",
        description=f"{APP_NAME} – avvia la GUI (default) oppure applica una patch via CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["gui", "apply"],
        help="Comando da eseguire (default: gui).",
    )
    parser.print_help()
    print("\nOpzioni CLI:", file=sys.stdout)
    cli.build_parser().print_help()


if __name__ == "__main__":
    sys.exit(main())
