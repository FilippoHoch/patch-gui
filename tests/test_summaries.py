from __future__ import annotations

import logging
from pathlib import Path
from typing import Mapping

import pytest

from patch_gui.patcher import ApplySession, FileResult
from patch_gui.summaries import (
    AI_SUMMARY_ENDPOINT_ENV,
    build_local_summary,
    generate_ai_summary,
)


class _DummyResponse:
    def __init__(self, payload: bytes, headers: Mapping[str, str] | None = None) -> None:
        self._payload = payload
        self.headers = dict(headers or {"Content-Type": "application/json; charset=utf-8"})

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_DummyResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None


@pytest.fixture
def session(tmp_path: Path) -> ApplySession:
    project = tmp_path / "project"
    project.mkdir()
    results = [
        FileResult(
            file_path=project / "sample.txt",
            relative_to_root="sample.txt",
            hunks_applied=1,
            hunks_total=2,
        ),
        FileResult(
            file_path=project / "skipped.txt",
            relative_to_root="skipped.txt",
            hunks_applied=0,
            hunks_total=1,
            skipped_reason="missing context",
        ),
    ]
    session = ApplySession(
        project_root=project,
        backup_dir=tmp_path / "backup",
        dry_run=False,
        threshold=0.85,
        started_at=0.0,
    )
    session.results.extend(results)
    return session


def test_build_local_summary_lists_changed_and_skipped(session: ApplySession) -> None:
    summary = build_local_summary(session)

    assert "Files processed: 2" in summary
    assert "Hunks applied: 1/3" in summary
    assert "sample.txt (1/2)" in summary
    assert "skipped.txt (0/1) – missing context" in summary


def test_generate_ai_summary_without_endpoint_skips_network(
    session: ApplySession,
) -> None:
    def unexpected_call(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("opener should not be used when endpoint is missing")

    summary = generate_ai_summary(session, environ={}, opener=unexpected_call)

    assert "Files processed: 2" in summary


def test_generate_ai_summary_uses_remote_payload(session: ApplySession) -> None:
    called: dict[str, object] = {}

    def opener(req, timeout):  # type: ignore[no-untyped-def]
        called["url"] = req.full_url
        called["authorization"] = req.get_header("Authorization")
        called["timeout"] = timeout
        called["body"] = req.data
        payload = b'{"summary": "AI overview"}'
        return _DummyResponse(payload)

    summary = generate_ai_summary(
        session,
        environ={
            AI_SUMMARY_ENDPOINT_ENV: "https://example.test/api",
            "PATCH_GUI_AI_SUMMARY_TOKEN": "Bearer secret",
            "PATCH_GUI_AI_SUMMARY_TIMEOUT": "5",
        },
        opener=opener,
    )

    assert summary == "AI overview"
    assert called["url"] == "https://example.test/api"
    assert called["authorization"] == "Bearer secret"
    assert called["timeout"] == 5.0
    assert isinstance(called["body"], bytes)


def test_generate_ai_summary_logs_failure(
    session: ApplySession, caplog: pytest.LogCaptureFixture
) -> None:
    class BoomOpener:
        def __call__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            from urllib import error as urllib_error

            raise urllib_error.URLError("boom")

    with caplog.at_level(logging.WARNING):
        summary = generate_ai_summary(
            session,
            environ={AI_SUMMARY_ENDPOINT_ENV: "https://example.test/api"},
            opener=BoomOpener(),
        )

    assert "Files processed: 2" in summary
    assert any("AI summary request failed" in message for message in caplog.messages)
