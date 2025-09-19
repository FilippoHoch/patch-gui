from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import pytest

from patch_gui.cli import run_cli
from patch_gui.config import AppConfig
from patch_gui.logging_utils import (
    LOG_BACKUP_COUNT_ENV_VAR,
    LOG_FILE_ENV_VAR,
    LOG_MAX_BYTES_ENV_VAR,
    configure_logging,
)
from tests._pytest_typing import typed_fixture


def _cleanup_file_handlers() -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # pragma: no cover - defensive cleanup
            pass


@typed_fixture()
def clean_file_handlers() -> Iterator[None]:
    _cleanup_file_handlers()
    try:
        yield None
    finally:
        _cleanup_file_handlers()


def test_configure_logging_uses_rotating_handler(
    tmp_path: Path, clean_file_handlers: None
) -> None:
    log_path = tmp_path / "app.log"

    configure_logging(level="INFO", log_file=log_path, max_bytes=1234, backup_count=3)

    handlers = [
        h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)
    ]
    assert len(handlers) == 1

    handler = handlers[0]
    from logging.handlers import RotatingFileHandler

    assert isinstance(handler, RotatingFileHandler)
    assert handler.baseFilename == str(log_path)
    assert int(handler.maxBytes) == 1234
    assert int(handler.backupCount) == 3


def test_configure_logging_reads_environment(
    tmp_path: Path, clean_file_handlers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = tmp_path / "env.log"

    monkeypatch.setenv(LOG_FILE_ENV_VAR, str(log_path))
    monkeypatch.setenv(LOG_MAX_BYTES_ENV_VAR, "50")
    monkeypatch.setenv(LOG_BACKUP_COUNT_ENV_VAR, "2")

    configure_logging(level="DEBUG")

    from logging.handlers import RotatingFileHandler

    handler = next(
        h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)
    )
    assert handler.baseFilename == str(log_path)
    assert int(handler.maxBytes) == 50
    assert int(handler.backupCount) == 2


def test_configure_logging_rotates_files(
    tmp_path: Path, clean_file_handlers: None
) -> None:
    log_path = tmp_path / "rotate.log"

    configure_logging(level="INFO", log_file=log_path, max_bytes=150, backup_count=1)

    logger = logging.getLogger("rotation-test")
    message = "x" * 200
    for _ in range(3):
        logger.info(message)

    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()

    backup_path = Path(str(log_path) + ".1")
    assert log_path.exists()
    assert backup_path.exists()
    assert backup_path.stat().st_size > 0


def test_run_cli_respects_log_configuration(
    tmp_path: Path, clean_file_handlers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = tmp_path / "cli.log"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    config = AppConfig()
    config.log_file = log_path
    config.log_max_bytes = 150
    config.log_backup_count = 1
    config.log_level = "info"
    config.backup_base = backup_dir

    class _DummySession:
        def __init__(self) -> None:
            self.backup_dir = backup_dir
            self.report_json_path: Path | None = None
            self.report_txt_path: Path | None = None

        def to_txt(self) -> str:
            return "summary"

        def to_json(self) -> dict[str, str]:
            return {"status": "ok"}

    def _fake_load_patch(path: str, *, encoding: str | None = None) -> object:
        return object()

    def _fake_apply_patchset(*args: object, **kwargs: object) -> _DummySession:
        logger = logging.getLogger("cli-test")
        message = "x" * 200
        for _ in range(3):
            logger.info(message)
        return _DummySession()

    monkeypatch.setattr("patch_gui.cli.load_config", lambda path=None: config)
    monkeypatch.setattr("patch_gui.cli.load_patch", _fake_load_patch)
    monkeypatch.setattr("patch_gui.cli.apply_patchset", _fake_apply_patchset)
    monkeypatch.setattr("patch_gui.cli.session_completed", lambda session: True)

    result = run_cli([
        "dummy.patch",
        "--root",
        str(tmp_path),
        "--summary-format",
        "none",
        "--log-level",
        "info",
    ])

    assert result == 0

    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()

    backup_path = Path(str(log_path) + ".1")
    assert log_path.exists()
    assert backup_path.exists()
    assert backup_path.stat().st_size > 0
