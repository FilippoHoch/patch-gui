from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pytest
from unidiff import PatchSet

from patch_gui import cli
import patch_gui.executor as executor
import patch_gui.utils as utils
import patch_gui.parser as parser
from patch_gui.utils import BACKUP_DIR, REPORT_JSON, REPORT_TXT

SAMPLE_DIFF = """--- a/sample.txt
+++ b/sample.txt
@@ -1,2 +1,2 @@
-old line
+new line
 line2
"""

AMBIGUOUS_DIFF = """--- a/app/sample.txt
+++ b/app/sample.txt
@@ -1 +1 @@
-old line
+new line
"""

NON_UTF8_DIFF = """--- a/sample.txt
+++ b/sample.txt
@@ -1,2 +1,2 @@
-old line
+nuova riga con caffè
 line2
"""


def _create_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "sample.txt").write_text("old line\nline2\n", encoding="utf-8")
    return project


def test_apply_patchset_dry_run(tmp_path: Path) -> None:
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
    assert session.backup_dir.exists()
    assert session.report_json_path is not None
    assert session.report_txt_path is not None
    assert session.report_json_path.exists()
    assert session.report_txt_path.exists()
    expected_dir = utils.default_session_report_dir(session.started_at)
    assert expected_dir.parent == utils.DEFAULT_REPORTS_DIR
    assert session.report_json_path.parent == expected_dir
    assert session.report_txt_path.parent == expected_dir
    assert not (session.backup_dir / "sample.txt").exists()
    assert len(session.results) == 1

    file_result = session.results[0]
    assert file_result.skipped_reason is None
    assert file_result.hunks_applied == file_result.hunks_total == 1
    report_txt = session.to_txt()
    assert "Hunk che verrebbero applicati: 1/1" in report_txt
    assert "Modalità dry-run" in report_txt


def test_apply_patchset_real_run_creates_backup(tmp_path: Path) -> None:
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

    report_dir = utils.default_session_report_dir(session.started_at)
    assert report_dir.parent == utils.DEFAULT_REPORTS_DIR
    json_report = report_dir / REPORT_JSON
    text_report = report_dir / REPORT_TXT
    assert json_report.exists()
    assert text_report.exists()
    assert session.report_json_path == json_report
    assert session.report_txt_path == text_report

    data = json.loads(json_report.read_text(encoding="utf-8"))
    assert data["files"][0]["hunks_applied"] == 1

    file_result = session.results[0]
    assert file_result.hunks_applied == file_result.hunks_total == 1


def test_apply_patchset_custom_report_paths(tmp_path: Path) -> None:
    project = _create_project(tmp_path)

    json_dest = tmp_path / "reports" / "custom" / "apply.json"
    txt_dest = tmp_path / "reports" / "apply.txt"

    session = cli.apply_patchset(
        PatchSet(SAMPLE_DIFF),
        project,
        dry_run=False,
        threshold=0.85,
        report_json=json_dest,
        report_txt=txt_dest,
    )

    assert session.report_json_path == json_dest
    assert session.report_txt_path == txt_dest
    assert json_dest.exists()
    assert txt_dest.exists()
    default_dir = utils.default_session_report_dir(session.started_at)
    assert not (default_dir / REPORT_JSON).exists()
    assert not (default_dir / REPORT_TXT).exists()

    data = json.loads(json_dest.read_text(encoding="utf-8"))
    assert data["files"][0]["hunks_applied"] == 1


def test_apply_patchset_no_report(tmp_path: Path) -> None:
    project = _create_project(tmp_path)

    session = cli.apply_patchset(
        PatchSet(SAMPLE_DIFF),
        project,
        dry_run=False,
        threshold=0.85,
        write_report_files=False,
    )

    assert session.report_json_path is None
    assert session.report_txt_path is None
    default_dir = utils.default_session_report_dir(session.started_at)
    assert not (default_dir / REPORT_JSON).exists()
    assert not (default_dir / REPORT_TXT).exists()


def test_apply_patchset_reports_ambiguous_candidates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    src_dir = project / "src/app"
    tests_dir = project / "tests/app"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    (src_dir / "sample.txt").write_text("old line\n", encoding="utf-8")
    (tests_dir / "sample.txt").write_text("old line\n", encoding="utf-8")

    session = cli.apply_patchset(
        PatchSet(AMBIGUOUS_DIFF),
        project,
        dry_run=True,
        threshold=0.85,
        interactive=False,
    )

    assert len(session.results) == 1
    file_result = session.results[0]
    assert file_result.skipped_reason is not None
    assert "src/app/sample.txt" in file_result.skipped_reason
    assert "tests/app/sample.txt" in file_result.skipped_reason

    report = session.to_txt()
    assert "src/app/sample.txt" in report
    assert "tests/app/sample.txt" in report


def test_apply_patchset_interactive_candidate_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    src_dir = project / "src/app"
    tests_dir = project / "tests/app"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    (src_dir / "sample.txt").write_text("old line\n", encoding="utf-8")
    (tests_dir / "sample.txt").write_text("old line\n", encoding="utf-8")

    monkeypatch.setattr("builtins.input", lambda _: "2")

    session = cli.apply_patchset(
        PatchSet(AMBIGUOUS_DIFF),
        project,
        dry_run=True,
        threshold=0.85,
    )

    assert len(session.results) == 1
    file_result = session.results[0]
    assert file_result.skipped_reason is None
    assert file_result.relative_to_root == "tests/app/sample.txt"
    assert file_result.hunks_applied == file_result.hunks_total == 1


def test_apply_patchset_skipped_reason_lists_candidates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    first_dir = project / "docs"
    second_dir = project / "legacy"
    first_dir.mkdir()
    second_dir.mkdir()

    for directory in (first_dir, second_dir):
        (directory / "sample.txt").write_text("old line\nline2\n", encoding="utf-8")

    session = cli.apply_patchset(
        PatchSet(SAMPLE_DIFF),
        project,
        dry_run=True,
        threshold=0.85,
        interactive=False,
    )

    assert len(session.results) == 1
    file_result = session.results[0]
    assert file_result.skipped_reason is not None
    assert "docs/sample.txt" in file_result.skipped_reason
    assert "legacy/sample.txt" in file_result.skipped_reason


def test_load_patch_applies_non_utf8_diff(tmp_path: Path) -> None:
    project = _create_project(tmp_path)
    patch_path = tmp_path / "non-utf8.diff"
    patch_path.write_bytes(NON_UTF8_DIFF.encode("utf-16"))

    patch = cli.load_patch(str(patch_path))
    assert "nuova riga con caffè" in str(patch)

    session = cli.apply_patchset(
        patch,
        project,
        dry_run=False,
        threshold=0.85,
    )

    target = project / "sample.txt"
    assert target.read_text(encoding="utf-8") == "nuova riga con caffè\nline2\n"

    file_result = session.results[0]
    assert file_result.skipped_reason is None
    assert file_result.hunks_applied == file_result.hunks_total == 1


def test_load_patch_respects_explicit_encoding(tmp_path: Path) -> None:
    patch_path = tmp_path / "explicit.diff"
    patch_path.write_text(NON_UTF8_DIFF, encoding="utf-16")

    patch = cli.load_patch(str(patch_path), encoding="utf-16")

    assert "nuova riga con caffè" in str(patch)


def test_load_patch_logs_warning_on_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    patch_path = tmp_path / "fallback.diff"
    patch_path.write_text(SAMPLE_DIFF, encoding="utf-8")

    real_decode = utils.decode_bytes

    def fake_decode(data: bytes) -> tuple[str, str, bool]:
        text, encoding, _ = real_decode(data)
        return text, encoding, True

    monkeypatch.setattr(executor, "decode_bytes", fake_decode)

    with caplog.at_level(logging.WARNING):
        patch = cli.load_patch(str(patch_path))

    assert isinstance(patch, PatchSet)
    assert any("fallback" in record.message.lower() for record in caplog.records)


def test_load_patch_missing_file_raises_clierror(tmp_path: Path) -> None:
    missing = tmp_path / "not-there.diff"

    with pytest.raises(cli.CLIError) as excinfo:
        cli.load_patch(str(missing))

    assert str(excinfo.value) == f"Diff file not found: {missing}"


def test_load_patch_invalid_diff_raises_clierror(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.diff"
    invalid.write_text(
        """--- a/file
+++ b/file
@@ -1 +1 @@
@@ -1 +1 @@
""",
        encoding="utf-8",
    )

    with pytest.raises(cli.CLIError) as excinfo:
        cli.load_patch(str(invalid))

    message = str(excinfo.value)
    assert "Invalid diff" in message
    assert "@@ -1,0 +1,0 @@" in message


def test_run_cli_requires_root_argument(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    patch_path = tmp_path / "input.diff"
    patch_path.write_text(SAMPLE_DIFF, encoding="utf-8")

    def fake_exit(
        self: argparse.ArgumentParser, status: int = 0, message: str | None = None
    ) -> None:
        raise cli.CLIError(message.strip() if message else "parser exited")

    monkeypatch.setattr(argparse.ArgumentParser, "exit", fake_exit, raising=False)

    with pytest.raises(cli.CLIError) as excinfo:
        cli.run_cli([str(patch_path)])

    message = str(excinfo.value)
    assert "--root" in message
    assert "error" in message.lower()


def test_run_cli_rejects_report_conflicts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = _create_project(tmp_path)
    patch_path = tmp_path / "report-options.diff"
    patch_path.write_text(SAMPLE_DIFF, encoding="utf-8")

    def fake_exit(
        self: argparse.ArgumentParser, status: int = 0, message: str | None = None
    ) -> None:
        raise cli.CLIError(message.strip() if message else "parser exited")

    monkeypatch.setattr(argparse.ArgumentParser, "exit", fake_exit, raising=False)

    with pytest.raises(cli.CLIError) as excinfo:
        cli.run_cli(
            [
                "--root",
                str(project),
                "--no-report",
                "--report-json",
                str(tmp_path / "custom.json"),
                str(patch_path),
            ]
        )

    message = str(excinfo.value)
    assert "--no-report" in message or "no-report" in message


def test_apply_patchset_logs_warning_on_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _create_project(tmp_path)

    real_decode = utils.decode_bytes

    def fake_decode(data: bytes) -> tuple[str, str, bool]:
        text, encoding, _ = real_decode(data)
        return text, encoding, True

    monkeypatch.setattr(executor, "decode_bytes", fake_decode)

    with caplog.at_level(logging.WARNING):
        session = cli.apply_patchset(
            PatchSet(SAMPLE_DIFF),
            project,
            dry_run=True,
            threshold=0.85,
        )

    assert session.results
    assert any("fallback" in record.message.lower() for record in caplog.records)


def test_run_cli_configures_requested_log_level(tmp_path: Path) -> None:
    project = _create_project(tmp_path)
    patch_path = tmp_path / "run-cli.diff"
    patch_path.write_text(SAMPLE_DIFF, encoding="utf-8")

    root_logger = logging.getLogger()
    previous_handlers = root_logger.handlers[:]
    previous_level = root_logger.level

    try:
        exit_code = cli.run_cli(
            [
                "--root",
                str(project),
                "--dry-run",
                "--log-level",
                "debug",
                str(patch_path),
            ]
        )
        assert exit_code == 0

        configured_logger = logging.getLogger()
        assert configured_logger.level == logging.DEBUG
        assert any(
            isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout
            for handler in configured_logger.handlers
        )
    finally:
        configured_logger = logging.getLogger()
        for handler in configured_logger.handlers[:]:
            configured_logger.removeHandler(handler)
        for handler in previous_handlers:
            configured_logger.addHandler(handler)
        configured_logger.setLevel(previous_level)


def _create_dummy_session(tmp_path: Path):
    class DummySession:
        def __init__(self) -> None:
            self.dry_run = True
            self.report_json_path = None
            self.report_txt_path = None
            self.results = []
            self.backup_dir = tmp_path / "backups"
            self.backup_dir.mkdir(exist_ok=True)

        def to_txt(self) -> str:
            return "Summary"

    return DummySession()


def test_run_cli_passes_explicit_encoding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = _create_project(tmp_path)
    patch_path = tmp_path / "input.diff"
    patch_path.write_text(SAMPLE_DIFF, encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_load_patch(source: str, *, encoding: str | None = None) -> PatchSet:
        captured["encoding"] = encoding
        captured["source"] = source
        return PatchSet(SAMPLE_DIFF)

    def fake_apply_patchset(*args: object, **kwargs: object) -> object:
        return _create_dummy_session(tmp_path)

    monkeypatch.setattr(cli, "load_patch", fake_load_patch)
    monkeypatch.setattr(cli, "apply_patchset", fake_apply_patchset)
    monkeypatch.setattr(cli, "session_completed", lambda session: True)

    exit_code = cli.run_cli(
        [
            "--root",
            str(project),
            "--dry-run",
            "--encoding",
            "utf-16",
            str(patch_path),
        ]
    )

    assert exit_code == 0
    assert captured["encoding"] == "utf-16"
    assert captured["source"] == str(patch_path)


def test_run_cli_defaults_to_auto_encoding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = _create_project(tmp_path)
    patch_path = tmp_path / "input.diff"
    patch_path.write_text(SAMPLE_DIFF, encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_load_patch(source: str, *, encoding: str | None = None) -> PatchSet:
        captured["encoding"] = encoding
        return PatchSet(SAMPLE_DIFF)

    def fake_apply_patchset(*args: object, **kwargs: object) -> object:
        return _create_dummy_session(tmp_path)

    monkeypatch.setattr(cli, "load_patch", fake_load_patch)
    monkeypatch.setattr(cli, "apply_patchset", fake_apply_patchset)
    monkeypatch.setattr(cli, "session_completed", lambda session: True)

    exit_code = cli.run_cli(
        ["--root", str(project), "--dry-run", str(patch_path)]
    )

    assert exit_code == 0
    assert captured["encoding"] is None


@pytest.mark.parametrize("raw, expected", [("0.5", 0.5), ("1.0", 1.0)])
def test_threshold_value_accepts_valid_inputs(raw: str, expected: float) -> None:
    assert parser.threshold_value(raw) == expected


@pytest.mark.parametrize(
    "raw, expected_message",
    [
        ("0", "Threshold must be between 0 (exclusive) and 1 (inclusive)."),
        ("1.1", "Threshold must be between 0 (exclusive) and 1 (inclusive)."),
        ("-0.2", "Threshold must be between 0 (exclusive) and 1 (inclusive)."),
        ("abc", "Threshold must be a decimal number."),
    ],
)
def test_threshold_value_rejects_invalid_inputs(
    raw: str, expected_message: str
) -> None:
    with pytest.raises(argparse.ArgumentTypeError) as excinfo:
        parser.threshold_value(raw)

    assert str(excinfo.value) == expected_message
