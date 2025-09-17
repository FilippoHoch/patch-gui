"""Typed wrappers around common pytest decorators for static analysis."""

from __future__ import annotations

from typing import Any, Callable, TypeVar, cast

import pytest

_F = TypeVar("_F", bound=Callable[..., object])


def typed_fixture(*args: Any, **kwargs: Any) -> Callable[[_F], _F]:
    return cast("Callable[[_F], _F]", pytest.fixture(*args, **kwargs))


def typed_parametrize(*args: Any, **kwargs: Any) -> Callable[[_F], _F]:
    return cast("Callable[[_F], _F]", pytest.mark.parametrize(*args, **kwargs))


__all__ = ["typed_fixture", "typed_parametrize"]
