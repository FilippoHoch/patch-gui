"""Entry point that dispatches between the GUI and CLI workflows."""

from __future__ import annotations

import argparse
import sys
from functools import lru_cache
from typing import Any, Optional, Sequence, cast

try:  # pragma: no cover - optional dependency may be missing in CLI-only installations
    from PySide6 import QtCore
except ImportError:  # pragma: no cover - executed when PySide6 is not installed
    QtCore = cast(Any, None)

from . import cli
from .i18n import install_translators
from .localization import gettext as _
from .utils import APP_NAME

__all__ = ["main"]


@lru_cache(maxsize=1)
def _cli_option_strings() -> set[str]:
    parser = cli.build_parser()
    return {
        option
        for option in parser._option_string_actions
        if option.startswith("--") and option not in {"--help"}
    }


def _tr(text: str) -> str:
    """Translate ``text`` using the ``diff_applier_gui`` context."""

    if QtCore is not None:
        translated_obj = QtCore.QCoreApplication.translate("diff_applier_gui", text)
        translated = str(translated_obj)
        if translated != text:
            return translated
    return _(text)


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

    if args[0] == "config":
        return cli.run_config(args[1:])

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
    option_strings = _cli_option_strings()
    for opt in args:
        if not opt.startswith("-"):
            continue
        normalized = opt.split("=", 1)[0]
        if normalized in option_strings:
            return True
    return False


def _launch_gui() -> int:
    if QtCore is None:
        _print_missing_gui_dependency()
        return 1

    try:
        from .app import main as gui_main
    except (
        ImportError
    ) as exc:  # pragma: no cover - defensive guard for partial installs
        _print_missing_gui_dependency(exc)
        return 1

    gui_main()
    return 0


def _print_gui_help() -> None:
    _ensure_translator()
    print(_tr("Usage: patch-gui gui"), file=sys.stdout)
    print(_tr("Opens the application's graphical interface."), file=sys.stdout)


def _print_help() -> None:
    _ensure_translator()
    description = _tr(
        "{app_name} – launch the GUI (default) or apply a patch via the CLI."
    )
    parser = argparse.ArgumentParser(
        prog="patch-gui",
        description=description.format(app_name=APP_NAME),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["gui", "apply", "config"],
        help=_tr("Command to execute (default: gui)."),
    )
    parser.print_help()
    print(_tr("\nCLI options:"), file=sys.stdout)
    cli.build_parser().print_help()
    print(_tr("\nConfiguration commands:"), file=sys.stdout)
    cli.build_config_parser().print_help()


def _ensure_translator() -> None:
    """Create a temporary ``QCoreApplication`` and install translations if needed."""

    if QtCore is None:
        return

    app = QtCore.QCoreApplication.instance()
    if app is None:
        # ``[]`` so the temporary instance does not inherit CLI arguments that belong to
        # ``argparse``; this avoids warnings from Qt about unknown options.
        app = QtCore.QCoreApplication([])
        app.setApplicationName(APP_NAME)

    if getattr(app, "_installed_translators", None):
        return

    translators = install_translators(app)
    setattr(app, "_installed_translators", translators)


def _print_missing_gui_dependency(exc: Optional[Exception] = None) -> None:
    message = _(
        "PySide6 is not installed. Install the GUI dependencies with 'pip install .[gui]' "
        "or include the 'gui' extra when installing the package."
    )
    print(message, file=sys.stderr)
    if exc is not None:
        print(_("Original details: {error}").format(error=exc), file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
