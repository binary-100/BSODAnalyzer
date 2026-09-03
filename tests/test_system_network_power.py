"""Tests for active network adapter power management helpers."""
from __future__ import annotations

import json
from unittest import mock

import system_network_power as snp


def test_query_active_adapter_parses_json() -> None:
    payload = {
        "Name": "Wi-Fi",
        "InterfaceDescription": "Killer(R) Wi-Fi 6 AX1650",
        "MediaType": "802.11",
        "Status": "Up",
        "AllowComputerToTurnOffDevice": 1,
    }
    with mock.patch.object(snp, "_run_ps", return_value=(True, json.dumps(payload))):
        adapter = snp.query_active_network_adapter()
    assert adapter is not None
    assert adapter["Name"] == "Wi-Fi"
    assert adapter["PowerSavingOn"] is True
    assert adapter["PowerManagementSupported"] is True


def test_set_active_adapter_rejects_bad_name() -> None:
    ok, msg = snp.set_active_adapter_allow_turn_off("bad/name", allow_turn_off=False)
    assert not ok
    assert "Invalid" in msg


def test_set_active_adapter_calls_powershell() -> None:
    with mock.patch.object(snp, "_run_ps", return_value=(True, "OK")) as run_ps:
        ok, msg = snp.set_active_adapter_allow_turn_off("Ethernet", allow_turn_off=False)
    assert ok
    assert "awake" in msg.lower()
    assert "Disabled" in run_ps.call_args[0][0]


def test_adapter_power_summary_power_saving_on() -> None:
    text = snp.adapter_power_summary(
        {
            "InterfaceDescription": "Realtek USB GbE",
            "PowerManagementSupported": True,
            "PowerSavingOn": True,
        }
    )
    assert "turn off" in text.lower()
    assert "Realtek" in text
