"""Helpers for fuzzy matching candidate ranges within files."""

from __future__ import annotations

import hashlib
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from difflib import SequenceMatcher
from typing import Sequence

logger = logging.getLogger(__name__)


class MatchingStrategy(str, Enum):
    """Available matching strategies for locating diff hunk candidates."""

    AUTO = "auto"
    LEGACY = "legacy"
    TOKEN = "token"


@dataclass(frozen=True)
class MatchingStats:
    """Track diagnostic metrics for candidate discovery."""

    evaluated_windows: int
    sequence_matches: int


def _hash_lines(lines: Sequence[str]) -> bytes:
    """Return a stable hash for ``lines`` suitable for indexing."""

    hasher = hashlib.blake2b(digest_size=16)
    for line in lines:
        # ``surrogatepass`` preserves undecodable bytes while ensuring the hash
        # remains stable across Python versions.
        hasher.update(line.encode("utf-8", "surrogatepass"))
        hasher.update(b"\0")
    return hasher.digest()


def _joined_text(lines: Sequence[str]) -> str:
    return "".join(lines)


def _legacy_find_candidates(
    file_lines: Sequence[str], before_lines: Sequence[str], threshold: float
) -> tuple[list[tuple[int, float]], MatchingStats]:
    """Replicate the historical behaviour using a full sliding window scan."""

    candidates: list[tuple[int, float]] = []
    if not before_lines:
        return candidates, MatchingStats(evaluated_windows=0, sequence_matches=0)
    window_len = len(before_lines)
    target_text = _joined_text(before_lines)
    evaluated = 0

    file_text = _joined_text(file_lines)
    logger.debug(
        "Ricerca candidati (legacy): window_len=%d, threshold=%.3f, testo_target=%d char",
        window_len,
        threshold,
        len(target_text),
    )
    idx = file_text.find(target_text)
    if idx != -1:
        cumulative = 0
        for i, line in enumerate(file_lines):
            if cumulative == idx:
                return [(i, 1.0)], MatchingStats(evaluated_windows=1, sequence_matches=1)
            cumulative += len(line)

    matches = 0
    for i in range(0, len(file_lines) - window_len + 1):
        window_text = _joined_text(file_lines[i : i + window_len])
        score = SequenceMatcher(None, window_text, target_text).ratio()
        evaluated += 1
        matches += 1
        if score >= threshold:
            candidates.append((i, score))

    candidates.sort(key=lambda x: (-x[1], x[0]))
    logger.debug(
        "Trovati %d candidati (legacy) con soglia %.3f",
        len(candidates),
        threshold,
    )
    return candidates, MatchingStats(evaluated_windows=evaluated, sequence_matches=matches)


def _build_gram_index(file_lines: Sequence[str], gram_size: int) -> dict[bytes, list[int]]:
    index: dict[bytes, list[int]] = defaultdict(list)
    if gram_size <= 0 or gram_size > len(file_lines):
        return index
    for pos in range(len(file_lines) - gram_size + 1):
        digest = _hash_lines(file_lines[pos : pos + gram_size])
        index[digest].append(pos)
    return index


def _token_find_candidates(
    file_lines: Sequence[str],
    before_lines: Sequence[str],
    threshold: float,
    *,
    gram_size: int = 4,
) -> tuple[list[tuple[int, float]], MatchingStats]:
    """Locate candidate positions using hashed n-grams to prune comparisons."""

    if not before_lines:
        return [], MatchingStats(evaluated_windows=0, sequence_matches=0)
    window_len = len(before_lines)
    if window_len > len(file_lines):
        return [], MatchingStats(evaluated_windows=0, sequence_matches=0)

    target_text = _joined_text(before_lines)
    file_text = _joined_text(file_lines)
    logger.debug(
        "Ricerca candidati (token): window_len=%d, threshold=%.3f, testo_target=%d char",
        window_len,
        threshold,
        len(target_text),
    )

    # Quick exact match shortcut identical to the legacy implementation.
    idx = file_text.find(target_text)
    if idx != -1:
        cumulative = 0
        for i, line in enumerate(file_lines):
            if cumulative == idx:
                return [(i, 1.0)], MatchingStats(evaluated_windows=1, sequence_matches=1)
            cumulative += len(line)

    gram = max(1, min(gram_size, window_len))
    index = _build_gram_index(file_lines, gram)
    if not index:
        return [], MatchingStats(evaluated_windows=0, sequence_matches=0)

    counts: Counter[int] = Counter()
    for offset in range(window_len - gram + 1):
        digest = _hash_lines(before_lines[offset : offset + gram])
        positions = index.get(digest)
        if not positions:
            continue
        for pos in positions:
            start = pos - offset
            if 0 <= start <= len(file_lines) - window_len:
                counts[start] += 1

    if not counts:
        return [], MatchingStats(evaluated_windows=0, sequence_matches=0)

    sorted_positions = [pos for pos, _ in counts.most_common()]
    evaluated = 0
    matched = 0
    candidates: list[tuple[int, float]] = []

    for pos in sorted_positions:
        window_text = _joined_text(file_lines[pos : pos + window_len])
        evaluated += 1
        score = SequenceMatcher(None, window_text, target_text).ratio()
        matched += 1
        if score >= threshold:
            candidates.append((pos, score))

    candidates.sort(key=lambda item: (-item[1], item[0]))
    logger.debug(
        "Trovati %d candidati (token) con soglia %.3f dopo %d confronti",
        len(candidates),
        threshold,
        evaluated,
    )
    return candidates, MatchingStats(evaluated_windows=evaluated, sequence_matches=matched)


def find_candidate_positions(
    file_lines: Sequence[str],
    before_lines: Sequence[str],
    threshold: float,
    *,
    strategy: MatchingStrategy = MatchingStrategy.AUTO,
) -> list[tuple[int, float]]:
    """Return candidate start positions sorted by similarity score."""

    if isinstance(strategy, MatchingStrategy):
        resolved_strategy = strategy
    else:
        try:
            resolved_strategy = MatchingStrategy(str(strategy))
        except ValueError:
            logger.warning(
                "Strategia matching sconosciuta %s – fallback legacy", strategy
            )
            resolved_strategy = MatchingStrategy.LEGACY

    legacy_candidates: list[tuple[int, float]] | None = None

    if resolved_strategy in {MatchingStrategy.AUTO, MatchingStrategy.TOKEN}:
        token_candidates, stats = _token_find_candidates(
            file_lines, before_lines, threshold
        )
        if token_candidates:
            logger.debug(
                "Strategia token restituisce %d candidati (windows=%d)",
                len(token_candidates),
                stats.evaluated_windows,
            )
            return token_candidates
        logger.debug(
            "Strategia token senza risultati, ricaduta al legacy (windows=%d)",
            stats.evaluated_windows,
        )
        legacy_candidates, _ = _legacy_find_candidates(file_lines, before_lines, threshold)
        return legacy_candidates

    legacy_candidates, _ = _legacy_find_candidates(file_lines, before_lines, threshold)
    return legacy_candidates


__all__ = [
    "MatchingStrategy",
    "MatchingStats",
    "find_candidate_positions",
]
