from __future__ import annotations

import logging
from pathlib import Path
import importlib
import importlib.util
import sys
import types
from typing import Any, Iterator

import pytest
from logging.handlers import RotatingFileHandler


class _DummyAttr:
    def __call__(self, *args: object, **kwargs: object) -> "_DummyAttr":
        return self

    def __getattr__(self, name: str) -> "_DummyAttr":  # pragma: no cover - fallback helper
        return self

    def connect(self, *args: object, **kwargs: object) -> None:
        return None

    def emit(self, *args: object, **kwargs: object) -> None:
        return None

    def __or__(self, other: object) -> "_DummyAttr":
        return self

    __ror__ = __or__

    def __and__(self, other: object) -> "_DummyAttr":
        return self

    __rand__ = __and__


_DUMMY_ATTR = _DummyAttr()


class _DummyMeta(type):
    def __getattr__(cls, name: str) -> _DummyAttr:  # pragma: no cover - fallback helper
        return _DUMMY_ATTR

    def __call__(cls, *args: object, **kwargs: object) -> _DummyAttr:
        return _DUMMY_ATTR


class _DummyQtClass(metaclass=_DummyMeta):
    def __init__(self, *args: object, **kwargs: object) -> None:
        return None

    def __getattr__(self, name: str) -> _DummyAttr:  # pragma: no cover - fallback helper
        return _DUMMY_ATTR

    def __call__(self, *args: object, **kwargs: object) -> _DummyAttr:
        return _DUMMY_ATTR


class _DummyQtModule(types.ModuleType):
    def __getattr__(self, name: str) -> type[_DummyQtClass]:  # pragma: no cover - fallback helper
        return _DummyQtClass


class _DummyQtPackage(types.ModuleType):
    QtCore: _DummyQtModule
    QtGui: _DummyQtModule
    QtWidgets: _DummyQtModule


_py_side_spec = importlib.util.find_spec("PySide6")
_needs_stub = _py_side_spec is None

if not _needs_stub:
    try:  # pragma: no cover - environment-dependent
        importlib.import_module("PySide6")
        importlib.import_module("PySide6.QtCore")
        importlib.import_module("PySide6.QtGui")
        importlib.import_module("PySide6.QtWidgets")
    except Exception:  # pragma: no cover - fallback when bindings are partially installed
        _needs_stub = True
        for name in ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]:
            sys.modules.pop(name, None)

if _needs_stub:  # pragma: no cover - environment-dependent
    qt_module = _DummyQtPackage("PySide6")
    setattr(qt_module, "__path__", [])
    qt_core: _DummyQtModule = _DummyQtModule("PySide6.QtCore")
    qt_gui: _DummyQtModule = _DummyQtModule("PySide6.QtGui")
    qt_widgets: _DummyQtModule = _DummyQtModule("PySide6.QtWidgets")

    qt_module.QtCore = qt_core
    qt_module.QtGui = qt_gui
    qt_module.QtWidgets = qt_widgets

    sys.modules["PySide6"] = qt_module
    sys.modules["PySide6.QtCore"] = qt_core
    sys.modules["PySide6.QtGui"] = qt_gui
    sys.modules["PySide6.QtWidgets"] = qt_widgets


from patch_gui.app import (  # noqa: E402  # isort:skip
    LOG_BACKUP_COUNT_ENV_VAR,
    LOG_FILE_ENV_VAR,
    LOG_MAX_BYTES_ENV_VAR,
    configure_logging,
)


def _cleanup_file_handlers() -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pragma: no cover - defensive cleanup
                pass


@pytest.fixture
def clean_file_handlers() -> Iterator[None]:
    _cleanup_file_handlers()
    try:
        yield None
    finally:
        _cleanup_file_handlers()


def test_configure_logging_uses_rotating_handler(tmp_path: Path, clean_file_handlers: None) -> None:
    log_path = tmp_path / "app.log"

    configure_logging(level="INFO", log_file=log_path, max_bytes=1234, backup_count=3)

    handlers = [h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)]
    assert len(handlers) == 1

    handler = handlers[0]
    assert isinstance(handler, RotatingFileHandler)
    assert handler.baseFilename == str(log_path)
    assert handler.maxBytes == 1234
    assert handler.backupCount == 3


def test_configure_logging_reads_environment(
    tmp_path: Path, clean_file_handlers: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = tmp_path / "env.log"

    monkeypatch.setenv(LOG_FILE_ENV_VAR, str(log_path))
    monkeypatch.setenv(LOG_MAX_BYTES_ENV_VAR, "50")
    monkeypatch.setenv(LOG_BACKUP_COUNT_ENV_VAR, "2")

    configure_logging(level="DEBUG")

    handler = next(h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler))
    assert handler.baseFilename == str(log_path)
    assert handler.maxBytes == 50
    assert handler.backupCount == 2


def test_configure_logging_rotates_files(tmp_path: Path, clean_file_handlers: None) -> None:
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
