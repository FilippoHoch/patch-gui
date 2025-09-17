"""Central place to store the package version."""

from __future__ import annotations

import sys

__all__ = ["__version__"]

__version__ = "0.1.0"

_PACKAGE_NAME = __name__.rsplit(".", 1)[0]
_parent = sys.modules.get(_PACKAGE_NAME)
if _parent is not None:
    setattr(_parent, "__version__", __version__)
