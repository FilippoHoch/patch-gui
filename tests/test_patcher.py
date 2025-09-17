from __future__ import annotations

from pathlib import Path

import pytest
from unidiff import PatchSet

from patch_gui.patcher import (
    HunkDecision,
    HunkView,
    apply_hunk_at_position,
    apply_hunks,
    backup_file,
    DEFAULT_EXCLUDE_DIRS,
    find_candidates,
    find_file_candidates,
    prepare_backup_dir,
)


def test_find_candidates_returns_exact_match_first() -> None:
    file_lines = ["line1\n", "line2\n", "line3\n"]
    before_lines = ["line2\n"]
    assert find_candidates(file_lines, before_lines, threshold=0.5) == [(1, 1.0)]


def test_find_candidates_returns_sorted_fuzzy_matches() -> None:
    file_lines = ["abc\n", "dxf\n", "zzz\n", "ab\n", "def\n"]
    before_lines = ["abc\n", "def\n"]
    result = find_candidates(file_lines, before_lines, threshold=0.5)
    assert len(result) >= 2
    assert result[0][0] == 3
    assert result[0][1] == pytest.approx(0.9333333333)
    assert result[1][0] == 0
    assert result[1][1] == pytest.approx(0.875)


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


def test_apply_hunks_invokes_manual_resolver_for_multiple_candidates() -> None:
    diff = """--- a/sample.txt
+++ b/sample.txt
@@ -1,2 +1,2 @@
-bb
-cc
+BB
+CC
"""
    patch = PatchSet(diff)
    pf = patch[0]
    file_lines = ["bx\n", "cc\n", "bb\n", "cx\n"]

    calls: list[tuple[HunkView, list[str], list[tuple[int, float]], str]] = []

    def resolver(
        hv: HunkView,
        lines: list[str],
        candidates: list[tuple[int, float]],
        decision: HunkDecision,
        reason: str,
    ) -> None:
        calls.append((hv, list(lines), list(candidates), reason))
        decision.strategy = "manual"
        decision.message = "user cancel"
        return None

    new_lines, decisions, applied = apply_hunks(file_lines, pf, threshold=0.5, manual_resolver=resolver)

    assert new_lines == file_lines
    assert applied == 0
    assert decisions[0].message == "user cancel"
    assert calls and calls[0][3] == "fuzzy"
    assert len(calls[0][2]) > 1


def test_find_file_candidates_handles_prefix_and_suffix(tmp_path: Path) -> None:
    project_root = tmp_path
    target = project_root / "src" / "pkg"
    target.mkdir(parents=True)
    (target / "module.py").write_text("print('hi')\n", encoding="utf-8")
    other = project_root / "tests" / "pkg"
    other.mkdir(parents=True)
    (other / "module.py").write_text("print('test')\n", encoding="utf-8")

    result = find_file_candidates(project_root, "a/src/pkg/module.py")
    assert result == [target / "module.py"]


def test_find_file_candidates_excludes_default_directories(tmp_path: Path) -> None:
    project_root = tmp_path
    included_dir = project_root / "src"
    included_dir.mkdir()
    included_file = included_dir / "module.py"
    included_file.write_text("print('ok')\n", encoding="utf-8")

    excluded_file = project_root / DEFAULT_EXCLUDE_DIRS[0] / "module.py"
    excluded_file.parent.mkdir(parents=True)
    excluded_file.write_text("print('ignored')\n", encoding="utf-8")

    result = find_file_candidates(project_root, "module.py")

    assert result == [included_file]


def test_find_file_candidates_allows_overriding_excludes(tmp_path: Path) -> None:
    project_root = tmp_path
    hidden = project_root / ".venv" / "pkg"
    hidden.mkdir(parents=True)
    file_path = hidden / "module.py"
    file_path.write_text("print('hidden')\n", encoding="utf-8")

    assert find_file_candidates(project_root, "module.py") == []

    custom = find_file_candidates(project_root, "module.py", exclude_dirs=())

    assert custom == [file_path]


def test_prepare_backup_dir_respects_dry_run(tmp_path: Path) -> None:
    project_root = tmp_path
    dry_dir = prepare_backup_dir(project_root, dry_run=True)
    assert not dry_dir.exists()

    real_dir = prepare_backup_dir(project_root, dry_run=False)
    assert real_dir.exists()


def test_backup_file_copies_content(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    file_path = project_root / "data.txt"
    file_path.write_text("hello", encoding="utf-8")
    backup_root = tmp_path / "backup"

    backup_file(project_root, file_path, backup_root)

    copied = backup_root / "data.txt"
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == "hello"
