"""Candidate matching strategies for diff hunk alignment."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Mapping, MutableMapping, Sequence

from difflib import SequenceMatcher

try:  # pragma: no cover - optional dependency
    from rapidfuzz import process  # type: ignore
    from rapidfuzz.distance import Levenshtein  # type: ignore
except Exception:  # pragma: no cover - rapidfuzz missing or incompatible
    Levenshtein = None  # type: ignore[assignment]
    process = None  # type: ignore[assignment]
    HAS_RAPIDFUZZ = False
else:  # pragma: no cover - guarded import
    HAS_RAPIDFUZZ = True


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CandidateMatch:
    """A potential location where a diff hunk might apply."""

    position: int
    score: float
    metadata: MutableMapping[str, object] = field(default_factory=dict)

    def as_tuple(self) -> tuple[int, float]:
        return self.position, self.score


DEFAULT_OPTIONS: Mapping[str, object] = {
    "use_rapidfuzz": True,
    "use_anchors": True,
    "max_candidates": None,
}


def _compute_similarity(
    window_text: str,
    target_text: str,
    *,
    use_rapidfuzz: bool,
    threshold: float,
) -> tuple[float, str]:
    """Return the similarity score and the scorer that produced it."""

    if use_rapidfuzz and HAS_RAPIDFUZZ and Levenshtein is not None:
        try:
            rf_score = float(
                Levenshtein.normalized_similarity(
                    window_text,
                    target_text,
                    score_cutoff=threshold,
                )
            )
        except Exception:  # pragma: no cover - rapidfuzz failure fallback
            logger.debug(
                "RapidFuzz similarity failed; falling back to SequenceMatcher",
                exc_info=True,
            )
        else:
            if rf_score >= threshold:
                return rf_score, "rapidfuzz"
            seq_score = SequenceMatcher(None, window_text, target_text).ratio()
            if seq_score >= threshold and seq_score > rf_score:
                logger.debug(
                    "SequenceMatcher score %.3f exceeded RapidFuzz score %.3f; using SequenceMatcher",
                    seq_score,
                    rf_score,
                )
                return seq_score, "sequence_matcher"
            return rf_score, "rapidfuzz"

    score = SequenceMatcher(None, window_text, target_text).ratio()
    return score, "sequence_matcher"


def _build_anchor_metadata(
    file_lines: Sequence[str], before_lines: Sequence[str]
) -> dict[int, dict[str, object]]:
    """Return anchor metadata indexed by candidate start position."""

    anchors: dict[int, dict[str, object]] = {}
    if not before_lines or not file_lines:
        return anchors

    window_len = len(before_lines)
    if window_len > len(file_lines):
        return anchors

    first_line = before_lines[0]
    last_line = before_lines[-1] if window_len > 1 else None
    total = len(file_lines) - window_len + 1

    for pos in range(total):
        hits: list[str] = []
        if file_lines[pos] == first_line:
            hits.append("start")
        if last_line is not None and file_lines[pos + window_len - 1] == last_line:
            hits.append("end")
        if hits:
            anchors[pos] = {
                "anchor_hits": len(hits),
                "anchors": hits,
            }
    return anchors


def _normalize_options(options: Mapping[str, object] | None) -> dict[str, object]:
    normalized = dict(DEFAULT_OPTIONS)
    if options:
        normalized.update(options)
    return normalized


def find_candidates(
    file_lines: Sequence[str],
    before_lines: Sequence[str],
    threshold: float,
    options: Mapping[str, object] | None = None,
) -> list[CandidateMatch]:
    """Return candidate start positions for ``before_lines`` within ``file_lines``.

    The returned list is sorted by descending similarity score, with the position as a
    secondary key to guarantee deterministic ordering.
    """

    if not before_lines:
        logger.debug("No 'before' lines supplied; no candidates generated")
        return []

    window_len = len(before_lines)
    if window_len == 0 or window_len > len(file_lines):
        return []

    opts = _normalize_options(options)
    use_rapidfuzz = bool(opts.get("use_rapidfuzz", True))
    if use_rapidfuzz and not HAS_RAPIDFUZZ:
        use_rapidfuzz = False
    use_anchors = bool(opts.get("use_anchors", True))
    max_candidates_option = opts.get("max_candidates")
    max_candidates = None
    if isinstance(max_candidates_option, int) and max_candidates_option > 0:
        max_candidates = max_candidates_option

    target_text = "".join(before_lines)
    total = len(file_lines) - window_len + 1
    anchor_metadata = _build_anchor_metadata(file_lines, before_lines) if use_anchors else {}
    anchor_positions = sorted(anchor_metadata)

    window_texts = ["".join(file_lines[pos : pos + window_len]) for pos in range(total)]

    ordered_positions: Iterable[int]
    if anchor_positions:
        remaining = [pos for pos in range(total) if pos not in anchor_metadata]
        ordered_positions = list(anchor_positions) + remaining
    else:
        ordered_positions = range(total)

    candidates: list[CandidateMatch] = []
    exact_matches: list[CandidateMatch] = []
    rapid_scores: dict[int, float] = {}
    if use_rapidfuzz and HAS_RAPIDFUZZ and process is not None:
        try:
            for _, score, idx in process.extract_iter(
                target_text,
                window_texts,
                scorer=Levenshtein.normalized_similarity,
                processor=None,
                score_cutoff=threshold,
            ):
                rapid_scores[idx] = float(score)
        except Exception:  # pragma: no cover - defensive guard
            logger.debug(
                "RapidFuzz batch similarity failed; falling back to per-window scoring",
                exc_info=True,
            )
            rapid_scores = {}

    for pos in ordered_positions:
        window_text = window_texts[pos]
        metadata: dict[str, object] = {
            "window_length": window_len,
        }
        if anchor_metadata:
            metadata.update(anchor_metadata.get(pos, {}))
        if window_text == target_text:
            metadata["scorer"] = "exact"
            candidate = CandidateMatch(position=pos, score=1.0, metadata=metadata)
            exact_matches.append(candidate)
            continue
        if rapid_scores and pos in rapid_scores:
            score = rapid_scores[pos]
            scorer = "rapidfuzz"
        else:
            score, scorer = _compute_similarity(
                window_text,
                target_text,
                use_rapidfuzz=use_rapidfuzz,
                threshold=threshold,
            )
        if score >= threshold:
            metadata["scorer"] = scorer
            candidate = CandidateMatch(position=pos, score=score, metadata=metadata)
            candidates.append(candidate)

    if exact_matches:
        exact_matches.sort(key=lambda item: item.position)
        logger.debug(
            "Candidate search found %d exact matches", len(exact_matches)
        )
        return exact_matches

    candidates.sort(key=lambda item: (-item.score, item.position))

    if max_candidates is not None and len(candidates) > max_candidates:
        candidates = candidates[:max_candidates]

    logger.debug(
        "Candidate search: window_len=%d threshold=%.3f options=%s -> %d matches",
        window_len,
        threshold,
        opts,
        len(candidates),
    )
    return candidates


__all__ = ["CandidateMatch", "DEFAULT_OPTIONS", "HAS_RAPIDFUZZ", "find_candidates"]
