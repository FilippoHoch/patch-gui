"""Core logic for loading patches and applying them to a project."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from .filetypes import inspect_file_type
from .localization import gettext as _
from .patcher import (
    ApplySession,
    FileResult,
    HunkDecision,
    HunkView,
    DEFAULT_EXCLUDE_DIRS,
    apply_hunks,
    backup_file,
    find_file_candidates,
    prepare_backup_dir,
)
from .reporting import write_session_reports
from .utils import (
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
        path = Path(source).expanduser()
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
    exclude_dirs: Sequence[str] | None = None,
) -> ApplySession:
    """Apply ``patch`` to ``project_root`` and return the :class:`ApplySession`."""

    root = project_root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise CLIError(_("Invalid project root: {path}").format(path=project_root))

    started_at = time.time()
    backup_dir = prepare_backup_dir(
        root,
        dry_run=dry_run,
        backup_base=backup_base,
        started_at=started_at,
    )
    resolved_excludes = (
        tuple(exclude_dirs) if exclude_dirs is not None else DEFAULT_EXCLUDE_DIRS
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

    write_session_reports(
        session,
        report_json=report_json,
        report_txt=report_txt,
        enable_reports=write_report_files,
    )

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
    source_file = getattr(pf, "source_file", None)
    target_file = getattr(pf, "target_file", None)
    if isinstance(source_file, str) and source_file.strip() == "/dev/null":
        is_added_file = True
    if isinstance(target_file, str) and target_file.strip() == "/dev/null":
        is_added_file = True

    candidates = find_file_candidates(
        project_root,
        rel_path,
        exclude_dirs=session.exclude_dirs,
    )

    path: Optional[Path] = None
    is_new_file = False

    if not candidates:
        if is_added_file and rel_path:
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
            fr.file_path = path
            fr.relative_to_root = display_relative_path(path, project_root)
            is_new_file = True
        else:
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

    lines: List[str]
    file_encoding = "utf-8"
    orig_eol = "\n"

    if not is_new_file:
        try:
            raw = path.read_bytes()
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
        backup_file(project_root, path, session.backup_dir)

    lines, decisions, applied = apply_hunks(
        lines,
        pf,
        threshold=session.threshold,
        manual_resolver=_cli_manual_resolver,
    )

    fr.hunks_applied = applied
    fr.decisions.extend(decisions)

    if not session.dry_run and applied:
        if is_new_file:
            path.parent.mkdir(parents=True, exist_ok=True)
        new_text = "".join(lines)
        if not is_new_file:
            new_text = new_text.replace("\n", orig_eol)
        write_text_preserving_encoding(path, new_text, file_encoding)

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


def _cli_manual_resolver(
    hv: HunkView,
    lines: List[str],
    candidates: List[Tuple[int, float]],
    decision: HunkDecision,
    reason: str,
) -> Optional[int]:
    del hv, lines  # unused in CLI resolver
    decision.candidates = candidates
    decision.strategy = "ambiguous"
    if reason == "fuzzy":
        decision.message = _(
            "Multiple candidate positions scored above the threshold. The CLI cannot "
            "choose automatically."
        )
    else:
        decision.message = _(
            "Only the context matches. Use the GUI or adjust the threshold to apply this "
            "hunk."
        )
    return None
