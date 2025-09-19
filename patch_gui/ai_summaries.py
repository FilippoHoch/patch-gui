"""Helpers for retrieving AI-generated summaries of patch sessions."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from .patcher import ApplySession

logger = logging.getLogger(__name__)

__all__ = [
    "AISummary",
    "AISummaryError",
    "AISummaryHooks",
    "compute_diff_digest",
    "generate_session_summary",
]


def compute_diff_digest(diff: object) -> str:
    """Return a stable digest for ``diff`` suitable for cache keys."""

    if isinstance(diff, str):
        text = diff
    else:
        text = str(diff)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AISummaryError(RuntimeError):
    """Raised when the AI summary service cannot produce a result."""


@dataclass(slots=True)
class AISummary:
    """Container for the overall and per-file summaries returned by the AI."""

    overall: Optional[str] = None
    per_file: Dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.overall or self.per_file)


_DEFAULT_TIMEOUT = 15.0
_MAX_DECISIONS_PER_FILE = 50
_MAX_CANDIDATES_PER_DECISION = 5


SummaryStartCallback = Callable[[dict[str, object]], None]
SummaryChunkCallback = Callable[[dict[str, object]], None]
SummaryCompleteCallback = Callable[["AISummary", bool], None]
SummaryCachedCallback = Callable[["AISummary"], None]


@dataclass(slots=True)
class AISummaryHooks:
    """Optional callbacks invoked while fetching AI summaries."""

    on_start: Optional[SummaryStartCallback] = None
    on_chunk: Optional[SummaryChunkCallback] = None
    on_complete: Optional[SummaryCompleteCallback] = None
    on_cached: Optional[SummaryCachedCallback] = None


_SUMMARY_CACHE: dict[str, tuple[AISummary, float]] = {}
_SUMMARY_CACHE_LOCK = threading.Lock()


def _build_payload(session: ApplySession) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for file_result in session.results:
        decisions: list[dict[str, object]] = []
        for decision in file_result.decisions[:_MAX_DECISIONS_PER_FILE]:
            entry: dict[str, object] = {
                "header": decision.hunk_header,
                "strategy": decision.strategy,
                "position": decision.selected_pos,
                "similarity": decision.similarity,
                "message": decision.message,
                "ai_recommendation": decision.ai_recommendation,
                "ai_confidence": decision.ai_confidence,
                "ai_source": decision.ai_source,
            }
            candidates = decision.candidates[:_MAX_CANDIDATES_PER_DECISION]
            if candidates:
                entry["candidates"] = [
                    {
                        "position": candidate.position,
                        "score": candidate.score,
                        "anchors": candidate.anchor_hits,
                    }
                    for candidate in candidates
                ]
            if decision.ai_explanation:
                entry["ai_explanation"] = decision.ai_explanation
            decisions.append(entry)

        file_payload: dict[str, object] = {
            "path": file_result.relative_to_root,
            "absolute_path": (
                str(file_result.file_path) if file_result.file_path else ""
            ),
            "file_type": file_result.file_type,
            "hunks_applied": file_result.hunks_applied,
            "hunks_total": file_result.hunks_total,
            "decisions": decisions,
        }
        if file_result.skipped_reason:
            file_payload["skipped_reason"] = file_result.skipped_reason
        files.append(file_payload)

    payload: dict[str, object] = {
        "project_root": str(session.project_root),
        "dry_run": session.dry_run,
        "threshold": session.threshold,
        "started_at": session.started_at,
        "files": files,
    }
    return payload


def _call_summary_service(
    payload: dict[str, object], *, timeout: float
) -> dict[str, object]:
    endpoint = os.getenv("PATCH_GUI_AI_SUMMARY_ENDPOINT")
    if not endpoint:
        raise AISummaryError(
            "AI summary endpoint not configured (set PATCH_GUI_AI_SUMMARY_ENDPOINT)."
        )

    token = os.getenv("PATCH_GUI_AI_SUMMARY_TOKEN") or os.getenv("PATCH_GUI_AI_TOKEN")

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(endpoint, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            charset = response.headers.get_content_charset("utf-8")
    except urllib.error.HTTPError as exc:  # pragma: no cover - network error paths
        raise AISummaryError(f"HTTP error {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network error paths
        raise AISummaryError(str(exc)) from exc

    try:
        decoded = body.decode(charset or "utf-8")
    except UnicodeDecodeError as exc:  # pragma: no cover - rare
        raise AISummaryError("Cannot decode AI summary response") from exc

    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise AISummaryError("Invalid JSON from AI summary endpoint") from exc

    if not isinstance(parsed, dict):
        raise AISummaryError("AI summary response must be a JSON object")

    return parsed


def _normalise_summary_text(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_summary_response(response: dict[str, object]) -> AISummary:
    overall = _normalise_summary_text(
        response.get("summary")
        or response.get("overall")
        or response.get("session")
        or response.get("text")
    )

    per_file: Dict[str, str] = {}
    files_obj = response.get("files") or response.get("per_file")
    if isinstance(files_obj, dict):
        for key, value in files_obj.items():
            key_str = str(key).strip()
            text = _normalise_summary_text(value)
            if key_str and text:
                per_file[key_str] = text
    elif isinstance(files_obj, list):
        for item in files_obj:
            if not isinstance(item, dict):
                continue
            path = item.get("file") or item.get("path") or item.get("name")
            text = item.get("summary") or item.get("text") or item.get("description")
            path_str = _normalise_summary_text(path)
            text_str = _normalise_summary_text(text)
            if path_str and text_str:
                per_file[path_str] = text_str

    return AISummary(overall=overall, per_file=per_file)


def _cache_key_for_payload(
    session: ApplySession, payload: dict[str, object]
) -> Optional[str]:
    if session.summary_diff_digest:
        return session.summary_diff_digest
    try:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )
    except TypeError:  # pragma: no cover - payload contains unserialisable items
        return None
    digest = hashlib.sha256(encoded).hexdigest()
    return digest


def _store_cache_entry(cache_key: str, summary: AISummary, timestamp: float) -> None:
    with _SUMMARY_CACHE_LOCK:
        _SUMMARY_CACHE[cache_key] = (
            AISummary(overall=summary.overall, per_file=dict(summary.per_file)),
            timestamp,
        )


def _load_cache_entry(cache_key: str) -> Optional[tuple[AISummary, float]]:
    with _SUMMARY_CACHE_LOCK:
        cached = _SUMMARY_CACHE.get(cache_key)
    if cached is None:
        return None
    summary, timestamp = cached
    return (
        AISummary(overall=summary.overall, per_file=dict(summary.per_file)),
        timestamp,
    )


def _invoke_callback(callback: Optional[Callable[..., None]], *args: object) -> None:
    if callback is None:
        return
    try:
        callback(*args)
    except Exception:  # pragma: no cover - defensive guard
        logger.debug("Summary callback raised", exc_info=True)


def generate_session_summary(
    session: ApplySession,
    *,
    use_cache: bool = True,
    timeout: float = _DEFAULT_TIMEOUT,
    hooks: Optional[AISummaryHooks] = None,
) -> Optional[AISummary]:
    """Return the AI-generated summary for ``session`` if configured."""

    hooks = hooks or AISummaryHooks()
    session.summary_error = None
    session.summary_duration = None
    session.summary_generated_at = None
    session.summary_cache_hit = None

    start_ts = time.time()
    try:
        payload = _build_payload(session)
    except Exception as exc:  # pragma: no cover - defensive
        session.summary_error = str(exc)
        logger.exception("Failed to build AI summary payload: %s", exc)
        return None

    cache_key = _cache_key_for_payload(session, payload)
    session.summary_cache_key = cache_key

    cached_entry: Optional[tuple[AISummary, float]] = None
    if use_cache and cache_key:
        cached_entry = _load_cache_entry(cache_key)

    if cached_entry is not None:
        summary, timestamp = cached_entry
        session.summary_cache_hit = True
        session.summary_generated_at = timestamp
        session.summary_duration = 0.0
        _invoke_callback(hooks.on_cached, summary)
        _invoke_callback(hooks.on_complete, summary, True)
        return summary

    session.summary_cache_hit = False
    _invoke_callback(hooks.on_start, payload)

    try:
        response = _call_summary_service(payload, timeout=timeout)
        _invoke_callback(hooks.on_chunk, response)
        summary = _parse_summary_response(response)
    except AISummaryError as exc:
        session.summary_error = str(exc)
        session.summary_duration = time.time() - start_ts
        logger.info("AI summary unavailable: %s", exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive guard
        session.summary_error = str(exc)
        session.summary_duration = time.time() - start_ts
        logger.exception("Unexpected error while retrieving AI summary: %s", exc)
        return None

    if summary.is_empty():
        session.summary_duration = time.time() - start_ts
        session.summary_error = "AI summary response did not contain any text"
        logger.info(session.summary_error)
        return None

    completed_ts = time.time()
    session.summary_generated_at = completed_ts
    session.summary_duration = completed_ts - start_ts
    session.summary_error = None

    if cache_key:
        _store_cache_entry(cache_key, summary, completed_ts)

    _invoke_callback(hooks.on_complete, summary, False)
    return summary
