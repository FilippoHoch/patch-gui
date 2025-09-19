"""Helpers for retrieving AI-generated summaries of patch sessions."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, Optional

from .patcher import ApplySession

logger = logging.getLogger(__name__)

__all__ = ["AISummary", "generate_session_summary", "AISummaryError"]


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
                        "similarity": candidate.score,
                        "metadata": dict(candidate.metadata),
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


def _call_summary_service(payload: dict[str, object]) -> dict[str, object]:
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
        with urllib.request.urlopen(request, timeout=_DEFAULT_TIMEOUT) as response:
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


def generate_session_summary(session: ApplySession) -> Optional[AISummary]:
    """Return the AI-generated summary for ``session`` if configured."""

    try:
        payload = _build_payload(session)
        response = _call_summary_service(payload)
        summary = _parse_summary_response(response)
    except AISummaryError as exc:
        logger.info("AI summary unavailable: %s", exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Unexpected error while retrieving AI summary: %s", exc)
        return None

    if summary.is_empty():
        logger.info("AI summary response did not contain any text")
        return None

    return summary
