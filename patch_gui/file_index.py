"""Utilities for indexing project files for quick lookup."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Iterable, Sequence


@dataclass
class FileIndexMetrics:
    """Statistics collected while building the file index."""

    build_duration: float = 0.0
    scanned_files: int = 0
    skipped_directories: int = 0
    skipped_files: int = 0

    def to_dict(self) -> dict[str, float | int]:
        return {
            "build_duration": self.build_duration,
            "scanned_files": self.scanned_files,
            "skipped_directories": self.skipped_directories,
            "skipped_files": self.skipped_files,
        }


@dataclass
class LookupEvent:
    """Metrics recorded for a single lookup operation."""

    rel_path: str
    suffix_components: int
    candidates_considered: int
    duration: float


@dataclass
class FileLookupMetrics:
    """Aggregated lookup metrics for debugging purposes."""

    total_queries: int = 0
    suffix_hits: int = 0
    total_candidates_considered: int = 0
    last_query: str | None = None
    last_candidates: int = 0
    last_duration: float = 0.0

    def register(self, event: LookupEvent) -> None:
        self.total_queries += 1
        self.total_candidates_considered += event.candidates_considered
        self.last_query = event.rel_path
        self.last_candidates = event.candidates_considered
        self.last_duration = event.duration
        if event.suffix_components > 0:
            self.suffix_hits += 1

    def to_dict(self) -> dict[str, float | int | str | None]:
        return {
            "total_queries": self.total_queries,
            "suffix_hits": self.suffix_hits,
            "total_candidates_considered": self.total_candidates_considered,
            "last_query": self.last_query,
            "last_candidates": self.last_candidates,
            "last_duration": self.last_duration,
        }


def _normalize_excludes(exclude_dirs: Sequence[str]) -> list[tuple[str, ...]]:
    normalized: list[tuple[str, ...]] = []
    for raw in exclude_dirs:
        if not raw:
            continue
        parts = tuple(part for part in Path(raw).parts if part not in ("", "."))
        if parts:
            normalized.append(parts)
    return normalized


class FileIndex:
    """Index of project files keyed by filename and path suffix."""

    def __init__(self, project_root: Path, exclude_dirs: Sequence[str]):
        self.project_root = project_root
        self.exclude_dirs = tuple(exclude_dirs)
        self._normalized_excludes = _normalize_excludes(exclude_dirs)
        self.metrics = FileIndexMetrics()
        self._name_map: DefaultDict[str, list[Path]] = defaultdict(list)
        self._suffix_map: DefaultDict[tuple[str, ...], list[Path]] = defaultdict(list)
        self._mtimes: dict[Path, float] = {}
        self._build()

    # ------------------------------------------------------------------
    # public helpers
    # ------------------------------------------------------------------
    def lookup(self, rel_path: str) -> tuple[list[Path], LookupEvent]:
        """Return candidate paths for ``rel_path`` using the cached index."""

        start = time.perf_counter()
        stripped = rel_path.strip()
        if not stripped:
            return [], LookupEvent(
                rel_path=stripped,
                suffix_components=0,
                candidates_considered=0,
                duration=0.0,
            )

        parts = tuple(part for part in Path(stripped).parts if part)
        name = parts[-1] if parts else stripped

        candidates: dict[Path, tuple[int, float]] = {}
        suffix_components = 0

        for depth in range(len(parts), 0, -1):
            suffix = parts[-depth:]
            matches = self._suffix_map.get(suffix)
            if not matches:
                continue
            suffix_components = max(suffix_components, depth)
            for match in matches:
                candidates[match] = (
                    max(
                        candidates.get(match, (0, self._mtimes.get(match, 0.0)))[0],
                        depth,
                    ),
                    self._mtimes.get(match, 0.0),
                )

        if not candidates and name:
            for match in self._name_map.get(name, []):
                candidates.setdefault(match, (0, self._mtimes.get(match, 0.0)))

        ordered = sorted(
            candidates.keys(),
            key=lambda path: (
                -candidates[path][0],
                -candidates[path][1],
                str(path),
            ),
        )

        duration = time.perf_counter() - start
        event = LookupEvent(
            rel_path=stripped,
            suffix_components=suffix_components,
            candidates_considered=len(ordered),
            duration=duration,
        )
        return ordered, event

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _build(self) -> None:
        start = time.perf_counter()
        root = self.project_root
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            current = Path(dirpath)
            try:
                relative_parts = current.relative_to(root).parts
            except ValueError:
                relative_parts = ()

            # filter directories in place
            keep_dirs: list[str] = []
            for dirname in dirnames:
                candidate_parts = relative_parts + (dirname,)
                if self._should_exclude(candidate_parts):
                    self.metrics.skipped_directories += 1
                    continue
                keep_dirs.append(dirname)
            dirnames[:] = keep_dirs

            for filename in filenames:
                path = current / filename
                try:
                    if not path.is_file():
                        self.metrics.skipped_files += 1
                        continue
                except OSError:
                    self.metrics.skipped_files += 1
                    continue

                try:
                    rel = path.relative_to(root)
                except ValueError:
                    continue

                self.metrics.scanned_files += 1
                self._name_map[filename].append(path)
                parts = rel.parts
                for depth in range(1, len(parts) + 1):
                    suffix = parts[-depth:]
                    self._suffix_map[suffix].append(path)
                try:
                    self._mtimes[path] = path.stat().st_mtime
                except OSError:
                    self._mtimes[path] = 0.0

        self.metrics.build_duration = time.perf_counter() - start

    def _should_exclude(self, parts: Iterable[str]) -> bool:
        if not self._normalized_excludes:
            return False
        tuple_parts = tuple(parts)
        if not tuple_parts:
            return False
        for pattern in self._normalized_excludes:
            if len(pattern) == 1:
                if pattern[0] in tuple_parts:
                    return True
            else:
                window = len(pattern)
                for idx in range(len(tuple_parts) - window + 1):
                    if tuple_parts[idx : idx + window] == pattern:
                        return True
        return False


__all__ = [
    "FileIndex",
    "FileIndexMetrics",
    "FileLookupMetrics",
    "LookupEvent",
]
