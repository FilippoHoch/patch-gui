import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest

from patch_gui.ai_summaries import AISummary, generate_session_summary
from patch_gui.patcher import ApplySession
from tests._pytest_typing import typed_fixture

try:  # pragma: no cover - optional dependency
    from PySide6 import QtWidgets as _QtWidgets
except Exception as exc:  # pragma: no cover - PySide6 missing in environment
    QtWidgets: Any | None = None
    _QT_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - executed when bindings are available
    QtWidgets = cast(Any, _QtWidgets)
    _QT_IMPORT_ERROR = None


def _build_session(tmp_path: Path) -> ApplySession:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(exist_ok=True)
    session = ApplySession(
        project_root=tmp_path,
        backup_dir=backup_dir,
        dry_run=True,
        threshold=0.9,
        started_at=1234.5,
    )
    return session


def test_generate_session_summary_uses_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import patch_gui.ai_summaries as summaries_module

    monkeypatch.setattr(summaries_module, "_SUMMARY_CACHE", {})

    calls: list[dict[str, object]] = []

    def fake_call(payload: dict[str, object], *, timeout: float) -> dict[str, object]:
        calls.append(payload)
        return {
            "summary": "Overall text",
            "files": {"file.txt": "File level summary"},
        }

    monkeypatch.setattr(summaries_module, "_call_summary_service", fake_call)

    session_a = _build_session(tmp_path)
    session_a.summary_diff_digest = "digest"
    summary_a = generate_session_summary(session_a)

    assert summary_a is not None
    assert summary_a.overall == "Overall text"
    assert session_a.summary_cache_hit is False
    assert session_a.summary_duration is not None
    assert calls and calls[0]["project_root"] == str(tmp_path)

    session_b = _build_session(tmp_path)
    session_b.summary_diff_digest = "digest"
    summary_b = generate_session_summary(session_b)

    assert summary_b is not None
    assert summary_b.overall == "Overall text"
    assert session_b.summary_cache_hit is True
    assert session_b.summary_duration == 0.0
    assert len(calls) == 1


@typed_fixture()
def qt_app() -> Any:
    if QtWidgets is None:  # pragma: no cover - PySide6 missing
        pytest.skip(f"PySide6 non disponibile: {_QT_IMPORT_ERROR}")

    assert QtWidgets is not None
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def test_ai_summary_worker_non_blocking(
    qt_app: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from patch_gui import app as app_module

    session = _build_session(tmp_path)
    session.summary_diff_digest = "digest"

    start_event = threading.Event()
    release_event = threading.Event()
    done_event = threading.Event()
    thread_name: dict[str, str] = {}
    results: dict[str, Any] = {}
    errors: dict[str, Any] = {}

    def fake_generate(
        session_arg: ApplySession,
        *,
        use_cache: bool = True,
        timeout: float = 15.0,
        hooks: Any | None = None,
    ) -> AISummary:
        thread_name["name"] = threading.current_thread().name
        if hooks is not None and hooks.on_start is not None:
            hooks.on_start({})
        start_event.set()
        release_event.wait(1.0)
        summary = AISummary(overall="Completato", per_file={})
        if hooks is not None and hooks.on_complete is not None:
            hooks.on_complete(summary, False)
        return summary

    monkeypatch.setattr(app_module, "generate_session_summary", fake_generate)

    worker = app_module.AISummaryWorker(session)

    def handle_completed(session_arg: ApplySession, summary_obj: object) -> None:
        results["summary"] = summary_obj
        done_event.set()

    def handle_failed(session_arg: ApplySession, message: str) -> None:
        errors["message"] = message
        done_event.set()

    worker.completed.connect(handle_completed)
    worker.failed.connect(handle_failed)
    worker.start()

    assert start_event.wait(1.0)
    assert (
        thread_name.get("name")
        and thread_name["name"] != threading.current_thread().name
    )
    assert "summary" not in results

    release_event.set()

    deadline = time.time() + 2.0
    while not done_event.is_set() and time.time() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)

    worker.wait(1000)

    assert done_event.is_set()
    assert not errors
    assert isinstance(results.get("summary"), AISummary)
    assert results["summary"].overall == "Completato"
