from __future__ import annotations

import json
from pathlib import Path

from unidiff import PatchSet

from patch_gui import cli
from patch_gui.utils import BACKUP_DIR, REPORT_JSON, REPORT_TXT

SAMPLE_DIFF = """--- a/sample.txt
+++ b/sample.txt
@@ -1,2 +1,2 @@
-old line
+new line
 line2
"""


def _create_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "sample.txt").write_text("old line\nline2\n", encoding="utf-8")
    return project


def test_apply_patchset_dry_run(tmp_path) -> None:
    project = _create_project(tmp_path)

    session = cli.apply_patchset(
        PatchSet(SAMPLE_DIFF),
        project,
        dry_run=True,
        threshold=0.85,
    )

    target = project / "sample.txt"
    assert target.read_text(encoding="utf-8") == "old line\nline2\n"
    assert session.dry_run is True
    assert not session.backup_dir.exists()
    assert len(session.results) == 1

    file_result = session.results[0]
    assert file_result.skipped_reason is None
    assert file_result.hunks_applied == file_result.hunks_total == 1


def test_apply_patchset_real_run_creates_backup(tmp_path) -> None:
    project = _create_project(tmp_path)
    target = project / "sample.txt"
    original = target.read_text(encoding="utf-8")

    session = cli.apply_patchset(
        PatchSet(SAMPLE_DIFF),
        project,
        dry_run=False,
        threshold=0.85,
    )

    assert target.read_text(encoding="utf-8") == "new line\nline2\n"
    assert session.backup_dir.parent.name == BACKUP_DIR
    assert session.backup_dir.exists()

    backup_copy = session.backup_dir / "sample.txt"
    assert backup_copy.exists()
    assert backup_copy.read_text(encoding="utf-8") == original

    json_report = session.backup_dir / REPORT_JSON
    text_report = session.backup_dir / REPORT_TXT
    assert json_report.exists()
    assert text_report.exists()

    data = json.loads(json_report.read_text(encoding="utf-8"))
    assert data["files"][0]["hunks_applied"] == 1

    file_result = session.results[0]
    assert file_result.hunks_applied == file_result.hunks_total == 1


def test_apply_patchset_with_non_utf8_patch(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / "accento.txt"

    original_text = "riga con accénto\nseconda linea\n"
    modified_text = "riga aggiornata con accénto\nseconda linea\n"
    target.write_bytes(original_text.encode("utf-16"))

    patch_text = (
        "--- a/accento.txt\n"
        "+++ b/accento.txt\n"
        "@@ -1,2 +1,2 @@\n"
        "-riga con accénto\n"
        "+riga aggiornata con accénto\n"
        " seconda linea\n"
    )
    patch_file = tmp_path / "accento.diff"
    patch_file.write_bytes(patch_text.encode("utf-16"))

    patch = cli.load_patch(str(patch_file))
    session = cli.apply_patchset(
        patch,
        project,
        dry_run=False,
        threshold=0.85,
    )

    file_result = session.results[0]
    assert file_result.skipped_reason is None
    assert file_result.hunks_applied == file_result.hunks_total == 1

    assert target.read_bytes() == modified_text.encode("utf-16")
    backup_copy = session.backup_dir / "accento.txt"
    assert backup_copy.exists()
    assert backup_copy.read_bytes() == original_text.encode("utf-16")
