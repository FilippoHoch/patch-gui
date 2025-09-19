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
    "clear_summary_cache",
    "compute_summary_cache_key",
    "generate_session_summary",
]


class AISummaryError(RuntimeError):
    """Raised when the AI summary service cannot produce a result."""


@dataclass(slots=True)
class AISummary:
    """Container for the overall and per-file summaries returned by the AI."""

    overall: Optional[str] = None
    per_file: Dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.overall or self.per_file)


@dataclass(slots=True)
class AISummaryHooks:
    """Callback hooks that allow integration with streaming endpoints."""

    on_request_start: Optional[Callable[[], None]] = None
    """Called immediately before the HTTP request is issued."""

    on_raw_chunk: Optional[Callable[[bytes], None]] = None
    """Called when a raw response chunk is received (once for non-streaming)."""

    on_response: Optional[Callable[[dict[str, object]], None]] = None
    """Called after the JSON payload has been parsed."""


_DEFAULT_TIMEOUT = 15.0
_MAX_DECISIONS_PER_FILE = 50
_MAX_CANDIDATES_PER_DECISION = 5

_SUMMARY_CACHE: dict[str, AISummary] = {}
_SUMMARY_CACHE_LOCK = threading.Lock()


def clear_summary_cache() -> None:
    """Empty the in-memory AI summary cache (useful in tests)."""

    with _SUMMARY_CACHE_LOCK:
        _SUMMARY_CACHE.clear()


def compute_summary_cache_key(diff_text: str) -> str:
    """Return a stable hash that can be used to cache a diff's AI summary."""

    normalized = diff_text.replace("\r\n", "\n").strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


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
                entry["candidates"] = [list(candidate) for candidate in candidates]
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
    payload: dict[str, object],
    *,
    timeout: float | None = None,
    hooks: AISummaryHooks | None = None,
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

    if hooks and hooks.on_request_start:
        try:
            hooks.on_request_start()
        except Exception:  # pragma: no cover - defensive, hook-supplied code
            logger.exception("AI summary hook raised during request start")

    effective_timeout = _DEFAULT_TIMEOUT if timeout is None else float(timeout)

    try:
        with urllib.request.urlopen(request, timeout=effective_timeout) as response:
            body = response.read()
            if hooks and hooks.on_raw_chunk:
                try:
                    hooks.on_raw_chunk(body)
                except Exception:  # pragma: no cover - defensive
                    logger.exception("AI summary hook raised while handling chunk")
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

    if hooks and hooks.on_response:
        try:
            hooks.on_response(parsed)
        except Exception:  # pragma: no cover - defensive
            logger.exception("AI summary hook raised while processing response")

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


def _get_cached_summary(key: str) -> Optional[AISummary]:
    with _SUMMARY_CACHE_LOCK:
        cached = _SUMMARY_CACHE.get(key)
    return cached


def _store_cached_summary(key: str, summary: AISummary) -> None:
    with _SUMMARY_CACHE_LOCK:
        _SUMMARY_CACHE[key] = summary


def generate_session_summary(
    session: ApplySession,
    *,
    cache_key: str | None = None,
    timeout: float | None = None,
    use_cache: bool = True,
    hooks: AISummaryHooks | None = None,
) -> Optional[AISummary]:
    """Return the AI-generated summary for ``session`` if configured."""

    key = cache_key or session.summary_cache_key
    session.summary_cache_key = key
    session.summary_error = None

    if use_cache and key:
        cached = _get_cached_summary(key)
        if cached is not None:
            session.summary_cache_hit = True
            session.summary_cached_at = time.time()
            return cached

    try:
        payload = _build_payload(session)
        response = _call_summary_service(payload, timeout=timeout, hooks=hooks)
        summary = _parse_summary_response(response)
    except AISummaryError as exc:
        logger.info("AI summary unavailable: %s", exc)
        session.summary_error = str(exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Unexpected error while retrieving AI summary: %s", exc)
        session.summary_error = str(exc)
        return None

    if summary.is_empty():
        logger.info("AI summary response did not contain any text")
        session.summary_error = "empty"
        return None

    session.summary_cache_hit = False
    session.summary_generated_at = time.time()
    if key:
        _store_cached_summary(key, summary)

    return summary
