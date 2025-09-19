from __future__ import annotations

from pathlib import Path

import patch_gui


def test_package_includes_typing_marker() -> None:
    package_paths = list(patch_gui.__path__)
    assert package_paths
    package_dir = Path(package_paths[0]).resolve()
    assert (package_dir / "py.typed").is_file()
