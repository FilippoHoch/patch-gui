"""Core logic for loading patches and applying them to a project."""

from __future__ import annotations

import logging
import os
import shutil
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from .config import AppConfig, load_config
from .filetypes import inspect_file_type
from .localization import gettext as _
from .patcher import (
    ApplySession,
    FileResult,
    HunkDecision,
    HunkView,
    apply_hunks,
    backup_file,
    find_file_candidates,
    prepare_backup_dir,
    prune_backup_sessions,
)
from .reporting import write_session_reports
from .utils import (
    REPORT_RESULTS_SUBDIR,
    REPORTS_SUBDIR,
    decode_bytes,
    display_relative_path,
    normalize_newlines,
    preprocess_patch_text,
    write_text_preserving_encoding,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CLIError",
    "ApplySession",
    "apply_patchset",
    "load_patch",
    "session_completed",
    "sys",
]


class CLIError(Exception):
    """Raised for recoverable CLI usage errors."""


def load_patch(source: str, encoding: str | None = None) -> PatchSet:
    """Load and parse a diff/patch file from ``source`` (path or ``'-'`` for stdin)."""

    def _log_decoding_details(
        source_label: str, detected_encoding: str, used_fallback: bool
    ) -> None:
        if used_fallback:
            logger.warning(
                _(
                    "Decoded diff %s using fallback UTF-8 (original encoding %s); "
                    "the content may contain substituted characters."
                ),
                source_label,
                detected_encoding,
            )

    if source == "-":
        stream = getattr(sys.stdin, "buffer", None)
        if encoding:
            data = stream.read() if stream is not None else sys.stdin.read()
            try:
                if isinstance(data, bytes):
                    text = data.decode(encoding)
                else:
                    text = str(data)
            except (LookupError, UnicodeDecodeError) as exc:
                raise CLIError(
                    _(
                        "Cannot decode diff from STDIN using encoding {encoding}: {error}"
                    ).format(encoding=encoding, error=exc)
                ) from exc
        else:
            if stream is not None:
                raw = stream.read()
                text, detected_encoding, used_fallback = decode_bytes(raw)
                _log_decoding_details("STDIN", detected_encoding, used_fallback)
            else:
                text = sys.stdin.read()
    else:
        expanded_source = os.path.expanduser(source)
        path = Path(expanded_source)
        if not path.exists():
            raise CLIError(_("Diff file not found: {path}").format(path=path))
        if encoding:
            try:
                text = path.read_text(encoding=encoding)
            except (LookupError, UnicodeDecodeError) as exc:
                raise CLIError(
                    _("Cannot decode diff using encoding {encoding}: {error}").format(
                        encoding=encoding, error=exc
                    )
                ) from exc
            except (
                Exception
            ) as exc:  # pragma: no cover - extremely rare I/O error types
                raise CLIError(
                    _("Cannot read {path}: {error}").format(path=path, error=exc)
                ) from exc
        else:
            try:
                raw = path.read_bytes()
            except (
                Exception
            ) as exc:  # pragma: no cover - extremely rare I/O error types
                raise CLIError(
                    _("Cannot read {path}: {error}").format(path=path, error=exc)
                ) from exc
            text, detected_encoding, used_fallback = decode_bytes(raw)
            _log_decoding_details(str(path), detected_encoding, used_fallback)

    processed = preprocess_patch_text(text)
    try:
        patch = PatchSet(processed)
    except UnidiffParseError as exc:
        raise CLIError(_("Invalid diff: {error}").format(error=exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive guard for unexpected errors
        raise CLIError(
            _("Unexpected error while parsing the diff: {error}").format(error=exc)
        ) from exc
    return patch


def apply_patchset(
    patch: PatchSet,
    project_root: Path,
    *,
    dry_run: bool,
    threshold: float,
    backup_base: Optional[Path] = None,
    interactive: bool = True,
    report_json: Path | str | None = None,
    report_txt: Path | str | None = None,
    write_report_files: bool = True,
    write_report_json: bool | None = None,
    write_report_txt: bool | None = None,
    exclude_dirs: Sequence[str] | None = None,
    config: AppConfig | None = None,
) -> ApplySession:
    """Apply ``patch`` to ``project_root`` and return the :class:`ApplySession`.

    ``threshold`` must be within the range ``(0, 1]`` to match CLI validation.
    """

    root = project_root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise CLIError(_("Invalid project root: {path}").format(path=project_root))

    if not 0 < threshold <= 1:
        raise CLIError(
            _("Threshold must be between 0 (exclusive) and 1 (inclusive).")
        )

    resolved_config = config or load_config()
    started_at = time.time()
    backup_base_arg = backup_base or resolved_config.backup_base
    try:
        backup_dir = prepare_backup_dir(
            root,
            dry_run=dry_run,
            backup_base=backup_base_arg,
            started_at=started_at,
        )
    except (OSError, PermissionError) as exc:
        failure_path = (
            getattr(exc, "filename", None)
            or getattr(exc, "filename2", None)
            or backup_base_arg
            or root
        )
        message = _(
            "Failed to prepare backup directory at {path}: {error}"
        ).format(path=failure_path, error=exc)
        raise CLIError(message) from exc

    retention_days = getattr(resolved_config, "backup_retention_days", 0)
    if retention_days > 0:
        prune_backup_sessions(
            backup_base_arg,
            retention_days=retention_days,
            reference_timestamp=started_at,
        )
        reports_base = backup_base_arg / REPORTS_SUBDIR / REPORT_RESULTS_SUBDIR
        prune_backup_sessions(
            reports_base,
            retention_days=retention_days,
            reference_timestamp=started_at,
        )
    resolved_excludes = (
        tuple(exclude_dirs)
        if exclude_dirs is not None
        else resolved_config.exclude_dirs
    )

    session = ApplySession(
        project_root=root,
        backup_dir=backup_dir,
        dry_run=dry_run,
        threshold=threshold,
        exclude_dirs=resolved_excludes,
        started_at=started_at,
    )

    for pf in patch:
        rel = _relative_path_from_patch(pf)
        fr = _apply_file_patch(root, pf, rel, session, interactive=interactive)
        session.results.append(fr)

    try:
        write_session_reports(
            session,
            report_json=report_json,
            report_txt=report_txt,
            enable_reports=write_report_files,
            write_json=write_report_json,
            write_txt=write_report_txt,
        )
    except (OSError, PermissionError) as exc:
        failure_path = getattr(exc, "filename", None) or getattr(exc, "filename2", None)
        if failure_path is None:
            failure_path = session.backup_dir
        message = _("Failed to write session reports to {path}: {error}").format(
            path=failure_path, error=exc
        )
        raise CLIError(message) from exc

    return session


def session_completed(session: ApplySession) -> bool:
    for fr in session.results:
        if fr.skipped_reason:
            return False
        if fr.hunks_total and fr.hunks_applied != fr.hunks_total:
            return False
    return True


def _relative_path_from_patch(pf: Any) -> str:
    rel = pf.path or pf.target_file or pf.source_file or ""
    return rel.strip()


def _normalize_patch_path(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    if cleaned.startswith("a/") or cleaned.startswith("b/"):
        cleaned = cleaned[2:]
    if cleaned == "/dev/null":
        return ""
    return cleaned


def _resolve_within_project(project_root: Path, relative: str) -> Optional[Path]:
    if not relative:
        return None
    candidate = project_root / relative
    try:
        resolved = candidate.resolve()
    except FileNotFoundError:
        resolved = candidate.resolve(strict=False)
    root = project_root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _iter_unique(values: Iterable[str]) -> Iterable[str]:
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        yield value


def _apply_file_patch(
    project_root: Path,
    pf: Any,
    rel_path: str,
    session: ApplySession,
    *,
    interactive: bool,
) -> FileResult:
    fr = FileResult(file_path=Path(), relative_to_root=rel_path)
    fr.hunks_total = len(pf)

    file_type_info = inspect_file_type(pf)
    fr.file_type = file_type_info.name

    if file_type_info.name == "binary":
        fr.skipped_reason = _("Binary patches are not supported in CLI mode")
        return fr

    is_added_file = bool(getattr(pf, "is_added_file", False))
    is_removed_file = bool(getattr(pf, "is_removed_file", False))
    is_rename = bool(getattr(pf, "is_rename", False))
    is_copy = bool(getattr(pf, "is_copy", False))
    patch_info = getattr(pf, "patch_info", None)
    if not is_copy and isinstance(patch_info, list):
        lowered = [entry.lower() for entry in patch_info if isinstance(entry, str)]
        if any(line.startswith("copy from") for line in lowered):
            is_copy = True
    source_file = getattr(pf, "source_file", None)
    target_file = getattr(pf, "target_file", None)
    if isinstance(source_file, str) and source_file.strip() == "/dev/null":
        is_added_file = True
    if isinstance(target_file, str) and target_file.strip() == "/dev/null":
        is_removed_file = True

    normalized_rel_path = _normalize_patch_path(rel_path)
    rename_source = _normalize_patch_path(source_file)
    rename_target = _normalize_patch_path(target_file)
    rename_flag = bool(getattr(pf, "is_rename", False))
    is_rename = (
        not is_copy
        and not is_added_file
        and not is_removed_file
        and rename_source
        and rename_target
        and (rename_source != rename_target or rename_flag)
    )

    candidates: list[Path] = []
    for candidate_path in _iter_unique(
        (
            [rename_source, normalized_rel_path]
            if is_rename
            else [normalized_rel_path]
        )
    ):
        candidates = find_file_candidates(
            project_root,
            candidate_path,
            exclude_dirs=session.exclude_dirs,
        )
        if candidates:
            break

    path: Optional[Path] = None
    is_new_file = False
    pending_operation: Optional[str] = None
    operation_source: Optional[Path] = None

    if not candidates:
        if (is_rename or is_copy) and isinstance(source_file, str):
            source_rel = source_file.strip()
            if source_rel and source_rel != "/dev/null":
                source_candidates = find_file_candidates(
                    project_root,
                    source_rel,
                    exclude_dirs=session.exclude_dirs,
                )
                if not source_candidates:
                    fr.skipped_reason = _(
                        "Source file for rename/copy not found in the project root"
                    )
                    return fr
                if len(source_candidates) > 1:
                    if not interactive:
                        fr.skipped_reason = _ambiguous_paths_message(
                            project_root, source_candidates
                        )
                        return fr
                    selected_source = _prompt_candidate_selection(
                        project_root, source_candidates
                    )
                    if selected_source is None:
                        fr.skipped_reason = _ambiguous_paths_message(
                            project_root, source_candidates
                        )
                        return fr
                    source_path = selected_source
                else:
                    source_path = source_candidates[0]

                if rel_path:
                    candidate = project_root / rel_path
                    resolved_candidate = candidate.resolve()
                    try:
                        resolved_candidate.relative_to(project_root)
                    except ValueError:
                        fr.skipped_reason = _(
                            "Patch targets a path outside the project root"
                        )
                        return fr
                    path = resolved_candidate
                    pending_operation = "copy" if is_copy else "rename"
                    operation_source = source_path
                else:
                    fr.skipped_reason = _("File not found in the project root")
                    return fr
        if path is None and is_added_file and rel_path:
            candidate = project_root / rel_path
            resolved_candidate = candidate.resolve()
            try:
                resolved_candidate.relative_to(project_root)
            except ValueError:
                fr.skipped_reason = _("Patch targets a path outside the project root")
                return fr

            path = resolved_candidate
            fr.file_path = path
            fr.relative_to_root = display_relative_path(path, project_root)
            is_new_file = True
        if path is None:
            fr.skipped_reason = _("File not found in the project root")
            return fr
    elif len(candidates) > 1:
        if not interactive:
            fr.skipped_reason = _ambiguous_paths_message(project_root, candidates)
            return fr
        selected = _prompt_candidate_selection(project_root, candidates)
        if selected is None:
            fr.skipped_reason = _ambiguous_paths_message(project_root, candidates)
            return fr
        path = selected
    else:
        path = candidates[0]

    if path is None:
        fr.skipped_reason = _("File not found in the project root")
        return fr

    fr.file_path = path
    fr.relative_to_root = display_relative_path(path, project_root)

    rename_target_path: Optional[Path] = None
    rename_decision: Optional[HunkDecision] = None
    if is_rename and rename_target:
        rename_target_path = _resolve_within_project(project_root, rename_target)
        if rename_target_path is None:
            fr.skipped_reason = _("Patch targets a path outside the project root")
            return fr
        try:
            current_resolved = path.resolve()
        except FileNotFoundError:
            current_resolved = path
        if rename_target_path == current_resolved:
            rename_target_path = None
        else:
            rename_decision = HunkDecision(
                hunk_header="rename",
                strategy="rename",
                message=_("Renamed file from {source} to {target}").format(
                    source=display_relative_path(path, project_root),
                    target=display_relative_path(rename_target_path, project_root),
                ),
            )

    if rename_decision and fr.hunks_total == 0:
        if session.dry_run:
            fr.file_path = rename_target_path or fr.file_path
            if rename_target_path is not None:
                fr.relative_to_root = display_relative_path(
                    rename_target_path, project_root
                )
            fr.decisions.append(rename_decision)
            return fr

        try:
            backup_file(project_root, path, session.backup_dir)
        except Exception as exc:  # pragma: no cover - defensive
            fr.skipped_reason = _(
                "Failed to back up file before rename: {error}"
            ).format(error=exc)
            return fr

        try:
            if rename_target_path is not None:
                rename_target_path.parent.mkdir(parents=True, exist_ok=True)
                path.rename(rename_target_path)
                fr.file_path = rename_target_path
                fr.relative_to_root = display_relative_path(
                    rename_target_path, project_root
                )
        except OSError as exc:
            message = _("Failed to rename file: {error}").format(error=exc)
            fr.skipped_reason = message
            rename_decision.strategy = "failed"
            rename_decision.message = message
            fr.decisions.append(rename_decision)
            return fr

        fr.decisions.append(rename_decision)
        return fr

    lines: List[str]
    file_encoding = "utf-8"
    orig_eol = "\n"

    content_path = path
    if pending_operation and operation_source is not None:
        if session.dry_run:
            content_path = operation_source
        else:
            if operation_source.resolve() != path:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if pending_operation == "rename":
                        operation_source.replace(path)
                    else:
                        shutil.copy2(operation_source, path)
                except OSError as exc:
                    fr.skipped_reason = _(
                        "Failed to prepare file for rename/copy patch: {error}"
                    ).format(error=exc)
                    return fr
            content_path = path

    if not is_new_file:
        try:
            raw = content_path.read_bytes()
        except Exception as exc:
            fr.skipped_reason = _("Cannot read the file: {error}").format(error=exc)
            return fr

        content, file_encoding, used_fallback = decode_bytes(raw)
        if used_fallback:
            logger.warning(
                _(
                    "Decoded file %s using fallback UTF-8 (original encoding %s); "
                    "some characters may be substituted."
                ),
                path,
                file_encoding,
            )
        orig_eol = "\r\n" if "\r\n" in content else "\n"
        lines = normalize_newlines(content).splitlines(keepends=True)
    else:
        file_encoding = getattr(pf, "encoding", None) or "utf-8"
        lines = []

    if not session.dry_run and not is_new_file:
        try:
            backup_file(project_root, path, session.backup_dir)
        except OSError as exc:
            relative_path = display_relative_path(path, project_root)
            message = _(
                "Failed to create backup for {path}: {error}"
            ).format(path=relative_path, error=exc)
            logger.error(message)
            fr.skipped_reason = message
            fr.decisions.append(
                HunkDecision(
                    hunk_header="backup",
                    strategy="failed",
                    message=message,
                )
            )
            return fr

    lines, decisions, applied = apply_hunks(
        lines,
        pf,
        threshold=session.threshold,
        manual_resolver=_cli_manual_resolver,
    )

    fr.hunks_applied = applied
    if rename_decision is not None:
        fr.decisions.append(rename_decision)
    fr.decisions.extend(decisions)

    if rename_target_path is not None:
        if session.dry_run:
            fr.file_path = rename_target_path
            fr.relative_to_root = display_relative_path(rename_target_path, project_root)
        elif applied == fr.hunks_total:
            try:
                rename_target_path.parent.mkdir(parents=True, exist_ok=True)
                path.rename(rename_target_path)
                path = rename_target_path
                fr.file_path = rename_target_path
                fr.relative_to_root = display_relative_path(
                    rename_target_path, project_root
                )
            except OSError as exc:
                message = _("Failed to rename file: {error}").format(error=exc)
                fr.skipped_reason = message
                rename_decision = rename_decision or HunkDecision(
                    hunk_header="rename",
                    strategy="failed",
                )
                rename_decision.strategy = "failed"
                rename_decision.message = message
                if rename_decision not in fr.decisions:
                    fr.decisions.append(rename_decision)
                return fr

    if not session.dry_run and applied:
        should_remove = is_removed_file and fr.hunks_total and applied == fr.hunks_total
        if should_remove:
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                message = _(
                    "Failed to delete file after applying patch: {error}"
                ).format(error=exc)
                fr.skipped_reason = message
                hunk_header = pf[0].header if len(pf) else rel_path
                fr.decisions.append(
                    HunkDecision(
                        hunk_header=hunk_header,
                        strategy="failed",
                        message=message,
                    )
                )
        else:
            if is_new_file:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    relative_dir = display_relative_path(path.parent, project_root)
                    message = _(
                        "Failed to create directory for {path}: {error}"
                    ).format(path=relative_dir, error=exc)
                    logger.error(message)
                    raise CLIError(message) from exc
            new_text = "".join(lines)
            if not is_new_file:
                new_text = new_text.replace("\n", orig_eol)
            try:
                write_text_preserving_encoding(path, new_text, file_encoding)
            except OSError as exc:
                relative_path = display_relative_path(path, project_root)
                message = _(
                    "Failed to write updated content to {path}: {error}"
                ).format(path=relative_path, error=exc)
                logger.error(message)
                raise CLIError(message) from exc

    return fr


def _prompt_candidate_selection(
    project_root: Path, candidates: Sequence[Path]
) -> Optional[Path]:
    display_paths: List[str] = []
    for path in candidates:
        display_paths.append(display_relative_path(path, project_root))

    print(_("Multiple files match the patch path:"))
    for idx, value in enumerate(display_paths, start=1):
        print(f"  {idx}) {value}")
    prompt = _(
        "Select the number of the file to use (1-{count}). Press Enter or type 's' to skip: "
    ).format(count=len(candidates))

    while True:
        try:
            choice = input(prompt)
        except EOFError:
            return None
        except KeyboardInterrupt:
            raise

        choice = choice.strip()
        if not choice or choice.lower() in {"s", "skip", "n", "no", "q", "quit"}:
            return None

        try:
            index = int(choice)
        except ValueError:
            print(_("Invalid input. Enter a number or leave empty to cancel."))
            continue

        if 1 <= index <= len(candidates):
            return candidates[index - 1]

        print(_("Number out of range. Try again."))


def _ambiguous_paths_message(project_root: Path, candidates: Sequence[Path]) -> str:
    max_display = 5
    shown: List[str] = []
    for path in candidates[:max_display]:
        shown.append(display_relative_path(path, project_root))
    remaining = len(candidates) - max_display
    if remaining > 0:
        shown.append(_("… (+{count} more)").format(count=remaining))
    joined = ", ".join(shown)
    return _(
        "Multiple files found for the provided path; resolve the ambiguity manually. "
        "Candidates: {candidates}"
    ).format(candidates=joined)


def _ai_rank_candidates(
    lines: List[str],
    hv: HunkView,
    candidates: List[Tuple[int, float]],
) -> Optional[Tuple[int, int, float, Optional[Tuple[int, int]]]]:
    if not candidates:
        return None

    reference_lines = hv.before_lines or hv.after_lines
    block_len = len(reference_lines)
    if block_len == 0 and hv.after_lines:
        block_len = len(hv.after_lines)
    if block_len <= 0:
        block_len = 1

    reference_text = "".join(reference_lines)
    if not reference_text:
        reference_text = "".join(hv.after_lines)

    best: Optional[Tuple[int, int, float, Optional[Tuple[int, int]]]] = None
    for display_index, (pos, similarity) in enumerate(candidates, start=1):
        if similarity is not None:
            score = float(similarity)
        elif reference_text:
            snippet = "".join(lines[pos : pos + block_len])
            if not snippet and 0 <= pos < len(lines):
                snippet = lines[pos]
            score = SequenceMatcher(None, reference_text, snippet).ratio()
        else:
            # Cannot compute a heuristic score without reference text
            continue

        start_line = pos + 1
        end_line = start_line + block_len - 1
        if start_line > len(lines):
            line_range: Optional[Tuple[int, int]] = None
        else:
            end_line = min(end_line, len(lines))
            line_range = (start_line, end_line)

        if best is None or score > best[2]:
            best = (display_index, pos, score, line_range)

    return best


def _cli_manual_resolver(
    hv: HunkView,
    lines: List[str],
    candidates: List[Tuple[int, float]],
    decision: HunkDecision,
    reason: str,
) -> Optional[int]:
    decision.candidates = list(candidates)
    decision.strategy = "manual"

    header_message = _("Reviewing hunk: {header}").format(header=hv.header)
    if reason == "fuzzy":
        context_message = _(
            "Multiple candidate positions matched this hunk above the similarity "
            "threshold."
        )
    else:
        context_message = _(
            "Only the surrounding context matched this hunk; a manual choice is "
            "required."
        )

    print("")
    print(header_message)
    print(context_message)

    if hv.before_lines:
        print(_("  Original hunk lines:"))
        for line in hv.before_lines:
            print(f"    - {line.rstrip()}" if line.endswith("\n") else f"    - {line}")
    if hv.after_lines:
        print(_("  Proposed hunk lines:"))
        for line in hv.after_lines:
            print(f"    + {line.rstrip()}" if line.endswith("\n") else f"    + {line}")

    window_len = len(hv.before_lines)
    highlight_width = max(window_len, 1)
    context_padding = 2

    ai_hint = _ai_rank_candidates(lines, hv, candidates)
    if ai_hint is not None:
        hint_index, hint_position, hint_score, hint_range = ai_hint
        if hint_range is None:
            range_text = _("line {line}").format(line=hint_position + 1)
        else:
            start_line, end_line = hint_range
            if start_line == end_line:
                range_text = _("line {line}").format(line=start_line)
            else:
                range_text = _("lines {start}-{end}").format(
                    start=start_line,
                    end=end_line,
                )
        print(
            _(
                "AI suggestion: candidate {index} ({range_text}) looks like the best "
                "match (confidence {confidence:.3f})."
            ).format(
                index=hint_index,
                range_text=range_text,
                confidence=hint_score,
            )
        )

    print("")
    print(_("Available candidate positions:"))
    for idx, (pos, score) in enumerate(candidates, start=1):
        similarity_str = f"{score:.3f}" if score is not None else _("n/a")
        line_number = pos + 1
        print(
            _("  {index}) Position {position} (line {line}, similarity {similarity})").format(
                index=idx,
                position=pos,
                line=line_number,
                similarity=similarity_str,
            )
        )

        snippet_start = max(0, pos - context_padding)
        snippet_end = min(len(lines), pos + highlight_width + context_padding)
        highlight_start = pos
        highlight_end = min(len(lines), pos + highlight_width)

        if snippet_start >= snippet_end:
            print(_("    (No surrounding lines available in the file.)"))
        else:
            print(_("    File context:"))
            for current_index in range(snippet_start, snippet_end):
                indicator = (
                    ">"
                    if highlight_start <= current_index < highlight_end
                    else " "
                )
                raw_line = lines[current_index]
                display_line = raw_line.rstrip("\n")
                print(f"    {indicator}{current_index + 1:>6}: {display_line}")
        print("")

    prompt = _(
        "Choose a candidate number (1-{count}) or press Enter to skip: "
    ).format(count=len(candidates))

    while True:
        try:
            raw = input(prompt)
        except EOFError:
            decision.strategy = "skipped"
            decision.selected_pos = None
            decision.similarity = None
            decision.message = _("Manual resolution skipped (EOF received).")
            return None
        except KeyboardInterrupt:
            raise

        choice = raw.strip()
        if not choice or choice.lower() in {"s", "skip", "n", "no", "q", "quit"}:
            decision.strategy = "skipped"
            decision.selected_pos = None
            decision.similarity = None
            decision.message = _("Manual resolution skipped by the user.")
            return None

        try:
            index = int(choice)
        except ValueError:
            print(
                _(
                    "Invalid input. Enter a number between 1 and {count}, or leave "
                    "blank to cancel."
                ).format(count=len(candidates))
            )
            continue

        if 1 <= index <= len(candidates):
            pos, score = candidates[index - 1]
            decision.strategy = "manual"
            decision.selected_pos = pos
            decision.similarity = score
            decision.message = _(
                "Applied manually via CLI using candidate {choice}."
            ).format(choice=index)
            return pos

        print(_("Number out of range. Try again."))
