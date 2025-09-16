from __future__ import annotations

import pytest

from patch_gui.patcher import HunkView, apply_hunk_at_position, find_candidates


def test_find_candidates_returns_exact_match_first() -> None:
    file_lines = ["line1\n", "line2\n", "line3\n"]
    before_lines = ["line2\n"]
    assert find_candidates(file_lines, before_lines, threshold=0.5) == [(1, 1.0)]


def test_find_candidates_returns_sorted_fuzzy_matches() -> None:
    file_lines = ["abc\n", "dxf\n", "zzz\n", "ab\n", "def\n"]
    before_lines = ["abc\n", "def\n"]
    result = find_candidates(file_lines, before_lines, threshold=0.5)
    assert result == [(3, pytest.approx(0.9333333333)), (0, pytest.approx(0.875))]


def test_find_candidates_with_empty_before_lines_returns_empty() -> None:
    assert find_candidates(["line\n"], [], threshold=0.5) == []


def test_apply_hunk_at_position_replaces_expected_window() -> None:
    file_lines = ["a\n", "b\n", "c\n"]
    hv = HunkView(header="@@ -2 +2 @@", before_lines=["b\n"], after_lines=["B\n"])
    result = apply_hunk_at_position(file_lines, hv, pos=1)
    assert result == ["a\n", "B\n", "c\n"]


def test_apply_hunk_at_position_raises_when_window_exceeds_length() -> None:
    file_lines = ["a\n", "b\n"]
    hv = HunkView(header="@@ -2,2 +2,2 @@", before_lines=["b\n", "c\n"], after_lines=["B\n"])
    with pytest.raises(IndexError):
        apply_hunk_at_position(file_lines, hv, pos=1)
