"""Declare the gettext builtin installed at runtime for type checkers."""

from collections.abc import Callable

_: Callable[[str], str]
