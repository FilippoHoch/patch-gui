from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from patch_gui import ai_conflict_helper
from patch_gui.ai_conflict_helper import (
    AI_CONFLICT_ENDPOINT_ENV,
    AI_SHARED_ENDPOINT_ENV,
    ConflictSuggestion,
    generate_conflict_suggestion,
)


def _build_args() -> dict[str, Any]:
    return {
        "file_context": "// sample file context\nconst value = 1;\n",
        "hunk_header": "@@ -1,2 +1,6 @@",
        "before_lines": ["const value = 1;\n"],
        "after_lines": ["const value = 2;\n"],
        "failure_reason": "Unexpected hunk found",
        "original_diff": "@@ -1 +1 @@\n-const value = 1;\n+const value = 2;\n",
    }


def test_generate_conflict_suggestion_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(AI_CONFLICT_ENDPOINT_ENV, raising=False)
    monkeypatch.delenv(AI_SHARED_ENDPOINT_ENV, raising=False)

    suggestion = generate_conflict_suggestion(**_build_args())

    assert suggestion is not None
    assert isinstance(suggestion, ConflictSuggestion)
    assert suggestion.source == "heuristic"
    assert "Suggerimento assistente" in suggestion.message
    assert suggestion.patch is not None


class _DummyResponse:
    def __init__(self, payload: dict[str, Any]):
        self._body = json.dumps(payload).encode("utf-8")
        self.headers = SimpleNamespace(get_content_charset=lambda default=None: "utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_DummyResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_generate_conflict_suggestion_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    called_payload: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float = 0.0) -> _DummyResponse:
        nonlocal called_payload
        called_payload = json.loads(request.data.decode("utf-8"))
        return _DummyResponse(
            {
                "message": "AI suggerisce di aggiornare il blocco.",
                "patch": "@@ -1 +1 @@\n-const value = 1;\n+const value = 2;\n",
                "confidence": 0.87,
                "source": "assistant",
            }
        )

    monkeypatch.setenv(AI_CONFLICT_ENDPOINT_ENV, "https://example.invalid/ai")
    monkeypatch.setattr(ai_conflict_helper.urllib.request, "urlopen", fake_urlopen)

    suggestion = generate_conflict_suggestion(**_build_args())

    assert suggestion is not None
    assert suggestion.source == "assistant"
    assert suggestion.confidence == pytest.approx(0.87)
    assert "AI suggerisce" in suggestion.message
    assert suggestion.patch is not None
    assert called_payload["task"] == "conflict-resolution"
    assert called_payload["before"] == ["const value = 1;\n"]
