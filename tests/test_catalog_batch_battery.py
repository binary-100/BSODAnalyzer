"""MSCatalog batch timeout and split-retry behavior on slow/battery paths."""

from __future__ import annotations

import catalog_ps_batch as cbatch


def test_mscatalog_batch_timeout_not_capped_at_120_for_small_parallel_batches() -> None:
    """Regression: 9 parallel queries on battery must not use a 120s kill timer."""
    ac = cbatch.mscatalog_batch_timeout_seconds(9, throttle=5, is_pwsh=True, on_battery=False)
    bat = cbatch.mscatalog_batch_timeout_seconds(9, throttle=5, is_pwsh=True, on_battery=True)
    assert ac >= 180
    assert bat >= 180
    assert bat >= ac


def test_mscatalog_batch_timeout_scales_with_query_count() -> None:
    small = cbatch.mscatalog_batch_timeout_seconds(9, on_battery=True)
    large = cbatch.mscatalog_batch_timeout_seconds(24, on_battery=True)
    assert large > small
