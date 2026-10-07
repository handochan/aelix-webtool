"""Aelix web tools. Importing the package performs no I/O or host imports."""

from __future__ import annotations

from typing import Any

__version__ = "0.2.0"


def setup(aelix: Any) -> None:
    """The installed ``aelix.extensions`` factory."""
    from .extension import register

    register(aelix)


__all__ = ["setup"]
