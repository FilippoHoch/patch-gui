"""Benchmark helper for the file lookup index."""

from __future__ import annotations

import argparse
import random
import string
import tempfile
import time
from pathlib import Path

from patch_gui.file_index import FileIndex


def _random_name(prefix: str, length: int = 8) -> str:
    alphabet = string.ascii_lowercase
    return prefix + "_" + "".join(random.choice(alphabet) for _ in range(length))


def _generate_repo(root: Path, files: int, duplicates: int) -> list[str]:
    targets: list[str] = []
    for idx in range(files):
        folder = root / f"package_{idx % max(1, duplicates)}" / f"module_{idx}"
        folder.mkdir(parents=True, exist_ok=True)
        filename = _random_name("file") + ".py"
        path = folder / filename
        path.write_text("print('hello world')\n", encoding="utf-8")
        targets.append(str(path.relative_to(root)))
    return targets


def run_benchmark(files: int, duplicates: int, lookups: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        targets = _generate_repo(root, files, duplicates)
        print(f"Generated repository with {files} files in {root}")

        start = time.perf_counter()
        index = FileIndex(root, exclude_dirs=())
        build_duration = time.perf_counter() - start
        print(
            "Index built in {:.3f}s (scanned={}, skipped_dirs={})".format(
                build_duration,
                index.metrics.scanned_files,
                index.metrics.skipped_directories,
            )
        )

        sample_targets = random.sample(targets, min(len(targets), lookups))
        lookup_start = time.perf_counter()
        for rel in sample_targets:
            index.lookup(rel)
        lookup_duration = time.perf_counter() - lookup_start
        avg = lookup_duration / max(1, len(sample_targets))
        print(
            "Performed {} lookups in {:.3f}s (avg {:.6f}s)".format(
                len(sample_targets), lookup_duration, avg
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--files", type=int, default=5000, help="Number of files to generate"
    )
    parser.add_argument(
        "--duplicates",
        type=int,
        default=25,
        help="Number of directory buckets to reuse for suffix collisions",
    )
    parser.add_argument(
        "--lookups",
        type=int,
        default=250,
        help="Number of random lookups to perform",
    )
    args = parser.parse_args()
    run_benchmark(args.files, args.duplicates, args.lookups)


if __name__ == "__main__":
    main()
