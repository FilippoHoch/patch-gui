from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from unidiff import PatchSet

import patch_gui.executor as executor
from patch_gui.patcher import (
    ApplySession,
    HunkDecision,
    HunkView,
    apply_hunk_at_position,
    apply_hunks,
    backup_file,
    DEFAULT_EXCLUDE_DIRS,
    find_candidates,
    find_file_candidates,
    prepare_backup_dir,
    prune_backup_sessions,
    write_reports,
)
from patch_gui.utils import format_session_timestamp


REMOVED_DIFF = """--- a/sample.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-old line
-line2
"""

RENAME_ONLY_DIFF = """diff --git a/sample.txt b/docs/renamed.txt
similarity index 100%
rename from sample.txt
rename to docs/renamed.txt
"""

RENAME_WITH_EDIT_DIFF = """diff --git a/sample.txt b/docs/renamed.txt
similarity index 91%
rename from sample.txt
rename to docs/renamed.txt
--- a/sample.txt
+++ b/docs/renamed.txt
@@ -1,2 +1,2 @@
-old line
+new line
 line2
"""


def _project_with_sample(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "sample.txt").write_text("old line\nline2\n", encoding="utf-8")
    return project


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
    hv = HunkView(
        header="@@ -2,2 +2,2 @@", before_lines=["b\n", "c\n"], after_lines=["B\n"]
    )
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

    new_lines, decisions, applied = apply_hunks(
        file_lines, pf, threshold=0.5, manual_resolver=resolver
    )

    assert new_lines == file_lines
    assert applied == 0
    assert "user cancel" in decisions[0].message
    assert calls and calls[0][3] == "fuzzy"
    assert len(calls[0][2]) > 1


def test_apply_hunks_context_fallback_uses_context_lines() -> None:
    diff = """--- a/sample.txt
+++ b/sample.txt
@@ -1,3 +1,3 @@
 line keep
-line old
+line new
 line end
"""
    patch = PatchSet(diff)
    pf = patch[0]
    file_lines = ["line keep\n", "line end\n"]

    captured: list[tuple[str, list[tuple[int, float]], HunkView]] = []

    def resolver(
        hv: HunkView,
        lines: list[str],
        candidates: list[tuple[int, float]],
        decision: HunkDecision,
        reason: str,
    ) -> None:
        captured.append((reason, list(candidates), hv))
        decision.strategy = "manual"
        decision.message = "context review"
        return None

    new_lines, decisions, applied = apply_hunks(
        file_lines, pf, threshold=0.9, manual_resolver=resolver
    )

    assert new_lines == file_lines
    assert applied == 0
    assert captured and captured[0][0] == "context"
    hv = captured[0][2]
    assert hv.context_lines == ["line keep\n", "line end\n"]
    expected_candidates = find_candidates(file_lines, hv.context_lines, threshold=0.9)
    assert captured[0][1] == expected_candidates
    assert decisions[0].candidates == expected_candidates
    assert "context review" in decisions[0].message


def test_apply_hunks_metadata_fallback_for_insertions_without_context() -> None:
    diff = """--- a/sample.txt
+++ b/sample.txt
@@ -0,0 +1,2 @@
+first line
+second line
"""
    patch = PatchSet(diff)
    pf = patch[0]
    file_lines = ["original\n"]

    new_lines, decisions, applied = apply_hunks(
        file_lines, pf, threshold=0.5, manual_resolver=None
    )

    assert applied == 1
    assert new_lines == ["first line\n", "second line\n", "original\n"]
    assert decisions[0].strategy == "metadata"
    assert decisions[0].selected_pos == 0


def test_apply_hunks_failure_attaches_ai_message() -> None:
    diff = """--- a/sample.txt
+++ b/sample.txt
@@ -1 +1 @@
-expected line
+new line
"""
    patch = PatchSet(diff)
    pf = patch[0]
    file_lines = ["another line\n"]

    new_lines, decisions, applied = apply_hunks(
        file_lines, pf, threshold=0.8, manual_resolver=None
    )

    assert new_lines == file_lines
    assert applied == 0
    assert decisions
    decision = decisions[0]
    assert decision.strategy == "failed"
    assert "Motivo del fallimento:" in decision.message
    assert "Patch suggerita:" in decision.message
    assert "+new line" in decision.message


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


def test_find_file_candidates_excludes_backup_directory(tmp_path: Path) -> None:
    project_root = tmp_path
    included_dir = project_root / "src"
    included_dir.mkdir()
    included_file = included_dir / "module.py"
    included_file.write_text("print('ok')\n", encoding="utf-8")

    timestamp = format_session_timestamp(1704067200.123)
    backup_file = project_root / ".diff_backups" / timestamp / "module.py"
    backup_file.parent.mkdir(parents=True)
    backup_file.write_text("print('backup')\n", encoding="utf-8")

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
    base_dir = tmp_path / "backups"
    base_dir.mkdir()

    started_at = 1735689600.456
    dry_dir = prepare_backup_dir(
        project_root,
        dry_run=True,
        backup_base=base_dir,
        started_at=started_at,
    )
    assert not dry_dir.exists()
    assert dry_dir.name == format_session_timestamp(started_at)

    real_dir = prepare_backup_dir(
        project_root,
        dry_run=False,
        backup_base=base_dir,
        started_at=started_at,
    )
    assert real_dir.exists()
    assert real_dir.name == format_session_timestamp(started_at)


def test_prepare_backup_dir_uses_millisecond_precision(tmp_path: Path) -> None:
    project_root = tmp_path
    base_dir = tmp_path / "millis"
    base_dir.mkdir()

    ts_first = 1735689600.100
    ts_second = 1735689600.101

    first = prepare_backup_dir(
        project_root,
        dry_run=True,
        backup_base=base_dir,
        started_at=ts_first,
    )
    second = prepare_backup_dir(
        project_root,
        dry_run=True,
        backup_base=base_dir,
        started_at=ts_second,
    )

    assert first.parent == base_dir
    assert second.parent == base_dir
    assert first.name == format_session_timestamp(ts_first)
    assert second.name == format_session_timestamp(ts_second)
    assert first.name != second.name


def test_prune_backup_sessions_removes_old_directories(tmp_path: Path) -> None:
    base_dir = tmp_path / "backups"
    base_dir.mkdir()

    reference = datetime(2024, 1, 10, 12, 0, 0)
    old_time = reference - timedelta(days=10)
    recent_time = reference - timedelta(days=2)
    newest_time = reference

    old_dir = base_dir / format_session_timestamp(old_time.timestamp())
    recent_dir = base_dir / format_session_timestamp(recent_time.timestamp())
    newest_dir = base_dir / format_session_timestamp(newest_time.timestamp())

    for path in (old_dir, recent_dir, newest_dir):
        path.mkdir(parents=True)
        (path / "marker.txt").write_text("data", encoding="utf-8")

    removed = prune_backup_sessions(
        base_dir,
        retention_days=5,
        reference_timestamp=reference.timestamp(),
    )

    assert not old_dir.exists()
    assert recent_dir.exists()
    assert newest_dir.exists()
    assert set(removed) == {old_dir}


def test_prune_backup_sessions_ignores_unrelated_entries(tmp_path: Path) -> None:
    base_dir = tmp_path / "backups"
    base_dir.mkdir()

    (base_dir / "reports").mkdir()
    (base_dir / "123-invalid").mkdir()

    result = prune_backup_sessions(
        base_dir,
        retention_days=1,
        reference_timestamp=datetime.now().timestamp(),
    )

    assert result == []
    assert (base_dir / "reports").exists()
    assert (base_dir / "123-invalid").exists()


def test_write_reports_dry_run_skips_backup_dir(tmp_path: Path) -> None:
    session = ApplySession(
        project_root=tmp_path,
        backup_dir=tmp_path / "backups" / "session",
        dry_run=True,
        threshold=0.85,
        started_at=0.0,
    )
    json_dest = tmp_path / "reports" / "apply.json"
    txt_dest = tmp_path / "reports" / "apply.txt"

    write_reports(session, json_path=json_dest, txt_path=txt_dest)

    assert not session.backup_dir.exists()
    assert json_dest.exists()
    assert txt_dest.exists()


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


def test_apply_patchset_reports_rename_only_details(tmp_path: Path) -> None:
    project = _project_with_sample(tmp_path)

    session = executor.apply_patchset(
        PatchSet(RENAME_ONLY_DIFF),
        project,
        dry_run=False,
        threshold=0.85,
    )

    new_path = project / "docs" / "renamed.txt"
    backup_path = session.backup_dir / "sample.txt"

    assert new_path.exists()
    assert backup_path.exists()

    file_result = session.results[0]
    assert file_result.decisions
    assert file_result.decisions[0].strategy == "rename"

    json_report = session.to_json()
    assert json_report["files"][0]["decisions"][0]["strategy"] == "rename"  # type: ignore[index]
    text_report = session.to_txt()
    assert "Hunk rename -> rename" in text_report


def test_apply_patchset_reports_rename_with_edit_details(tmp_path: Path) -> None:
    project = _project_with_sample(tmp_path)

    session = executor.apply_patchset(
        PatchSet(RENAME_WITH_EDIT_DIFF),
        project,
        dry_run=False,
        threshold=0.85,
    )

    new_path = project / "docs" / "renamed.txt"
    backup_path = session.backup_dir / "sample.txt"

    assert new_path.exists()
    assert new_path.read_text(encoding="utf-8") == "new line\nline2\n"
    assert backup_path.exists()

    file_result = session.results[0]
    assert file_result.decisions
    assert file_result.decisions[0].strategy == "rename"
    assert any(d.strategy != "rename" for d in file_result.decisions)

    json_report = session.to_json()
    assert json_report["files"][0]["decisions"][0]["strategy"] == "rename"  # type: ignore[index]
    assert json_report["files"][0]["hunks_applied"] == 1  # type: ignore[index]
    text_report = session.to_txt()
    assert "Hunk rename -> rename" in text_report


def test_apply_file_patch_removes_file_and_keeps_backup(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    target = project_root / "sample.txt"
    original = "old line\nline2\n"
    target.write_text(original, encoding="utf-8")

    patch = PatchSet(REMOVED_DIFF)
    pf = patch[0]
    rel_path = (pf.path or pf.target_file or pf.source_file or "").strip()

    backup_base = tmp_path / "backups"
    backup_dir = prepare_backup_dir(
        project_root,
        dry_run=False,
        backup_base=backup_base,
        started_at=123.456,
    )

    session = ApplySession(
        project_root=project_root,
        backup_dir=backup_dir,
        dry_run=False,
        threshold=0.85,
        started_at=123.456,
    )

    fr = executor._apply_file_patch(
        project_root,
        pf,
        rel_path,
        session,
        interactive=False,
        auto_accept=False,
    )

    assert fr.skipped_reason is None
    assert fr.hunks_applied == fr.hunks_total == 1
    assert not target.exists()

    backup_copy = backup_dir / "sample.txt"
    assert backup_copy.exists()
    assert backup_copy.read_text(encoding="utf-8") == original
