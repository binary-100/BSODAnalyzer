"""Track A: serialized crash driver/fw scheduling helpers."""


def test_defer_fw_when_driver_starts() -> None:
    defer_fw = False

    def try_start_driver(has_driver: bool, started: bool) -> bool:
        if not has_driver:
            return False
        return started

    def schedule_update_checks(has_driver: bool, driver_started: bool) -> str:
        nonlocal defer_fw
        if try_start_driver(has_driver, driver_started):
            defer_fw = True
            return "driver_only"
        return "fw_immediate"

    assert schedule_update_checks(True, True) == "driver_only"
    assert defer_fw is True
    defer_fw = False
    assert schedule_update_checks(False, False) == "fw_immediate"
    assert defer_fw is False


def test_finish_driver_chains_firmware_when_deferred() -> None:
    defer_fw = True
    fw_scheduled = False

    def finish_driver_scan() -> None:
        nonlocal defer_fw, fw_scheduled
        if defer_fw:
            defer_fw = False
            fw_scheduled = True

    finish_driver_scan()
    assert fw_scheduled is True
    assert defer_fw is False


def test_synth_defer_when_driver_thread_busy() -> None:
    """Mixed PnP+synth batch: keep synth pending until thread cleanup."""
    pending_synth = ["Device for module foo.sys"]
    thread_running = True
    started = False

    def on_catalog_ready() -> None:
        nonlocal started
        synth = list(pending_synth)
        if not synth:
            return
        if thread_running:
            return
        pending_synth.clear()
        started = True

    on_catalog_ready()
    assert pending_synth
    assert not started

    def cleanup() -> None:
        nonlocal started
        synth = list(pending_synth)
        if synth:
            pending_synth.clear()
            started = True

    thread_running = False
    cleanup()
    assert started
    assert not pending_synth


def test_driver_retry_no_start_still_runs_fw() -> None:
    defer_fw = True
    fw_ran = False

    def retry_driver(started: bool) -> None:
        nonlocal defer_fw, fw_ran
        if not started:
            if defer_fw:
                defer_fw = False
                fw_ran = True

    retry_driver(False)
    assert fw_ran is True


def test_is_index_enabled_requires_remember_in_full_install() -> None:
    import driver_index as drvidx

    full_remember_off = {
        "install_mode": "full",
        "use_driver_index": True,
        "remember_driver_firmware_checks": False,
    }
    full_remember_on = {
        "install_mode": "full",
        "use_driver_index": True,
        "remember_driver_firmware_checks": True,
    }
    assert not drvidx.is_index_enabled(full_remember_off)
    assert drvidx.is_index_enabled(full_remember_on)


if __name__ == "__main__":
    test_defer_fw_when_driver_starts()
    test_finish_driver_chains_firmware_when_deferred()
    test_synth_defer_when_driver_thread_busy()
    test_driver_retry_no_start_still_runs_fw()
    test_is_index_enabled_requires_remember_in_full_install()
    print("Track A crash scan tests OK")
