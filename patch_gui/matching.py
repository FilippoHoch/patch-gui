"""Candidate matching strategies for locating diff hunk insertion points."""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

try:  # pragma: no cover - exercised through fallback tests
    from rapidfuzz import fuzz

    _HAS_RAPIDFUZZ = True
except ImportError:  # pragma: no cover - handled in tests
    fuzz = None  # type: ignore[assignment]
    _HAS_RAPIDFUZZ = False


from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class MatchingStrategy(str, Enum):
    """High level strategy choices exposed to the configuration layer."""

    AUTO = "auto"
    LEGACY = "legacy"
    RAPIDFUZZ = "rapidfuzz"
    TOKEN = "token"  # Backwards compatible alias for the optimised matcher.

    @property
    def resolved(self) -> "MatchingStrategy":
        if self is MatchingStrategy.TOKEN:
            return MatchingStrategy.RAPIDFUZZ
        return self


@dataclass(frozen=True)
class MatchingOptions:
    """Configuration knobs influencing the candidate search."""

    strategy: MatchingStrategy = MatchingStrategy.AUTO
    use_anchors: bool = True
    max_candidates: int | None = None


@dataclass(frozen=True)
class CandidateMatch:
    """Describe a single candidate location."""

    position: int
    score: float
    anchor_hits: int = 0

    def as_tuple(self) -> tuple[int, float]:
        return (self.position, self.score)


@dataclass(frozen=True)
class MatchingStats:
    """Diagnostic metrics recorded during matching."""

    evaluated_windows: int
    total_windows: int
    anchor_windows: int
    strategy: MatchingStrategy
    backend: str
    duration: float

    @property
    def anchor_pruned(self) -> bool:
        return self.anchor_windows < self.total_windows


@dataclass(frozen=True)
class CandidateSearchResult:
    """Outcome of :func:`find_candidates`."""

    candidates: list[CandidateMatch]
    stats: MatchingStats


def _resolve_strategy(strategy: MatchingStrategy | str | None) -> MatchingStrategy:
    if strategy is None:
        return MatchingStrategy.AUTO
    if isinstance(strategy, MatchingStrategy):
        return strategy.resolved
    try:
        resolved = MatchingStrategy(str(strategy))
    except ValueError:
        logger.warning("Unknown matching strategy %s – defaulting to legacy", strategy)
        return MatchingStrategy.LEGACY
    return resolved.resolved


def _sequence_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _rapidfuzz_ratio(a: str, b: str) -> float:
    if not _HAS_RAPIDFUZZ or fuzz is None:  # pragma: no cover - guarded by tests
        return _sequence_ratio(a, b)
    return fuzz.ratio(a, b) / 100.0


def _candidate_positions_with_anchors(
    file_lines: Sequence[str], before_lines: Sequence[str]
) -> Counter[int]:
    """Return candidate positions keyed by the amount of matching anchors."""

    window_len = len(before_lines)
    if window_len == 0 or window_len > len(file_lines):
        return Counter()

    anchors: list[tuple[int, str]] = []
    anchors.append((0, before_lines[0]))
    if window_len > 1:
        anchors.append((window_len - 1, before_lines[-1]))

    hits: Counter[int] = Counter()
    max_start = len(file_lines) - window_len
    for offset, anchor_line in anchors:
        for idx, line in enumerate(file_lines):
            if line != anchor_line:
                continue
            start = idx - offset
            if 0 <= start <= max_start:
                hits[start] += 1
    return hits


def _iter_windows(
    file_lines: Sequence[str],
    window_len: int,
    positions: Iterable[int],
) -> Iterable[tuple[int, str]]:
    for start in positions:
        end = start + window_len
        if end > len(file_lines):
            continue
        yield start, "".join(file_lines[start:end])


def _score_windows(
    window_texts: Sequence[str],
    target_text: str,
    *,
    use_rapidfuzz: bool,
) -> list[float]:
    if not window_texts:
        return []
    if use_rapidfuzz and _HAS_RAPIDFUZZ and fuzz is not None:
        return [_rapidfuzz_ratio(text, target_text) for text in window_texts]
    return [_sequence_ratio(text, target_text) for text in window_texts]


def find_candidates(
    file_lines: Sequence[str],
    before_lines: Sequence[str],
    threshold: float,
    options: MatchingOptions | None = None,
) -> CandidateSearchResult:
    """Return matching candidates sorted by similarity score."""

    opts = options or MatchingOptions()
    resolved_strategy = _resolve_strategy(opts.strategy)
    window_len = len(before_lines)
    total_windows = max(len(file_lines) - window_len + 1, 0)

    if window_len == 0 or total_windows == 0:
        stats = MatchingStats(
            evaluated_windows=0,
            total_windows=total_windows,
            anchor_windows=0,
            strategy=resolved_strategy,
            backend="none" if window_len == 0 else "sequence",
            duration=0.0,
        )
        return CandidateSearchResult(candidates=[], stats=stats)

    start_time = time.perf_counter()
    target_text = "".join(before_lines)
    exact_join = "".join(file_lines)
    exact_index = exact_join.find(target_text)
    if exact_index != -1:
        cumulative = 0
        for idx, line in enumerate(file_lines):
            if cumulative == exact_index:
                match = CandidateMatch(position=idx, score=1.0, anchor_hits=window_len)
                duration = time.perf_counter() - start_time
                stats = MatchingStats(
                    evaluated_windows=1,
                    total_windows=total_windows,
                    anchor_windows=1,
                    strategy=resolved_strategy,
                    backend="exact",
                    duration=duration,
                )
                return CandidateSearchResult(candidates=[match], stats=stats)
            cumulative += len(line)

    anchors = Counter[int]()
    if opts.use_anchors:
        anchors = _candidate_positions_with_anchors(file_lines, before_lines)

    if anchors:
        candidate_positions = sorted(anchors.keys())
        anchor_windows = len(candidate_positions)
    else:
        candidate_positions = list(range(total_windows))
        anchor_windows = total_windows

    use_rapidfuzz = _HAS_RAPIDFUZZ and resolved_strategy in (
        MatchingStrategy.AUTO,
        MatchingStrategy.RAPIDFUZZ,
    )

    if resolved_strategy is MatchingStrategy.LEGACY:
        use_rapidfuzz = False

    backend = "rapidfuzz" if use_rapidfuzz else "sequence"

    window_texts: list[str] = []
    ordered_positions: list[int] = []
    for start, text in _iter_windows(file_lines, window_len, candidate_positions):
        ordered_positions.append(start)
        window_texts.append(text)

    scores = _score_windows(window_texts, target_text, use_rapidfuzz=use_rapidfuzz)

    evaluated = len(scores)
    candidates: list[CandidateMatch] = []
    for start, score in zip(ordered_positions, scores):
        if score >= threshold:
            candidates.append(
                CandidateMatch(
                    position=start,
                    score=score,
                    anchor_hits=anchors.get(start, 0),
                )
            )

    candidates.sort(key=lambda m: (-m.score, -m.anchor_hits, m.position))
    if opts.max_candidates is not None:
        candidates = candidates[: opts.max_candidates]

    duration = time.perf_counter() - start_time
    stats = MatchingStats(
        evaluated_windows=evaluated,
        total_windows=total_windows,
        anchor_windows=anchor_windows,
        strategy=resolved_strategy,
        backend=backend,
        duration=duration,
    )

    logger.debug(
        "Matching completed: strategy=%s backend=%s evaluated=%d/%d anchors=%d duration=%.4fs",
        resolved_strategy.value,
        backend,
        evaluated,
        total_windows,
        anchor_windows,
        duration,
    )

    if not candidates and resolved_strategy is MatchingStrategy.AUTO and use_rapidfuzz:
        logger.debug("RapidFuzz yielded no candidates – retrying with legacy scorer")
        legacy_opts = MatchingOptions(
            strategy=MatchingStrategy.LEGACY,
            use_anchors=opts.use_anchors,
            max_candidates=opts.max_candidates,
        )
        return find_candidates(file_lines, before_lines, threshold, legacy_opts)

    return CandidateSearchResult(candidates=candidates, stats=stats)


def find_candidate_positions(
    file_lines: Sequence[str],
    before_lines: Sequence[str],
    threshold: float,
    *,
    strategy: MatchingStrategy = MatchingStrategy.AUTO,
    use_anchors: bool = True,
) -> list[tuple[int, float]]:
    """Compatibility wrapper returning legacy tuple results."""

    result = find_candidates(
        file_lines,
        before_lines,
        threshold,
        MatchingOptions(strategy=strategy, use_anchors=use_anchors),
    )
    return [candidate.as_tuple() for candidate in result.candidates]


__all__ = [
    "CandidateMatch",
    "CandidateSearchResult",
    "MatchingOptions",
    "MatchingStats",
    "MatchingStrategy",
    "find_candidates",
    "find_candidate_positions",
]
