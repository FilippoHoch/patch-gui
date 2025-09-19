"""Utility per generare gli artifact di distribuzione di Patch GUI.

Lo script riproduce i passaggi indicati in ``RELEASE.md`` per ottenere gli
artifact ``sdist`` e ``wheel`` aggiornati. In particolare:

1. (Opzionale) rimuove le cartelle di build precedenti.
2. Compila le traduzioni Qt tramite ``build_translations``.
3. Esegue ``python -m build`` per creare i pacchetti in ``dist/``.
4. (Opzionale) valida i file risultanti con ``twine check``.

Esempio d'uso::

    python scripts/build_packages.py --clean --check

"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
BUILD_DIR = REPO_ROOT / "build"


class PackagingError(RuntimeError):
    """Eccezione sollevata quando un comando richiesto fallisce."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera i pacchetti distribuiti")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Elimina le cartelle di build precedenti prima di iniziare",
    )
    parser.add_argument(
        "--skip-translations",
        action="store_true",
        help="Non ricompila le traduzioni Qt (richiede build già aggiornate)",
    )
    parser.add_argument(
        "--check",
        dest="run_check",
        action="store_true",
        help="Esegue 'twine check' sugli artifact generati",
    )
    parser.add_argument(
        "--no-check",
        dest="run_check",
        action="store_false",
        help="Salta la validazione con twine (default)",
    )
    parser.set_defaults(run_check=False)
    return parser.parse_args(argv)


def run(cmd: list[str]) -> None:
    display = " ".join(cmd)
    print(f"$ {display}")
    result = subprocess.run(cmd, cwd=REPO_ROOT, text=True)
    if result.returncode != 0:
        raise PackagingError(f"Comando fallito: {display}")


def clean_artifacts() -> None:
    for path in (DIST_DIR, BUILD_DIR):
        if path.exists():
            print(f"[clean] Rimuovo {path.relative_to(REPO_ROOT)}")
            shutil.rmtree(path)

    for egg_info in REPO_ROOT.glob("*.egg-info"):
        print(f"[clean] Rimuovo {egg_info.relative_to(REPO_ROOT)}")
        shutil.rmtree(egg_info)


def build_packages(*, skip_translations: bool) -> None:
    if not skip_translations:
        run([sys.executable, "-m", "build_translations"])
    else:
        print("[skip] Salto la compilazione delle traduzioni")

    run([sys.executable, "-m", "build"])


def check_dist() -> None:
    if not DIST_DIR.exists():
        raise PackagingError("La cartella 'dist/' non esiste: la build è fallita?")

    artifacts = sorted(DIST_DIR.glob("*"))
    if not artifacts:
        raise PackagingError("Nessun file generato in 'dist/'")

    run([sys.executable, "-m", "twine", "check", *[str(path) for path in artifacts]])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        if args.clean:
            clean_artifacts()
        build_packages(skip_translations=args.skip_translations)
        if args.run_check:
            check_dist()
    except PackagingError as error:
        print(f"Errore: {error}")
        return 1
    except FileNotFoundError as error:
        missing = error.filename or str(error)
        print(
            f"Errore: comando non trovato ({missing}). Installa il pacchetto richiesto."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
