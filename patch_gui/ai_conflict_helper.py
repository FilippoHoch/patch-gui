"""Utility helpers to provide guidance when a hunk cannot be applied automatically."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from difflib import unified_diff
from typing import Sequence


__all__ = [
    "AI_CONFLICT_ENDPOINT_ENV",
    "AI_CONFLICT_TOKEN_ENV",
    "AI_SHARED_ENDPOINT_ENV",
    "AI_SHARED_TOKEN_ENV",
    "AIConflictAssistantError",
    "ConflictSuggestion",
    "generate_conflict_suggestion",
    "urllib",
]


logger = logging.getLogger(__name__)


AI_CONFLICT_ENDPOINT_ENV = "PATCH_GUI_AI_CONFLICT_ENDPOINT"
AI_CONFLICT_TOKEN_ENV = "PATCH_GUI_AI_CONFLICT_TOKEN"
AI_SHARED_ENDPOINT_ENV = "PATCH_GUI_AI_ENDPOINT"
AI_SHARED_TOKEN_ENV = "PATCH_GUI_AI_TOKEN"

_DEFAULT_TIMEOUT = 15.0
_MAX_CONTEXT_CHARS = 6000
_MAX_DIFF_CHARS = 8000


@dataclass
class ConflictSuggestion:
    """Structured response describing how to resolve a failed hunk."""

    message: str
    patch: str | None = None
    source: str = "heuristic"
    confidence: float | None = None


class AIConflictAssistantError(RuntimeError):
    """Raised when the remote assistant cannot provide a suggestion."""


def _trim_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    ellipsis = "…"
    return value[: max(0, limit - len(ellipsis))] + ellipsis


def _build_patch(
    before_lines: Sequence[str], after_lines: Sequence[str], header: str
) -> str | None:
    """Return a minimal diff that the user can copy to apply manually."""

    diff_lines = list(
        unified_diff(
            before_lines,
            after_lines,
            fromfile="original",
            tofile="suggested",
            lineterm="",
        )
    )
    if not diff_lines and not header:
        return None
    result: list[str] = []
    if header:
        result.append(header)
    result.extend(diff_lines)
    diff_text = "\n".join(result).strip()
    if not diff_text:
        return None
    return _trim_text(diff_text, _MAX_DIFF_CHARS)


def _extract_context(
    file_context: str, before_text: str, window: int = 120
) -> str | None:
    if not file_context or not before_text:
        return None
    idx = file_context.find(before_text)
    if idx == -1:
        return None
    start = max(0, idx - window)
    end = min(len(file_context), idx + len(before_text) + window)
    snippet = file_context[start:end]
    trimmed = snippet.strip()
    if not trimmed:
        return None
    return _trim_text(trimmed, _MAX_CONTEXT_CHARS)


def _call_ai_service(payload: dict[str, object]) -> dict[str, object]:
    endpoint = os.getenv(AI_CONFLICT_ENDPOINT_ENV) or os.getenv(AI_SHARED_ENDPOINT_ENV)
    if not endpoint:
        raise AIConflictAssistantError(
            "AI conflict endpoint not configured (set PATCH_GUI_AI_CONFLICT_ENDPOINT)."
        )

    token = os.getenv(AI_CONFLICT_TOKEN_ENV) or os.getenv(AI_SHARED_TOKEN_ENV)
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
        raise AIConflictAssistantError(f"HTTP error {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network error paths
        raise AIConflictAssistantError(str(exc)) from exc

    try:
        decoded = body.decode(charset or "utf-8")
    except UnicodeDecodeError as exc:  # pragma: no cover - rare decoding errors
        raise AIConflictAssistantError("Cannot decode AI response") from exc

    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise AIConflictAssistantError("Invalid JSON from AI endpoint") from exc

    if not isinstance(parsed, dict):
        raise AIConflictAssistantError("AI response must be a JSON object")

    return parsed


def _parse_ai_response(response: dict[str, object]) -> ConflictSuggestion:
    raw_message = response.get("message") or response.get("assistant_message")
    raw_patch = response.get("patch") or response.get("diff")
    if raw_message is None and raw_patch is None:
        raise AIConflictAssistantError("AI response missing 'message' or 'patch'")

    message = str(raw_message).strip() if raw_message is not None else ""
    patch = str(raw_patch).strip() if raw_patch is not None else None
    source = str(response.get("source") or "assistant")
    raw_confidence = response.get("confidence")
    confidence: float | None
    if raw_confidence is None:
        confidence = None
    else:
        if isinstance(raw_confidence, (int, float)):
            confidence = float(raw_confidence)
        elif isinstance(raw_confidence, str):
            try:
                confidence = float(raw_confidence)
            except ValueError as exc:
                raise AIConflictAssistantError(
                    "Invalid confidence value from AI response"
                ) from exc
        else:
            raise AIConflictAssistantError("Invalid confidence value from AI response")

    if patch:
        patch = _trim_text(patch, _MAX_DIFF_CHARS)

    if not message:
        message = "Suggerimento generato automaticamente dall'assistente AI."

    return ConflictSuggestion(
        message=message,
        patch=patch or None,
        source=source,
        confidence=confidence,
    )


def _maybe_request_ai(
    *,
    file_context: str,
    hunk_header: str,
    before_lines: Sequence[str],
    after_lines: Sequence[str],
    failure_reason: str,
    original_diff: str,
) -> ConflictSuggestion | None:
    endpoint = os.getenv(AI_CONFLICT_ENDPOINT_ENV) or os.getenv(AI_SHARED_ENDPOINT_ENV)
    if not endpoint:
        return None

    payload: dict[str, object] = {
        "task": "conflict-resolution",
        "hunk_header": hunk_header,
        "before": list(before_lines),
        "after": list(after_lines),
        "failure_reason": failure_reason,
        "original_diff": _trim_text(original_diff, _MAX_DIFF_CHARS),
        "file_context": _trim_text(file_context, _MAX_CONTEXT_CHARS),
    }

    try:
        response = _call_ai_service(payload)
        suggestion = _parse_ai_response(response)
        suggestion.source = suggestion.source or "assistant"
        return suggestion
    except AIConflictAssistantError as exc:
        logger.warning("AI conflict assistant unavailable: %s", exc)
        return None


def generate_conflict_suggestion(
    *,
    file_context: str,
    hunk_header: str,
    before_lines: Sequence[str],
    after_lines: Sequence[str],
    failure_reason: str,
    original_diff: str,
) -> ConflictSuggestion | None:
    """Return textual guidance and a patch snippet to resolve a failed hunk."""

    before_text = "".join(before_lines)
    after_text = "".join(after_lines)

    if not (before_text or after_text or original_diff.strip()):
        return None

    ai_suggestion = _maybe_request_ai(
        file_context=file_context,
        hunk_header=hunk_header,
        before_lines=before_lines,
        after_lines=after_lines,
        failure_reason=failure_reason,
        original_diff=original_diff,
    )
    if ai_suggestion is not None:
        return ai_suggestion

    failure_reason = failure_reason.strip()

    message_lines: list[str] = []
    intro = "Suggerimento assistente: analizza il blocco seguente e applica le modifiche manualmente."
    message_lines.append(intro)
    if failure_reason:
        message_lines.append(f"Motivo del fallimento: {failure_reason}.")

    if before_text and after_text:
        message_lines.append(
            "Sostituisci il blocco corrente con la versione proposta mantenendo eventuali adattamenti necessari."
        )
    elif after_text:
        message_lines.append(
            "Inserisci il nuovo blocco nel punto corretto del file, verificando l'indentazione e il contesto."
        )
    else:
        message_lines.append(
            "Rimuovi manualmente le righe indicate e conferma che il contesto rimanente sia coerente."
        )

    context_excerpt = _extract_context(file_context, before_text)
    if context_excerpt:
        message_lines.append("Contesto trovato nel file:")
        message_lines.append(context_excerpt)

    patch_text = (original_diff.strip() or None) or _build_patch(
        before_lines, after_lines, hunk_header
    )
    if patch_text:
        message_lines.append(
            "È possibile copiare il diff suggerito per applicarlo manualmente."
        )

    message = "\n".join(message_lines)

    return ConflictSuggestion(message=message, patch=patch_text)
