"""Helper utilities to compile Qt translation files during the build."""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Protocol, cast


class _BuildCommandProtocol(Protocol):  # pragma: no cover - typing helper
    announce: Callable[[str, int], None]

    def run(self) -> None: ...


class _SDistCommandProtocol(Protocol):  # pragma: no cover - typing helper
    announce: Callable[[str, int], None]

    def run(self) -> None: ...


_SetuptoolsBuildPy: type[_BuildCommandProtocol] | None
try:  # Used when setuptools is available (build/install)
    from setuptools.command.build_py import build_py as _ImportedBuildPy
except ModuleNotFoundError:  # pragma: no cover - CLI usage without setuptools installed
    _SetuptoolsBuildPy = None
else:  # pragma: no cover - import only needed when setuptools is present
    _SetuptoolsBuildPy = cast("type[_BuildCommandProtocol]", _ImportedBuildPy)

_SetuptoolsSDist: type[_SDistCommandProtocol] | None
try:
    from setuptools.command.sdist import sdist as _ImportedSDist
except ModuleNotFoundError:  # pragma: no cover - CLI usage without setuptools installed
    _SetuptoolsSDist = None
else:  # pragma: no cover - import only needed when setuptools is present
    _SetuptoolsSDist = cast("type[_SDistCommandProtocol]", _ImportedSDist)

TRANSLATIONS_DIR = Path(__file__).resolve().parent / "patch_gui" / "translations"
LRELEASE_CANDIDATES: tuple[str, ...] = ("pyside6-lrelease", "lrelease-qt6", "lrelease")

Announcer = Callable[[str, int], None]
Level = int


def _emit(
    message: str, level: Level = logging.INFO, announcer: Announcer | None = None
) -> None:
    if announcer is not None:
        announcer(message, level)
        return

    stream = sys.stderr if level >= logging.WARNING else sys.stdout
    print(message, file=stream)


def _find_lrelease() -> Optional[Path]:
    for candidate in LRELEASE_CANDIDATES:
        path = shutil.which(candidate)
        if path:
            return Path(path)
    return None


def compile_translations(
    *, force: bool = False, strict: bool = False, announcer: Announcer | None = None
) -> List[Path]:
    """Compile all ``.ts`` translations using ``lrelease``."""

    ts_files = sorted(TRANSLATIONS_DIR.glob("*.ts"))
    if not ts_files:
        _emit(
            f"No translation sources found in {TRANSLATIONS_DIR}.",
            level=logging.DEBUG,
            announcer=announcer,
        )
        return []

    lrelease = _find_lrelease()
    if lrelease is None:
        message = (
            "Cannot find 'lrelease' (tried: %s). Skipping translation compilation."
            % ", ".join(LRELEASE_CANDIDATES)
        )
        _emit(message, level=logging.WARNING, announcer=announcer)
        if strict:
            raise RuntimeError(message)
        return []

    compiled: List[Path] = []
    for ts_file in ts_files:
        result = _compile_single(ts_file, lrelease, force=force, announcer=announcer)
        if result is not None:
            compiled.append(result)
        elif strict:
            raise RuntimeError(f"Failed to compile translation {ts_file.name}")
    return compiled


def _compile_single(
    ts_path: Path, lrelease: Path, *, force: bool, announcer: Announcer | None
) -> Optional[Path]:
    qm_path = ts_path.with_suffix(".qm")
    try:
        if not force and qm_path.exists():
            if ts_path.stat().st_mtime <= qm_path.stat().st_mtime:
                _emit(
                    f"Translation {qm_path.name} is up to date.",
                    level=logging.DEBUG,
                    announcer=announcer,
                )
                return qm_path
    except OSError:
        # Fall back to recompiling when we cannot compare timestamps.
        pass

    _emit(
        f"Compiling {ts_path.name} → {qm_path.name}",
        level=logging.INFO,
        announcer=announcer,
    )
    result = subprocess.run(
        [str(lrelease), str(ts_path), "-qm", str(qm_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _emit(
            "lrelease failed for %s (exit code %s): %s%s"
            % (ts_path.name, result.returncode, result.stdout, result.stderr),
            level=logging.WARNING,
            announcer=announcer,
        )
        return None
    return qm_path


if TYPE_CHECKING:

    class BuildPy(_BuildCommandProtocol):  # pragma: no cover - typing helper
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        def run(self) -> None: ...

elif _SetuptoolsBuildPy is not None:

    class BuildPy(_SetuptoolsBuildPy):
        """Custom build command that ensures Qt translations are generated."""

        def run(self) -> None:
            compile_translations(announcer=self.announce)
            super().run()

else:  # pragma: no cover - setuptools not installed when running CLI only

    class BuildPy:  # type: ignore[no-redef]
        """Placeholder used when setuptools is not available."""

        announce: Callable[[str, int], None]

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError(
                "setuptools is required to use the custom build command."
            )

        def run(self) -> None:
            raise RuntimeError(
                "setuptools is required to use the custom build command."
            )


if TYPE_CHECKING:

    class SDist(_SDistCommandProtocol):  # pragma: no cover - typing helper
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        def run(self) -> None: ...

elif _SetuptoolsSDist is not None:

    class SDist(_SetuptoolsSDist):
        """Custom sdist command that ensures Qt translations are generated."""

        def run(self) -> None:
            compile_translations(announcer=self.announce)
            super().run()

else:  # pragma: no cover - setuptools not installed when running CLI only

    class SDist:  # type: ignore[no-redef]
        """Placeholder used when setuptools is not available."""

        announce: Callable[[str, int], None]

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError(
                "setuptools is required to use the custom sdist command."
            )

        def run(self) -> None:
            raise RuntimeError(
                "setuptools is required to use the custom sdist command."
            )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild translations even if the .qm files are newer than the sources.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail with exit code 1 if lrelease is not available or compilation fails.",
    )
    args = parser.parse_args(argv)

    try:
        compile_translations(force=args.force, strict=args.strict)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
