from __future__ import annotations

from typing import Any

import pytest

from patch_gui import matching
from patch_gui.matching import MatchingStrategy


def test_auto_strategy_matches_legacy_results() -> None:
    file_lines = [
        "alpha\n",
        "beta\n",
        "gamma\n",
        "delta\n",
        "epsilon\n",
        "beta\n",
        "gamma\n",
    ]
    before_lines = ["beta\n", "gamma\n"]

    legacy = matching.find_candidate_positions(
        file_lines, before_lines, 0.7, strategy=MatchingStrategy.LEGACY
    )
    auto = matching.find_candidate_positions(
        file_lines, before_lines, 0.7, strategy=MatchingStrategy.AUTO
    )

    assert auto == legacy


def test_token_strategy_limits_sequence_matcher_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = {"value": 0}
    original_matcher = matching.SequenceMatcher

    class CountingMatcher:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            call_count["value"] += 1
            self._delegate = original_matcher(*args, **kwargs)

        def ratio(self) -> float:
            return self._delegate.ratio()

        def __getattr__(self, name: str) -> Any:  # pragma: no cover - safety net
            return getattr(self._delegate, name)

    monkeypatch.setattr(matching, "SequenceMatcher", CountingMatcher)

    file_lines = [f"line {i}\n" for i in range(200)]
    before_lines = [f"line {i}\n" for i in range(80, 90)]
    file_lines[84] = "line 84 changed\n"

    matching.find_candidate_positions(
        file_lines, before_lines, 0.95, strategy=MatchingStrategy.TOKEN
    )
    token_calls = call_count["value"]
    call_count["value"] = 0
    matching.find_candidate_positions(
        file_lines, before_lines, 0.95, strategy=MatchingStrategy.LEGACY
    )
    legacy_calls = call_count["value"]

    assert token_calls < legacy_calls


def test_find_candidate_positions_handles_empty_before_lines() -> None:
    assert (
        matching.find_candidate_positions(
            ["one\n", "two\n"], [], 0.5, strategy=MatchingStrategy.AUTO
        )
        == []
    )
