"""Candidate matching strategies for locating hunk positions in target files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, Mapping, MutableMapping, Sequence


logger = logging.getLogger(__name__)


try:  # pragma: no cover - exercised via runtime environment
    from rapidfuzz.distance import Levenshtein  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    Levenshtein = None  # type: ignore


@dataclass(slots=True, frozen=True)
class CandidateMatch:
    """Representation of a candidate position in the target file."""

    position: int
    score: float
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MatchingOptions:
    """Configuration toggles for the matching strategy."""

    use_rapidfuzz: bool = True
    enable_structural_anchors: bool = True
    max_anchor_lines: int = 4


@dataclass(slots=True)
class MatchingResult:
    """Return value for :func:`find_candidates`."""

    candidates: list[CandidateMatch]
    metadata: MutableMapping[str, object]


def _select_anchor_offsets(before_lines: Sequence[str], max_anchor_lines: int) -> list[int]:
    """Return offsets within ``before_lines`` that are good anchor candidates."""

    offsets: list[int] = []
    seen: dict[str, int] = {}
    for line in before_lines:
        seen[line] = seen.get(line, 0) + 1

    for offset, raw_line in enumerate(before_lines):
        line = raw_line.strip()
        if not line:
            continue
        if seen[raw_line] > 1 and not (
            line.endswith(":")
            or line.startswith("def ")
            or line.startswith("class ")
            or line.startswith("if ")
            or line.startswith("for ")
            or line.startswith("while ")
        ):
            continue
        offsets.append(offset)
        if len(offsets) >= max_anchor_lines:
            break
    return offsets


def _collect_anchor_positions(
    file_lines: Sequence[str],
    before_lines: Sequence[str],
    offsets: Iterable[int],
) -> tuple[set[int], int]:
    """Return candidate start positions based on matching anchor lines."""

    positions: set[int] = set()
    hits = 0
    if not offsets:
        return positions, hits

    line_index: dict[str, list[int]] = {}
    for idx, line in enumerate(file_lines):
        line_index.setdefault(line, []).append(idx)

    window_len = len(before_lines)
    for anchor_offset in offsets:
        anchor_line = before_lines[anchor_offset]
        indices = line_index.get(anchor_line)
        if not indices:
            continue
        hits += 1
        for index in indices:
            start = index - anchor_offset
            if start < 0:
                continue
            if start + window_len > len(file_lines):
                continue
            positions.add(start)
    return positions, hits


def _legacy_similarity(a: str, b: str) -> float:
    """Fallback similarity score using :mod:`difflib`."""

    return SequenceMatcher(None, a, b).ratio()


def _rapidfuzz_similarity(a: str, b: str) -> float:
    if Levenshtein is None:
        return _legacy_similarity(a, b)
    return float(Levenshtein.normalized_similarity(a, b))


def find_candidates(
    file_lines: Sequence[str],
    before_lines: Sequence[str],
    threshold: float,
    options: MatchingOptions | None = None,
) -> MatchingResult:
    """Return candidate windows that meet ``threshold``.

    The return value includes both the candidates and metadata describing
    the work performed (number of windows scored, anchor usage, etc.).
    """

    opts = options or MatchingOptions()
    metadata: MutableMapping[str, object] = {
        "engine": "rapidfuzz" if opts.use_rapidfuzz and Levenshtein is not None else "difflib",
        "anchor_hits": 0,
        "total_windows": 0,
        "scored_windows": 0,
        "candidate_windows": 0,
    }

    if not before_lines:
        logger.debug("Skipping candidate search: empty 'before' block")
        return MatchingResult([], metadata)

    window_len = len(before_lines)
    if window_len == 0 or window_len > len(file_lines):
        return MatchingResult([], metadata)

    target_text = "".join(before_lines)
    total_windows = len(file_lines) - window_len + 1
    metadata["total_windows"] = max(total_windows, 0)

    scorer = _rapidfuzz_similarity if opts.use_rapidfuzz else _legacy_similarity
    if scorer is _rapidfuzz_similarity and Levenshtein is None:
        metadata["engine"] = "difflib"
    elif scorer is _rapidfuzz_similarity:
        metadata["engine"] = "rapidfuzz"

    candidate_positions: set[int] = set()
    anchor_offsets: list[int] = []
    anchor_positions: set[int] = set()
    if opts.enable_structural_anchors and window_len > 1:
        anchor_offsets = _select_anchor_offsets(before_lines, opts.max_anchor_lines)
        positions, hits = _collect_anchor_positions(file_lines, before_lines, anchor_offsets)
        candidate_positions |= positions
        anchor_positions |= positions
        metadata["anchor_hits"] = hits

    if not candidate_positions:
        candidate_positions = set(range(0, total_windows))
    metadata["candidate_windows"] = len(candidate_positions)

    ordered_positions = sorted(candidate_positions)
    candidates: list[CandidateMatch] = []

    # First check for exact matches to short-circuit fuzzy scoring when possible.
    before_slice = list(before_lines)
    for pos in ordered_positions:
        if file_lines[pos : pos + window_len] == before_slice:
            candidate = CandidateMatch(
                position=pos,
                score=1.0,
                metadata={"exact": True, "derived_from_anchor": pos in anchor_positions},
            )
            logger.debug("Exact candidate found at position %d", pos)
            return MatchingResult([candidate], metadata)

    for pos in ordered_positions:
        window_text = "".join(file_lines[pos : pos + window_len])
        score = scorer(window_text, target_text)
        metadata["scored_windows"] = int(metadata["scored_windows"]) + 1
        if score >= threshold:
            candidate_metadata: dict[str, object] = {"derived_from_anchor": pos in anchor_positions}
            candidates.append(CandidateMatch(position=pos, score=score, metadata=candidate_metadata))

    candidates.sort(key=lambda c: (-c.score, c.position))
    return MatchingResult(candidates, metadata)


__all__ = [
    "CandidateMatch",
    "MatchingOptions",
    "MatchingResult",
    "find_candidates",
]

