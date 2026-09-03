"""Unit tests for catalog_lru_cache LRU helpers."""

from __future__ import annotations

import os
import sys
from collections import OrderedDict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import catalog_lru_cache as lru


def test_lru_touch_moves_key_to_end() -> None:
    cache: OrderedDict[str, tuple] = OrderedDict([("a", (1,)), ("b", (2,))])
    lru._lru_cache_touch(cache, "a")
    assert list(cache.keys()) == ["b", "a"]


def test_lru_set_evicts_oldest_when_over_max() -> None:
    cache: OrderedDict[str, tuple] = OrderedDict()
    lru._lru_cache_set(cache, "one", (1,), max_entries=2)
    lru._lru_cache_set(cache, "two", (2,), max_entries=2)
    lru._lru_cache_set(cache, "three", (3,), max_entries=2)
    assert list(cache.keys()) == ["two", "three"]
    assert "one" not in cache


def test_lru_set_updates_existing_key() -> None:
    cache: OrderedDict[str, tuple] = OrderedDict()
    lru._lru_cache_set(cache, "k", (1,), max_entries=3)
    lru._lru_cache_set(cache, "k", (9,), max_entries=3)
    assert cache["k"] == (9,)
    assert len(cache) == 1
