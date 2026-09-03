"""Status-line helpers for driver and firmware catalog workers."""


def catalog_status_message(
    detail: str,
    *,
    drv_running: bool,
    fw_running: bool,
) -> str:
    """Prefix status text for the active catalog worker.

    Driver and firmware Search are mutually exclusive in the GUI — only one worker
    runs at a time. If both flags are set (should not happen), avoid stale
    "parallel" wording and describe both searches plainly.
    """
    text = (detail or "").strip()
    if not text:
        return ""
    if drv_running and fw_running:
        if text.lower().startswith(("driver", "firmware")):
            return text
        return f"Driver and firmware searches: {text}"
    if drv_running and not text.lower().startswith("driver"):
        return f"Driver update search: {text}"
    if fw_running and not text.lower().startswith("firmware"):
        return f"Firmware update search: {text}"
    return text
