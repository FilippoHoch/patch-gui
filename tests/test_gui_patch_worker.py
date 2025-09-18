"""Regression tests for the GUI patch application worker."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from unidiff import PatchSet

from patch_gui.patcher import ApplySession, prepare_backup_dir

try:  # pragma: no cover - optional dependency
    from PySide6 import QtWidgets as _QtWidgets
except Exception as exc:  # pragma: no cover - PySide6 missing in environment
    QtWidgets: Any | None = None
    _QT_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - executed when bindings are available
    QtWidgets = _QtWidgets
    _QT_IMPORT_ERROR = None


ADDED_DIFF = """--- /dev/null
+++ b/new_dir/example.txt
@@ -0,0 +1,2 @@
+first line
+second line
"""


REMOVED_DIFF = """--- a/sample.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-first line
-second line
"""


OUTSIDE_DIFF = """--- /dev/null
+++ b/../outside.txt
@@ -0,0 +1 @@
+sneaky
"""


@pytest.fixture()
def qt_app() -> Any:
    """Provide a ``QApplication`` instance for tests that need Qt."""

    if QtWidgets is None:  # pragma: no cover - PySide6 missing
        pytest.skip(f"PySide6 non disponibile: {_QT_IMPORT_ERROR}")

    assert QtWidgets is not None
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _build_session(project_root: Path, *, dry_run: bool) -> ApplySession:
    backup_base = project_root.parent / "backups"
    backup_dir = prepare_backup_dir(
        project_root,
        dry_run=dry_run,
        backup_base=backup_base,
        started_at=1234.5,
    )
    return ApplySession(
        project_root=project_root,
        backup_dir=backup_dir,
        dry_run=dry_run,
        threshold=0.85,
        started_at=1234.5,
    )


def _relative_from_patch(pf: Any) -> str:
    return (pf.path or pf.target_file or pf.source_file or "").strip()


def test_worker_applies_added_file_and_creates_directories(
    qt_app: Any, tmp_path: Path
) -> None:
    from patch_gui.app import PatchApplyWorker

    project_root = tmp_path / "project"
    project_root.mkdir()

    patch = PatchSet(ADDED_DIFF)
    pf = patch[0]
    rel_path = _relative_from_patch(pf)

    session = _build_session(project_root, dry_run=False)
    worker = PatchApplyWorker(patch, session)

    result = worker.apply_file_patch(pf, rel_path)

    assert result.skipped_reason is None
    assert result.hunks_applied == result.hunks_total == 1

    created_file = project_root / "new_dir" / "example.txt"
    assert created_file.exists()
    assert created_file.read_text(encoding="utf-8") == "first line\nsecond line\n"

    backup_contents = list(session.backup_dir.rglob("*"))
    assert all(not item.is_file() for item in backup_contents)


def test_worker_removes_file_and_preserves_backup(qt_app: Any, tmp_path: Path) -> None:
    from patch_gui.app import PatchApplyWorker

    project_root = tmp_path / "project"
    project_root.mkdir()

    target = project_root / "sample.txt"
    original = "first line\nsecond line\n"
    target.write_text(original, encoding="utf-8")

    patch = PatchSet(REMOVED_DIFF)
    pf = patch[0]
    rel_path = _relative_from_patch(pf)

    session = _build_session(project_root, dry_run=False)
    worker = PatchApplyWorker(patch, session)

    result = worker.apply_file_patch(pf, rel_path)

    assert result.skipped_reason is None
    assert result.hunks_applied == result.hunks_total == 1
    assert not target.exists()

    backup_copy = session.backup_dir / "sample.txt"
    assert backup_copy.exists()
    assert backup_copy.read_text(encoding="utf-8") == original


def test_worker_rejects_new_file_outside_project_root(
    qt_app: Any, tmp_path: Path
) -> None:
    from patch_gui.app import PatchApplyWorker

    project_root = tmp_path / "project"
    project_root.mkdir()

    patch = PatchSet(OUTSIDE_DIFF)
    pf = patch[0]
    rel_path = _relative_from_patch(pf)

    session = _build_session(project_root, dry_run=False)
    worker = PatchApplyWorker(patch, session)

    result = worker.apply_file_patch(pf, rel_path)

    assert result.hunks_applied == 0
    assert result.skipped_reason is not None
    assert "root" in result.skipped_reason.lower()

    outside_target = project_root.parent / "outside.txt"
    assert not outside_target.exists()
