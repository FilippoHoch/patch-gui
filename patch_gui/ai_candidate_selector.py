"""Utilities for ranking ambiguous hunk candidates with the help of an AI model."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional, Sequence

from .matching import CandidateMatch
from .patcher import HunkView

logger = logging.getLogger(__name__)


class AIAssistantError(RuntimeError):
    """Raised when the AI assistant cannot provide a suggestion."""


@dataclass(slots=True)
class AISuggestion:
    """Suggestion returned by :func:`rank_candidates`."""

    candidate_index: int
    position: int
    confidence: float
    explanation: str | None
    source: str  # "assistant" | "local"


_DEFAULT_TIMEOUT = 10.0
_MAX_SNIPPET_CHARS = 400


def _build_payload(
    file_lines: Sequence[str],
    hv: HunkView,
    candidates: Sequence[CandidateMatch],
) -> dict[str, object]:
    """Return the JSON payload describing the ambiguous hunk context."""

    window_len = len(hv.before_lines) or len(hv.after_lines) or 1
    snippets: list[dict[str, object]] = []
    for index, candidate in enumerate(candidates, start=1):
        position = candidate.position
        similarity = candidate.score
        snippet_lines = file_lines[position : position + window_len]
        snippet = "".join(snippet_lines)
        if len(snippet) > _MAX_SNIPPET_CHARS:
            snippet = snippet[: _MAX_SNIPPET_CHARS - 1] + "…"
        snippets.append(
            {
                "index": index,
                "position": position,
                "similarity": similarity,
                "excerpt": snippet,
                "anchors": candidate.anchor_hits,
            }
        )

    return {
        "header": hv.header,
        "before": hv.before_lines,
        "after": hv.after_lines,
        "context": hv.context_lines,
        "candidates": snippets,
    }


def _call_ai_service(payload: dict[str, object]) -> dict[str, object]:
    """Send ``payload`` to the configured AI endpoint and return the response."""

    endpoint = os.getenv("PATCH_GUI_AI_ENDPOINT")
    if not endpoint:
        raise AIAssistantError(
            "AI endpoint not configured (set PATCH_GUI_AI_ENDPOINT)."
        )

    token = os.getenv("PATCH_GUI_AI_TOKEN")
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
        raise AIAssistantError(f"HTTP error {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network error paths
        raise AIAssistantError(str(exc)) from exc

    try:
        decoded = body.decode(charset or "utf-8")
    except UnicodeDecodeError as exc:  # pragma: no cover - rare
        raise AIAssistantError("Cannot decode AI response") from exc

    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise AIAssistantError("Invalid JSON from AI endpoint") from exc

    if not isinstance(parsed, dict):
        raise AIAssistantError("AI response must be a JSON object")

    return parsed


def _parse_ai_choice(
    response: dict[str, object],
    candidate_positions: dict[int, int],
) -> AISuggestion:
    """Extract an :class:`AISuggestion` from the AI ``response``."""

    choice_obj = response.get("choice") or response.get("best") or response
    if not isinstance(choice_obj, dict):
        raise AIAssistantError("AI response missing 'choice' object")

    candidate_index: Optional[int] = None
    if "candidate_index" in choice_obj:
        try:
            candidate_index = int(choice_obj["candidate_index"])
        except (TypeError, ValueError) as exc:
            raise AIAssistantError("Invalid candidate_index in AI response") from exc
    elif "index" in choice_obj:
        try:
            candidate_index = int(choice_obj["index"])
        except (TypeError, ValueError) as exc:
            raise AIAssistantError("Invalid index in AI response") from exc

    position: Optional[int] = None
    if "position" in choice_obj:
        try:
            position = int(choice_obj["position"])
        except (TypeError, ValueError) as exc:
            raise AIAssistantError("Invalid position in AI response") from exc

    if candidate_index is not None and candidate_index in candidate_positions:
        position = candidate_positions[candidate_index]
    elif position is not None:
        # Align to known candidate index if possible.
        for idx, pos in candidate_positions.items():
            if pos == position:
                candidate_index = idx
                break

    if candidate_index is None or candidate_index not in candidate_positions:
        raise AIAssistantError("AI response did not reference a valid candidate")

    raw_confidence = choice_obj.get("confidence")
    try:
        confidence = float(raw_confidence) if raw_confidence is not None else 0.0
    except (TypeError, ValueError) as exc:
        raise AIAssistantError("Invalid confidence value from AI response") from exc

    explanation = choice_obj.get("explanation")
    if explanation is not None:
        explanation = str(explanation)

    return AISuggestion(
        candidate_index=candidate_index,
        position=candidate_positions[candidate_index],
        confidence=confidence,
        explanation=explanation,
        source="assistant",
    )


def _local_best_candidate(
    file_lines: Sequence[str],
    hv: HunkView,
    candidates: Sequence[CandidateMatch],
) -> Optional[AISuggestion]:
    """Return the best candidate using local heuristics only."""

    if not candidates:
        return None

    reference_lines = hv.before_lines or hv.after_lines
    block_len = len(reference_lines)
    if block_len == 0 and hv.after_lines:
        block_len = len(hv.after_lines)
    if block_len <= 0:
        block_len = 1

    reference_text = "".join(reference_lines) or "".join(hv.after_lines)

    best: Optional[AISuggestion] = None
    for index, candidate in enumerate(candidates, start=1):
        position = candidate.position
        similarity = candidate.score
        if similarity is not None:
            score = float(similarity)
        elif reference_text:
            snippet = "".join(file_lines[position : position + block_len])
            if not snippet and 0 <= position < len(file_lines):
                snippet = file_lines[position]
            score = SequenceMatcher(None, reference_text, snippet).ratio()
        else:
            continue

        explanation = "Local heuristic based on textual similarity."
        if best is None or score > best.confidence:
            best = AISuggestion(
                candidate_index=index,
                position=position,
                confidence=score,
                explanation=explanation,
                source="local",
            )

    return best


def rank_candidates(
    file_lines: Sequence[str],
    hv: HunkView,
    candidates: Sequence[CandidateMatch],
    *,
    use_ai: bool,
    logger_override: Optional[logging.Logger] = None,
) -> Optional[AISuggestion]:
    """Return the best candidate suggestion using AI with local fallback."""

    log = logger_override or logger

    local_choice = _local_best_candidate(file_lines, hv, candidates)
    if not candidates:
        return None

    if not use_ai:
        return local_choice

    try:
        payload = _build_payload(file_lines, hv, candidates)
        candidate_positions = {
            index: candidate.position
            for index, candidate in enumerate(candidates, start=1)
        }
        response = _call_ai_service(payload)
        ai_choice = _parse_ai_choice(response, candidate_positions)
        if ai_choice.confidence <= 0 and local_choice is not None:
            # Avoid zero-confidence suggestions when a heuristic score is available.
            ai_choice.confidence = local_choice.confidence
        if ai_choice.explanation is None and local_choice is not None:
            ai_choice.explanation = local_choice.explanation
        return ai_choice
    except AIAssistantError as exc:
        log.warning("AI assistant unavailable: %s", exc)
        return local_choice
