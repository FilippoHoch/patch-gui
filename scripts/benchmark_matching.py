#!/usr/bin/env python3
"""Quick benchmark utility to compare matching strategies on a single file."""

from __future__ import annotations

import argparse
import random
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from patch_gui import matching
from patch_gui.matching import MatchingStrategy


@contextmanager
def _count_sequence_calls() -> Iterator[dict[str, int]]:
    counter = {"calls": 0}
    original_matcher = matching.SequenceMatcher

    class CountingMatcher:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            counter["calls"] += 1
            self._delegate = original_matcher(*args, **kwargs)

        def ratio(self) -> float:
            return self._delegate.ratio()

        def __getattr__(self, name: str) -> Any:  # pragma: no cover - defensive
            return getattr(self._delegate, name)

    matching.SequenceMatcher = CountingMatcher  # type: ignore[assignment]
    try:
        yield counter
    finally:
        matching.SequenceMatcher = original_matcher  # type: ignore[assignment]


def _load_lines(path: Path, encoding: str | None) -> list[str]:
    try:
        data = path.read_text(encoding=encoding or "utf-8")
    except UnicodeDecodeError:
        data = path.read_text(encoding="utf-8", errors="replace")
    return data.splitlines(keepends=True)


def _run_benchmark(
    lines: list[str],
    window: int,
    threshold: float,
    positions: list[int],
    strategy: MatchingStrategy,
) -> tuple[float, int]:
    start = time.perf_counter()
    with _count_sequence_calls() as counter:
        for pos in positions:
            before = lines[pos : pos + window]
            matching.find_candidate_positions(
                lines, before, threshold, strategy=strategy
            )
    elapsed = time.perf_counter() - start
    return elapsed, counter["calls"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark the matching strategies on a single file."
    )
    parser.add_argument("file", type=Path, help="Path to the file to benchmark")
    parser.add_argument(
        "--window",
        type=int,
        default=8,
        help="Number of lines in each sampled hunk window (default: 8)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Similarity threshold used for fuzzy matching (default: 0.85)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=40,
        help="Number of random windows to benchmark (default: 40)",
    )
    parser.add_argument(
        "--encoding",
        default=None,
        help="Optional file encoding override (default: autodetect via UTF-8)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed used for pseudo-random sampling (default: 42)",
    )
    args = parser.parse_args()

    lines = _load_lines(args.file, args.encoding)
    if not lines:
        parser.error("The selected file does not contain any lines to benchmark.")
    if args.window <= 0:
        parser.error("--window must be a positive integer")
    if not 0 < args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")

    max_start = len(lines) - args.window
    if max_start < 0:
        parser.error(
            "Window size exceeds file length; decrease --window or choose a larger file."
        )

    random.seed(args.seed)
    available_positions = list(range(max_start + 1))
    if not available_positions:
        positions = [0] * args.iterations
    else:
        positions = random.choices(available_positions, k=args.iterations)

    print(
        f"Benchmarking {args.file} (lines={len(lines)}, window={args.window}, "
        f"iterations={len(positions)}, threshold={args.threshold:.2f})"
    )

    results: list[tuple[MatchingStrategy, float, int]] = []
    for strategy in (MatchingStrategy.TOKEN, MatchingStrategy.LEGACY):
        elapsed, calls = _run_benchmark(
            lines, args.window, args.threshold, positions, strategy
        )
        results.append((strategy, elapsed, calls))

    for strategy, elapsed, calls in results:
        avg_ms = (elapsed / len(positions)) * 1000 if positions else 0.0
        print(
            f"- {strategy.value:>6}: {elapsed:.3f}s total, {avg_ms:.2f}ms avg, "
            f"SequenceMatcher calls: {calls}"
        )

    auto_elapsed, auto_calls = _run_benchmark(
        lines, args.window, args.threshold, positions, MatchingStrategy.AUTO
    )
    avg_ms = (auto_elapsed / len(positions)) * 1000 if positions else 0.0
    print(
        f"-   auto: {auto_elapsed:.3f}s total, {avg_ms:.2f}ms avg, "
        f"SequenceMatcher calls: {auto_calls}"
    )


if __name__ == "__main__":
    main()
