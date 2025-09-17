from __future__ import annotations

from pathlib import Path


def test_cmdclass_uses_python_qualified_identifiers() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")

    assert "build_translations:BuildPy" not in text
    assert "build_translations:SDist" not in text
