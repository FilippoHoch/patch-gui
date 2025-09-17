"""Argument parser helpers for the ``patch_gui`` CLI."""

from __future__ import annotations

import argparse
from typing import Optional

from .utils import APP_NAME, BACKUP_DIR, REPORT_JSON, REPORT_TXT

LOG_LEVEL_CHOICES = ("critical", "error", "warning", "info", "debug")

__all__ = ["LOG_LEVEL_CHOICES", "build_parser", "threshold_value"]


def build_parser(parser: Optional[argparse.ArgumentParser] = None) -> argparse.ArgumentParser:
    """Create or enrich an ``ArgumentParser`` with CLI options."""

    if parser is None:
        parser = argparse.ArgumentParser(
            prog="patch-gui apply",
            description=(
                f"{APP_NAME}: applica una patch unified diff usando le stesse euristiche "
                "della GUI, ma dalla riga di comando."
            ),
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
    else:
        parser.description = (
            f"{APP_NAME}: applica una patch unified diff usando le stesse euristiche "
            "della GUI, ma dalla riga di comando."
        )
        parser.formatter_class = argparse.ArgumentDefaultsHelpFormatter
    parser.add_argument(
        "patch",
        help="Percorso del file diff da applicare (usa '-' per leggere da STDIN).",
    )
    parser.add_argument(
        "--root",
        required=True,
        help="Root del progetto su cui applicare la patch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula l'applicazione senza modificare i file o creare backup.",
    )
    parser.add_argument(
        "--threshold",
        type=threshold_value,
        default=0.85,
        help="Soglia (0-1) per il matching fuzzy del contesto.",
    )
    parser.add_argument(
        "--backup",
        help=(
            "Cartella base per backup e report; di default viene utilizzato "
            "'<root>/%s'." % BACKUP_DIR
        ),
    )
    parser.add_argument(
        "--report-json",
        help=(
            "Percorso del report JSON generato; di default '<backup>/%s'."
            % REPORT_JSON
        ),
    )
    parser.add_argument(
        "--report-txt",
        help=(
            "Percorso del report testuale generato; di default '<backup>/%s'."
            % REPORT_TXT
        ),
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Non creare i file di report JSON/TXT.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help=(
            "Disabilita le richieste interattive su STDIN e mantiene il "
            "comportamento precedente in caso di ambiguità."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=LOG_LEVEL_CHOICES,
        help=(
            "Livello di logging da inviare su stdout (debug, info, warning, error, critical)."
        ),
    )
    return parser


def threshold_value(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:  # pragma: no cover - argparse already handles typical errors
        raise argparse.ArgumentTypeError("La soglia deve essere un numero decimale.") from exc
    if not 0 < parsed <= 1:
        raise argparse.ArgumentTypeError(
            "La soglia deve essere compresa tra 0 (escluso) e 1 (incluso)."
        )
    return parsed
