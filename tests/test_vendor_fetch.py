"""Tests for ordered vendor fetch steps."""
from __future__ import annotations

import vendor_fetch as vf


def test_run_steps_returns_first_success() -> None:
    calls: list[str] = []

    def fail() -> None:
        calls.append("fail")
        return None

    def ok() -> str:
        calls.append("ok")
        return "610.62"

    result = vf.run_steps(
        [vf.FetchStep("first", fail), vf.FetchStep("second", ok)],
        vendor="test",
    )
    assert result.value == "610.62"
    assert result.method == "second"
    assert result.failures == ["first: no data"]
    assert calls == ["fail", "ok"]


def test_run_steps_records_all_failures() -> None:
    result = vf.run_steps(
        [vf.FetchStep("a", lambda: None), vf.FetchStep("b", lambda: None)],
        vendor="empty",
    )
    assert result.value is None
    assert result.failures == ["a: no data", "b: no data"]
    diag = vf.last_fetch_diag("empty")
    assert diag is not None
    assert len(diag.failures) == 2


def test_failed_run_does_not_reuse_previous_vendor_value() -> None:
    """A failed lookup must not inherit the last success for the same vendor.

    The key is the vendor name alone, so two devices from one vendor (AMD GPU and AMD
    chipset) share it — reusing the value reported the first device's version for the
    second, and made a dead endpoint look healthy to vendor_endpoint_health.
    """
    vf.clear_session_diagnostics()
    first = vf.run_steps([vf.FetchStep("ok", lambda: "26.6.4")], vendor="acme")
    assert first.value == "26.6.4"

    second = vf.run_steps([vf.FetchStep("a", lambda: None)], vendor="acme")
    assert second.value is None
    assert second.method == ""
    assert second.failures == ["a: no data"]

    diag = vf.last_fetch_diag("acme")
    assert diag is not None
    assert diag.value is None


if __name__ == "__main__":
    test_run_steps_returns_first_success()
    test_run_steps_records_all_failures()
    print("vendor_fetch tests OK")
