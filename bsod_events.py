"""Windows event log queries for BSOD Analyzer."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from bsod_runtime import run_powershell
import log_read_windows as lrw

def _parse_bugcheck_from_message(msg: str) -> str | None:
    """Extract bugcheck code from Event 1001 message (e.g. '0x00000124')."""
    if not msg:
        return None
    m = re.search(r"bugcheck was:\s*(0x[0-9a-fA-F]+)", msg)
    return m.group(1) if m else None


def query_bugcheck_events() -> tuple[list, bool]:
    """Query Windows Event Log for crash events (one PowerShell run for 1001, 41, 6008).

    Returns (events, query_failed). query_failed is True when PowerShell did not
    return usable JSON (timeout, access denied, parse error) — not when the log
    is simply empty.
    """
    events = []
    seen_times = set()

    # Single script: query all three event types and return one JSON (saves 2 process spawns)
    ps_combined = f"""
    $out = @{{ Events1001=@(); Events41=@(); Events6008=@() }}
    try {{
        Get-WinEvent -FilterHashtable @{{LogName='System'; ProviderName='Microsoft-Windows-WER-SystemErrorReporting'; Id=1001}} -MaxEvents {lrw.CRASH_WER1001_MAX} -ErrorAction SilentlyContinue | ForEach-Object {{
            $xml = [xml]$_.ToXml(); $h = @{{ TimeCreated=$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'); Message=$_.Message }}
            if ($xml.Event.EventData.Data) {{ foreach ($d in $xml.Event.EventData.Data) {{ $h[$d.Name] = $d.'#text' }} }}
            $out.Events1001 += [PSCustomObject]$h
        }}
    }} catch {{}}
    try {{
        Get-WinEvent -FilterHashtable @{{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=41}} -MaxEvents {lrw.CRASH_KERNEL_POWER_41_MAX} -ErrorAction SilentlyContinue | ForEach-Object {{
            $xml = [xml]$_.ToXml(); $h = @{{ TimeCreated=$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss') }}
            if ($xml.Event.EventData.Data) {{ foreach ($d in $xml.Event.EventData.Data) {{ $h[$d.Name] = $d.'#text' }} }}
            $out.Events41 += [PSCustomObject]$h
        }}
    }} catch {{}}
    try {{
        Get-WinEvent -FilterHashtable @{{LogName='System'; Id=6008}} -MaxEvents {lrw.CRASH_UNEXPECTED_SHUTDOWN_6008_MAX} -ErrorAction SilentlyContinue | ForEach-Object {{
            $out.Events6008 += [PSCustomObject]@{{ TimeCreated=$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss') }}
        }}
    }} catch {{}}
    $out | ConvertTo-Json -Depth 4
    """
    ok, out = run_powershell(ps_combined)
    if not ok or not (out or "").strip():
        events.sort(key=lambda e: e["time"], reverse=True)
        return events[:lrw.CRASH_EVENTS_RETURN_CAP], True

    try:
        data = json.loads(out)
        data = data or {}
        def _as_list(v):
            if v is None:
                return []
            return [v] if isinstance(v, dict) else v
        # Event 1001
        for evt in _as_list(data.get("Events1001")):
            t = evt.get("TimeCreated", "?")
            code = evt.get("BugcheckCode") or _parse_bugcheck_from_message(evt.get("Message", ""))
            events.append({
                "type": "BugCheck",
                "time": t,
                "code": code or "?",
                "code_source": "wer1001",
                "p1": evt.get("BugcheckParameter1", "0"),
                "p2": evt.get("BugcheckParameter2", "0"),
                "p3": evt.get("BugcheckParameter3", "0"),
                "p4": evt.get("BugcheckParameter4", "0"),
                "dump": evt.get("DumpFile", ""),
            })
            seen_times.add(t)
        # Event 41
        for evt in _as_list(data.get("Events41")):
            t = evt.get("TimeCreated", "?")
            explicit_bc = (evt.get("BugcheckCode") or "").strip()
            raw_code = explicit_bc or "0"
            try:
                code_int = int(str(raw_code).strip(), 10)
                code_str = f"0x{code_int:08X}" if code_int else "N/A"
            except (ValueError, TypeError):
                code_str = "N/A"
            code_source = "event41_bugcheck" if explicit_bc and code_str not in ("N/A", "0x00000000") else "event41_shutdown"
            if t not in seen_times:
                seen_times.add(t)
                note = "Unexpected shutdown (power loss or crash)."
                if code_source == "event41_bugcheck":
                    note = (
                        "Unexpected shutdown (Event 41 bugcheck field present — "
                        "not verified without WER BugCheck or matching minidump)."
                    )
                events.append({
                    "type": "KernelPower",
                    "time": t,
                    "code": code_str,
                    "code_source": code_source,
                    "p1": evt.get("BugcheckParameter1", evt.get("Parameter2", "0")),
                    "p2": evt.get("BugcheckParameter2", evt.get("Parameter3", "0")),
                    "p3": evt.get("BugcheckParameter3", evt.get("Parameter4", "0")),
                    "p4": evt.get("BugcheckParameter4", evt.get("Parameter5", "0")),
                    "dump": "",
                    "note": note,
                })
        # Event 6008
        for evt in _as_list(data.get("Events6008")):
            t = evt.get("TimeCreated", "?")
            if t not in seen_times:
                seen_times.add(t)
                events.append({
                    "type": "UnexpectedShutdown",
                    "time": t,
                    "code": "N/A",
                    "code_source": "6008",
                    "p1": "0", "p2": "0", "p3": "0", "p4": "0",
                    "dump": "",
                    "note": "System did not shut down cleanly.",
                })
    except (json.JSONDecodeError, TypeError, KeyError):
        return [], True

    events.sort(key=lambda e: e["time"], reverse=True)
    return events[:lrw.CRASH_EVENTS_RETURN_CAP], False


def _parse_event_time(time_str: str) -> datetime | None:
    """Best-effort parse for event log TimeCreated strings.

    Every query in this module renders TimeCreated with `ToString('yyyy-MM-dd HH:mm:ss')`,
    which .NET emits in **local** time. A string with no offset is therefore local, not
    UTC — tagging it UTC shifted every timestamp by the machine's offset.
    """
    s = (time_str or "").strip()
    if not s or s == "?":
        return None
    m = re.search(r"/Date\((\d+)", s)
    if m:
        try:
            return datetime.fromtimestamp(int(m.group(1)) / 1000.0, tz=timezone.utc)
        except (ValueError, OSError):
            pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(s[:26], fmt)
            return dt.astimezone() if dt.tzinfo is None else dt
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone() if dt.tzinfo is None else dt
    except ValueError:
        return None


def compute_crash_timeline(events: list | None) -> dict:
    """
    Count BSOD-related events in the last 7 / 30 days from event-log rows.
    No background service — uses data already collected during Run Analysis.
    """
    now = datetime.now(timezone.utc)
    cut7 = now - timedelta(days=7)
    cut30 = now - timedelta(days=30)
    crash_types = frozenset({"BugCheck", "KernelPower", "UnexpectedShutdown"})
    times: list[datetime] = []
    for e in events or []:
        if (e.get("type") or "") not in crash_types:
            continue
        dt = _parse_event_time(e.get("time", ""))
        if dt:
            times.append(dt)
    times.sort(reverse=True)
    c7 = sum(1 for t in times if t >= cut7)
    c30 = sum(1 for t in times if t >= cut30)
    last_clean_hint = ""
    if not times:
        last_clean_hint = "No crash events found in the recent log window."
    elif c7 == 0:
        last_clean_hint = "No BSODs or unexpected shutdowns in the last 7 days."
    elif c30 == 0:
        last_clean_hint = "No BSODs in the last 30 days (but some activity in the last week)."
    # Local time, matching the clock the user reads their own crash against.
    last_crash = times[0].astimezone().strftime("%Y-%m-%d %H:%M") if times else ""
    return {
        "count_7d": c7,
        "count_30d": c30,
        "total_in_window": len(times),
        "last_crash": last_crash,
        "last_clean_hint": last_clean_hint,
    }


def query_whea_hardware_errors() -> list:
    """Query WHEA-Logger Event 18 (fatal hardware error) for component details."""
    events = []
    ps = r"""
    Get-WinEvent -FilterHashtable @{
        LogName='System'
        ProviderName='Microsoft-Windows-WHEA-Logger'
        Id=18
    } -MaxEvents 15 -ErrorAction SilentlyContinue | ForEach-Object {
        [PSCustomObject]@{
            TimeCreated = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
            Message = $_.Message
        }
    } | ConvertTo-Json
    """
    ok, out = run_powershell(ps)
    if ok and out:
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            for evt in data:
                msg = evt.get("Message", "")
                component = None
                if "Component:" in msg:
                    m = re.search(r"Component:\s*([^\r\n]+)", msg)
                    if m:
                        component = m.group(1).strip()
                events.append({
                    "time": evt.get("TimeCreated", "?"),
                    "message": msg[:300] if msg else "",
                    "component": component,
                })
        except json.JSONDecodeError:
            pass
    return events


def query_application_crashes() -> list:
    """Query Application log for Event 1000 (Application Error / crash)."""
    events = []
    ps = r"""
    Get-WinEvent -FilterHashtable @{
        LogName='Application'
        ProviderName='Application Error'
        Id=1000
    } -MaxEvents 30 -ErrorAction SilentlyContinue | ForEach-Object {
        $xml = [xml]$_.ToXml()
        $hash = @{ TimeCreated=$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss') }
        $data = $xml.Event.EventData.Data
        if ($data) { foreach ($d in $data) { $hash[$d.Name] = $d.'#text' } }
        [PSCustomObject]$hash
    } | ConvertTo-Json
    """
    ok, out = run_powershell(ps)
    if ok and out:
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            for evt in data:
                # Event 1000 XML can use "ApplicationName", "FaultingApplicationName", or "Faulting application name"
                app = (
                    evt.get("ApplicationName")
                    or evt.get("FaultingApplicationName")
                    or evt.get("Faulting application name")
                    or evt.get("Application")
                    or "?"
                )
                mod = (
                    evt.get("ModuleName")
                    or evt.get("FaultingModule")
                    or evt.get("Faulting module name")
                    or evt.get("Module")
                    or ""
                )
                exc = evt.get("ExceptionCode") or evt.get("Exception") or ""
                events.append({
                    "time": evt.get("TimeCreated", "?"),
                    "application": app.strip() if isinstance(app, str) else str(app),
                    "version": evt.get("ApplicationVersion", ""),
                    "module": mod.strip() if isinstance(mod, str) else str(mod),
                    "exception_code": exc,
                })
        except json.JSONDecodeError:
            pass
    return events


def query_thermal_events() -> list:
    """Query thermal events (throttling, etc.) near crash times."""
    events = []
    ps = r"""
    Get-WinEvent -LogName 'Microsoft-Windows-Kernel-Power/Thermal-Operational' -MaxEvents 20 -ErrorAction SilentlyContinue | ForEach-Object {
        [PSCustomObject]@{
            TimeCreated = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
            Id = $_.Id
            Message = $_.Message
        }
    } | ConvertTo-Json
    """
    ok, out = run_powershell(ps)
    if ok and out:
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            for evt in data:
                events.append({
                    "time": evt.get("TimeCreated", "?"),
                    "id": evt.get("Id"),
                    "message": (evt.get("Message") or "")[:200],
                })
        except json.JSONDecodeError:
            pass
    return events


def query_boot_recovery_events() -> tuple[list, bool]:
    """Boot failure / recovery / kernel boot status (cold-boot and repair-mode signals).

    Returns (events, query_failed).
    """
    events: list[dict] = []
    ps = r"""
    $ErrorActionPreference = 'SilentlyContinue'
    function Trim-Msg($m) {
        if (-not $m) { return '' }
        $t = ($m -replace '\s+',' ').Trim()
        if ($t.Length -gt 320) { $t = $t.Substring(0,320) }
        return $t
    }
    $out = @{ StartupRepair=@(); KernelBoot=@(); Wininit=@() }
    foreach ($log in @('Microsoft-Windows-StartupRepair/Operational','Microsoft-Windows-StartupRepair/Admin')) {
        try {
            Get-WinEvent -LogName $log -MaxEvents 20 -EA Stop | ForEach-Object {
                $out.StartupRepair += [PSCustomObject]@{
                    TimeCreated = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                    Id = $_.Id
                    Provider = $_.ProviderName
                    Message = (Trim-Msg $_.Message)
                }
            }
        } catch {}
    }
    try {
        Get-WinEvent -FilterHashtable @{
            LogName = 'System'
            ProviderName = 'Microsoft-Windows-Kernel-Boot'
        } -MaxEvents 30 -EA Stop | ForEach-Object {
            if ($_.Id -in 20,21,22,23,24,25,26,27,28,29,30,32,38,39) {
                $out.KernelBoot += [PSCustomObject]@{
                    TimeCreated = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                    Id = $_.Id
                    Provider = $_.ProviderName
                    Message = (Trim-Msg $_.Message)
                }
            }
        }
    } catch {}
    try {
        Get-WinEvent -FilterHashtable @{
            LogName = 'System'
            ProviderName = 'Microsoft-Windows-Wininit'
        } -MaxEvents 25 -EA Stop | ForEach-Object {
            $msg = (Trim-Msg $_.Message)
            if ($msg -match 'recovery|repair|failed boot|boot failure|startup repair|could not load|crash dump') {
                $out.Wininit += [PSCustomObject]@{
                    TimeCreated = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                    Id = $_.Id
                    Provider = $_.ProviderName
                    Message = $msg
                }
            }
        }
    } catch {}
    $out | ConvertTo-Json -Depth 5
    """
    ok, out = run_powershell(ps)
    if not ok or not (out or "").strip():
        return events, True
    try:
        data = json.loads(out) or {}

        def _as_list(v):
            if v is None:
                return []
            return [v] if isinstance(v, dict) else v

        for evt in _as_list(data.get("StartupRepair")):
            events.append({
                "type": "BootRecovery",
                "subtype": "StartupRepair",
                "time": evt.get("TimeCreated", "?"),
                "id": evt.get("Id"),
                "message": evt.get("Message", ""),
                "note": "Windows Startup Repair / Automatic Repair activity.",
            })
        for evt in _as_list(data.get("KernelBoot")):
            msg = evt.get("Message", "") or ""
            note = "Kernel boot phase event."
            low = msg.lower()
            if any(x in low for x in ("failed", "error", "critical", "bugcheck", "crash")):
                note = "Kernel boot reported failure or bugcheck during startup."
            events.append({
                "type": "BootRecovery",
                "subtype": "KernelBoot",
                "time": evt.get("TimeCreated", "?"),
                "id": evt.get("Id"),
                "message": msg,
                "note": note,
            })
        for evt in _as_list(data.get("Wininit")):
            events.append({
                "type": "BootRecovery",
                "subtype": "Wininit",
                "time": evt.get("TimeCreated", "?"),
                "id": evt.get("Id"),
                "message": evt.get("Message", ""),
                "note": "Wininit reported recovery or boot failure.",
            })
    except (json.JSONDecodeError, TypeError, KeyError):
        return [], True
    events.sort(key=lambda e: e.get("time", ""), reverse=True)
    return events[:20], False


def query_reliability_livekernel_bundle() -> dict:
    """On-demand Reliability Monitor–adjacent data: Live Kernel events, WER, stability index.

    Single PowerShell pass; no background service. Used during Run Analysis only.
    """
    empty: dict = {"livekernel": [], "wer_errors": [], "stability_index": None}
    ps = r"""
    $ErrorActionPreference = 'SilentlyContinue'
    function Trim-Msg($m) {
        if (-not $m) { return '' }
        $t = ($m -replace '\s+',' ').Trim()
        if ($t.Length -gt 300) { $t = $t.Substring(0,300) }
        return $t
    }
    $lk = [System.Collections.Generic.List[object]]::new()
    foreach ($log in @('Microsoft-Windows-LiveKernelEvent/Operational','Microsoft-Windows-LiveKernelEvent/Admin')) {
        try {
            Get-WinEvent -LogName $log -MaxEvents 25 -EA Stop | ForEach-Object {
                $lk.Add([PSCustomObject]@{
                    Kind = 'livekernel'
                    TimeCreated = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                    Id = $_.Id
                    Provider = $_.ProviderName
                    Message = (Trim-Msg $_.Message)
                })
            }
        } catch {}
    }
    if ($lk.Count -eq 0) {
        Get-WinEvent -FilterHashtable @{
            LogName = 'System'
            ProviderName = 'Microsoft-Windows-LiveKernelEvent'
        } -MaxEvents 25 -EA 0 | ForEach-Object {
            $lk.Add([PSCustomObject]@{
                Kind = 'livekernel'
                TimeCreated = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                Id = $_.Id
                Provider = $_.ProviderName
                Message = (Trim-Msg $_.Message)
            })
        }
    }
    $wer = [System.Collections.Generic.List[object]]::new()
    Get-WinEvent -FilterHashtable @{
        LogName = 'System'
        ProviderName = 'Microsoft-Windows-WER-SystemErrorReporting'
    } -MaxEvents 20 -EA 0 | ForEach-Object {
        $wer.Add([PSCustomObject]@{
            Kind = 'wer'
            TimeCreated = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
            Id = $_.Id
            Provider = $_.ProviderName
            Message = (Trim-Msg $_.Message)
        })
    }
    $stab = $null
    try {
        $m = Get-CimInstance -Namespace root/cimv2 -ClassName Win32_ReliabilityStabilityMetrics -EA Stop |
            Sort-Object TimeGenerated -Descending | Select-Object -First 1
        if ($m -and $null -ne $m.SystemStabilityIndex) {
            $stab = [double]$m.SystemStabilityIndex
        }
    } catch {}
    [PSCustomObject]@{
        LiveKernel = @($lk)
        Wer = @($wer)
        StabilityIndex = $stab
    } | ConvertTo-Json -Depth 5
    """
    ok, out = run_powershell(ps)
    if not ok or not out:
        return {**empty, "_query_failed": True}
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {**empty, "_query_failed": True}
    if not isinstance(data, dict):
        return empty

    # Lazy: the report layer imports this module, so a top-level import would invert.
    from crash_report_narrative import _summarize_livekernel_message

    livekernel = []
    lk_raw = data.get("LiveKernel") or data.get("livekernel") or []
    if isinstance(lk_raw, dict):
        lk_raw = [lk_raw]
    for evt in lk_raw:
        if not isinstance(evt, dict):
            continue
        msg = (evt.get("Message") or "").strip()
        livekernel.append({
            "time": evt.get("TimeCreated", "?"),
            "id": evt.get("Id"),
            "provider": evt.get("Provider", "Microsoft-Windows-LiveKernelEvent"),
            "message": msg,
            "summary": _summarize_livekernel_message(msg, evt.get("Id")),
        })

    wer_errors = []
    wer_raw = data.get("Wer") or data.get("wer_errors") or []
    if isinstance(wer_raw, dict):
        wer_raw = [wer_raw]
    for evt in wer_raw:
        if not isinstance(evt, dict):
            continue
        wer_errors.append({
            "time": evt.get("TimeCreated", "?"),
            "id": evt.get("Id"),
            "message": (evt.get("Message") or "")[:300],
        })

    stab = data.get("StabilityIndex") if data.get("StabilityIndex") is not None else data.get("stability_index")
    stability_index = None
    if stab is not None:
        try:
            stability_index = round(float(stab), 2)
        except (TypeError, ValueError):
            pass

    return {
        "livekernel": livekernel,
        "wer_errors": wer_errors,
        "stability_index": stability_index,
    }

