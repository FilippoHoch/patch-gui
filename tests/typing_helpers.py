"""Utilities that provide type-safe wrappers around common pytest decorators."""

from __future__ import annotations

from typing import Any, Callable, TypeVar, cast

import pytest

F = TypeVar("F", bound=Callable[..., object])


def fixture(func: F) -> F:
    """Return ``func`` wrapped by :func:`pytest.fixture` with preserved typing."""

    return cast(F, pytest.fixture(func))


def parametrize(*args: Any, **kwargs: Any) -> Callable[[F], F]:
    """Type-aware wrapper around :func:`pytest.mark.parametrize`."""

    decorator = pytest.mark.parametrize(*args, **kwargs)

    def _apply(func: F) -> F:
        return cast(F, decorator(func))

    return _apply
