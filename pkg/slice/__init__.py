"""Slice utilities."""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def chunk(items: list[T], chunk_size: int) -> list[list[T]]:
    """Split items into chunks of chunk_size.
    
    chunk([1, 2, 3], 2) => [[1, 2], [3]]
    """
    if not items:
        return []
    result = []
    for i in range(0, len(items), chunk_size):
        result.append(items[i:i + chunk_size])
    return result
