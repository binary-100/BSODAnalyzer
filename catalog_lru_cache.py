"""Generic LRU helpers for catalog session caches."""

from __future__ import annotations

from collections import OrderedDict


def _lru_cache_touch(cache: OrderedDict, key: str) -> None:
    if key in cache:
        cache.move_to_end(key)


def _lru_cache_set(
    cache: OrderedDict,
    key: str,
    value: tuple,
    *,
    max_entries: int,
) -> None:
    if key in cache:
        cache.move_to_end(key)
    cache[key] = value
    while len(cache) > max_entries:
        cache.popitem(last=False)


__all__ = ["_lru_cache_set", "_lru_cache_touch"]
