"""Custom data dir and OneDrive detection for full-install mode."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import app_settings as app_set


def test_default_full_install_data_dir_not_onedrive() -> None:
    path = app_set.default_full_install_data_dir()
    assert "BSODAnalyzer" in str(path)
    assert not app_set.is_onedrive_synced_path(path)


def test_is_onedrive_synced_path_detects_onedrive_segment() -> None:
    assert app_set.is_onedrive_synced_path(
        Path("C:/Users/me/OneDrive/Documents/BSODAnalyzer")
    )
    assert not app_set.is_onedrive_synced_path(
        Path("C:/Users/me/AppData/Local/BSODAnalyzer")
    )
    assert not app_set.is_onedrive_synced_path(
        Path("D:/Archive/onedrive-backups/BSODAnalyzer")
    )


def test_custom_data_dir_override() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        custom = Path(tmp) / "data"
        settings = dict(app_set.DEFAULT_SETTINGS)
        settings["install_mode"] = "full"
        settings["custom_data_dir"] = str(custom)
        assert app_set.full_install_data_dir(settings) == custom.resolve()


def test_normalize_custom_data_dir_empty_for_default() -> None:
    default = app_set.default_full_install_data_dir()
    assert app_set.normalize_custom_data_dir(str(default)) == ""


def test_migrate_full_install_data_moves_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "old"
        dst = Path(tmp) / "new"
        src.mkdir()
        (src / "driver_index.sqlite").write_text("x", encoding="utf-8")
        (src / "settings.json").write_text("{}", encoding="utf-8")
        ok, msg = app_set.migrate_full_install_data(src, dst)
        assert ok
        assert "Relocated" in msg
        assert (dst / "driver_index.sqlite").is_file()
        assert not (src / "driver_index.sqlite").exists()


def test_migrate_fails_when_destination_has_settings_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "old"
        dst = Path(tmp) / "new"
        src.mkdir()
        dst.mkdir()
        (src / "settings.json").write_text('{"install_mode": "full"}', encoding="utf-8")
        (src / "driver_index.sqlite").write_text("x", encoding="utf-8")
        (dst / "settings.json").write_text("{}", encoding="utf-8")
        ok, msg = app_set.migrate_full_install_data(src, dst)
        assert not ok
        assert "settings.json" in msg.lower()
        assert (src / "settings.json").is_file()
        assert not (dst / "driver_index.sqlite").exists()


def test_migrate_fails_when_nothing_moved_due_to_collisions() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "old"
        dst = Path(tmp) / "new"
        src.mkdir()
        dst.mkdir()
        (src / "driver_index.sqlite").write_text("x", encoding="utf-8")
        (dst / "driver_index.sqlite").write_text("y", encoding="utf-8")
        ok, msg = app_set.migrate_full_install_data(src, dst)
        assert not ok
        assert "already contains" in msg.lower()


def test_data_dir_pointer_resolves_cold_start() -> None:
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        default = base / "default"
        custom = base / "custom"
        custom.mkdir()
        default.mkdir()
        full_settings = {
            "version": app_set.SETTINGS_VERSION,
            "install_mode": "full",
            "install_mode_chosen": True,
            "custom_data_dir": "",
            "remember_driver_firmware_checks": True,
        }
        (custom / "settings.json").write_text(
            json.dumps(full_settings, indent=2),
            encoding="utf-8",
        )
        with patch.object(app_set, "default_full_install_data_dir", lambda: default), patch.object(
            app_set, "maintenance_data_dir", lambda: default
        ), patch.object(app_set, "portable_settings_dir", lambda: base / "portable"):
            app_set._write_data_dir_pointer(custom)
            resolved = app_set._settings_path()
            assert resolved == custom / "settings.json"
            loaded = app_set.load_settings()
            assert app_set.is_full_install_mode(loaded)


def test_onedrive_warning_when_custom_dir_under_onedrive() -> None:
    settings = {
        "install_mode": "full",
        "custom_data_dir": r"C:\Users\me\OneDrive\BSODAnalyzer",
    }
    warn = app_set.onedrive_data_dir_warning(settings)
    assert warn is not None
    assert "OneDrive" in warn


def test_data_sync_warning_legacy_stick_on_onedrive() -> None:
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmp:
        onedrive_root = Path(tmp) / "OneDrive"
        onedrive_stick = onedrive_root / "BSODAnalyzer_portable"
        onedrive_stick.mkdir(parents=True)
        (onedrive_stick / "settings.json").write_text("{}", encoding="utf-8")
        with patch.object(app_set, "portable_settings_dir", lambda: onedrive_stick), patch.object(
            app_set, "_exe_parent_dir", lambda: Path(tmp) / "BSODAnalyzer_v6"
        ):
            warn = app_set.data_sync_warning({"install_mode": "portable"})
            assert warn is not None
            assert "Legacy portable data" in warn


def test_portable_writes_pc_local_not_beside_exe() -> None:
    import os
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmp:
        exe_dir = Path(tmp) / "stick"
        exe_dir.mkdir()
        local_root = Path(tmp) / "LocalAppData" / "BSODAnalyzer"
        settings = app_set.apply_portable_defaults({})
        with patch.object(app_set, "_exe_parent_dir", return_value=exe_dir), patch.object(
            app_set, "default_full_install_data_dir", return_value=local_root
        ), patch.dict(os.environ, {"LOCALAPPDATA": str(Path(tmp) / "LocalAppData")}):
            cfg = app_set._config_dir(settings)
            assert cfg == local_root
            exports = app_set.local_export_directory()
            assert "BSODAnalyzer_portable" not in str(exports).replace("\\", "/")
            assert str(exports).startswith(str(local_root))


def test_save_settings_portable_fallback_when_pc_local_locked() -> None:
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exe_dir = tmp_path / "app"
        exe_dir.mkdir()
        local_data = tmp_path / "LocalAppData" / "BSODAnalyzer"
        data = app_set.apply_portable_defaults({"theme": "night"})
        real_atomic = app_set._atomic_write_text
        primary = local_data / "settings.json"

        def _patched_atomic(path: Path, text: str, *, retries: int = 3):
            if path.resolve() == primary.resolve():
                return False, "Permission denied"
            return real_atomic(path, text, retries=retries)

        with patch.object(app_set, "_exe_parent_dir", return_value=exe_dir), patch.object(
            app_set, "default_full_install_data_dir", return_value=local_data
        ), patch.object(app_set, "maintenance_data_dir", return_value=local_data), patch.object(
            app_set, "_atomic_write_text", side_effect=_patched_atomic
        ):
            ok = app_set.save_settings(data)
            assert ok is True
            fallback = app_set._portable_fallback_settings_path()
            assert fallback.is_file()
            assert app_set._read_portable_redirect() == fallback


def test_first_launch_install_prompt_disabled_by_default() -> None:
    assert app_set.DEFAULT_SETTINGS["prompt_install_mode_on_first_launch"] is False


def test_ensure_install_mode_silent_portable_default() -> None:
    from unittest.mock import MagicMock, patch

    import bsod_gui_preferences as gui_prefs
    import bsod_gui_qt

    fresh = dict(app_set.DEFAULT_SETTINGS)
    saved: dict = {}

    def _save(settings: dict) -> None:
        saved.clear()
        saved.update(settings)

    with patch.object(app_set, "load_settings", return_value=fresh), patch.object(
        app_set, "save_settings", side_effect=_save
    ), patch.object(
        gui_prefs, "InstallModeChoiceDialog", MagicMock()
    ) as mock_dlg:
        bsod_gui_qt._ensure_install_mode_chosen()
        mock_dlg.assert_not_called()
        assert saved.get("install_mode") == "portable"
        assert saved.get("install_mode_chosen") is True


def test_ensure_install_mode_shows_dialog_when_prompt_enabled() -> None:
    from unittest.mock import MagicMock, patch

    from PySide6 import QtWidgets

    import bsod_gui_preferences as gui_prefs
    import bsod_gui_qt

    fresh = dict(app_set.DEFAULT_SETTINGS)
    fresh["prompt_install_mode_on_first_launch"] = True
    saved: dict = {}

    def _save(settings: dict) -> None:
        saved.clear()
        saved.update(settings)

    mock_dlg = MagicMock()
    mock_dlg.exec.return_value = QtWidgets.QDialog.DialogCode.Accepted
    mock_dlg.choice_is_full.return_value = False

    with patch.object(app_set, "load_settings", return_value=fresh), patch.object(
        app_set, "save_settings", side_effect=_save
    ), patch.object(gui_prefs, "InstallModeChoiceDialog", return_value=mock_dlg):
        bsod_gui_qt._ensure_install_mode_chosen()
        mock_dlg.exec.assert_called_once()
        assert saved.get("install_mode") == "portable"


def test_save_settings_portable_fallback_when_beside_exe_locked() -> None:
    """Legacy name — portable saves PC-local; fallback uses portable_redirects."""
    test_save_settings_portable_fallback_when_pc_local_locked()


def test_save_settings_does_not_raise_on_permission_error() -> None:
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exe_dir = tmp_path / "app"
        exe_dir.mkdir()
        local_data = tmp_path / "LocalAppData" / "BSODAnalyzer"
        data = app_set.apply_portable_defaults({})

        with patch.object(app_set, "_exe_parent_dir", return_value=exe_dir), patch.object(
            app_set, "default_full_install_data_dir", return_value=local_data
        ), patch.object(app_set, "_atomic_write_text", return_value=(False, "Permission denied")):
            ok = app_set.save_settings(data)
        assert ok is False
        assert app_set.peek_settings_save_error()


if __name__ == "__main__":
    test_default_full_install_data_dir_not_onedrive()
    test_is_onedrive_synced_path_detects_onedrive_segment()
    test_custom_data_dir_override()
    test_normalize_custom_data_dir_empty_for_default()
    test_migrate_full_install_data_moves_files()
    test_migrate_fails_when_destination_has_settings_json()
    test_migrate_fails_when_nothing_moved_due_to_collisions()
    test_data_dir_pointer_resolves_cold_start()
    test_onedrive_warning_when_custom_dir_under_onedrive()
    test_data_sync_warning_legacy_stick_on_onedrive()
    test_portable_writes_pc_local_not_beside_exe()
    test_first_launch_install_prompt_disabled_by_default()
    test_ensure_install_mode_silent_portable_default()
    test_ensure_install_mode_shows_dialog_when_prompt_enabled()
    test_save_settings_portable_fallback_when_beside_exe_locked()
    test_save_settings_does_not_raise_on_permission_error()
    print("Data dir settings tests OK")
