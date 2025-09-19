from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from patch_gui import ai_summaries
from patch_gui.ai_summaries import AISummaryHooks, compute_summary_cache_key
from patch_gui.patcher import ApplySession


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    ai_summaries.clear_summary_cache()


def _make_session(tmp_path: Path) -> ApplySession:
    project_root = tmp_path / "project"
    project_root.mkdir(exist_ok=True)
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir(exist_ok=True)
    return ApplySession(
        project_root=project_root,
        backup_dir=backup_dir,
        dry_run=True,
        threshold=0.7,
        started_at=1234.5,
    )


def test_generate_session_summary_uses_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session = _make_session(tmp_path)
    session.summary_cache_key = compute_summary_cache_key("example diff")

    events: list[Any] = []

    def fake_call(
        payload: dict[str, object],
        *,
        timeout: float | None = None,
        hooks: AISummaryHooks | None = None,
    ) -> dict[str, object]:
        events.append(payload)
        if hooks and hooks.on_request_start:
            hooks.on_request_start()
        if hooks and hooks.on_raw_chunk:
            hooks.on_raw_chunk(b"chunk")
        response = {"summary": "overall", "files": {"file.py": "detail"}}
        if hooks and hooks.on_response:
            hooks.on_response(response)
        return response

    monkeypatch.setattr(ai_summaries, "_call_summary_service", fake_call)

    hooks = AISummaryHooks(
        on_request_start=lambda: events.append("start"),
        on_raw_chunk=lambda chunk: events.append(("chunk", bytes(chunk))),
        on_response=lambda response: events.append(("response", dict(response))),
    )

    summary = ai_summaries.generate_session_summary(session, hooks=hooks)

    assert summary is not None
    assert session.summary_cache_hit is False
    assert session.summary_generated_at is not None
    assert events[1:] == ["start", ("chunk", b"chunk"), ("response", {"summary": "overall", "files": {"file.py": "detail"}})]

    new_session = _make_session(tmp_path)
    new_session.summary_cache_key = session.summary_cache_key

    cached_summary = ai_summaries.generate_session_summary(new_session)

    assert cached_summary is summary
    assert new_session.summary_cache_hit is True
    assert new_session.summary_cached_at is not None
    # ``fake_call`` should only run once.
    assert len(events) == 4


def test_generate_session_summary_records_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session = _make_session(tmp_path)
    session.summary_cache_key = "abc"

    def fake_call(
        payload: dict[str, object],
        *,
        timeout: float | None = None,
        hooks: AISummaryHooks | None = None,
    ) -> dict[str, object]:
        raise ai_summaries.AISummaryError("boom")

    monkeypatch.setattr(ai_summaries, "_call_summary_service", fake_call)

    result = ai_summaries.generate_session_summary(session, use_cache=False)

    assert result is None
    assert session.summary_error == "boom"
