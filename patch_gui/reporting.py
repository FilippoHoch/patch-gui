"""Utilities for generating CLI reports."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from .patcher import ApplySession, write_reports

__all__ = ["coerce_report_path", "write_session_reports"]


def write_session_reports(
    session: ApplySession,
    *,
    report_json: Path | str | None,
    report_txt: Path | str | None,
    enable_reports: bool,
    write_json: bool = True,
    write_txt: bool = True,
) -> Tuple[Optional[Path], Optional[Path]]:
    if not enable_reports or (not write_json and not write_txt):
        session.report_json_path = None
        session.report_txt_path = None
        return None, None

    json_path = coerce_report_path(report_json)
    txt_path = coerce_report_path(report_txt)

    written = write_reports(
        session,
        json_path=json_path,
        txt_path=txt_path,
        write_json=write_json,
        write_txt=write_txt,
    )
    session.report_json_path, session.report_txt_path = written
    return written


def coerce_report_path(value: Path | str | None) -> Optional[Path]:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.expanduser()
    cleaned = value.strip()
    if not cleaned:
        return None
    return Path(cleaned).expanduser()
