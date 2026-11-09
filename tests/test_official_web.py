"""Stage 13A consent, component, and auxiliary-process tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.config import AppConfig, load_config, save_config
from ai_quiz_overlay.services.official_web import (
    OFFICIAL_LOGIN_RISK_ITEMS,
    OFFICIAL_LOGIN_RISK_VERSION,
    OFFICIAL_LOGIN_TERMS_READ_DATE,
    consent_is_current,
    official_web_ready,
    runtime_access_method,
    startup_access_config,
)
from ai_quiz_overlay.services.official_web_component import (
    COMPONENT_MANIFEST_NAME,
    ComponentImportError,
    component_status,
    import_component,
    manifest_bytes_for_files,
)
from ai_quiz_overlay.services.official_web_component import ComponentStatus
from ai_quiz_overlay.services.official_web_process import (
    OfficialWebProcessManager,
)
from ai_quiz_overlay.ui.official_web_dialog import OfficialWebRiskDialog


class OfficialWebRiskTests(unittest.TestCase):
    def test_full_disclaimer_contains_required_boundaries(self) -> None:
        text = (Path(__file__).resolve().parents[1] / "DISCLAIMER.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("软件作者和贡献者不对相关损失负责", text)
        self.assertIn("不包含对 DeepSeek 服务的任何授权或许可", text)
        self.assertIn("不是法律意见", text)
        self.assertIn("不用于商业", text)

    def test_risk_text_has_eight_reviewed_items(self) -> None:
        self.assertEqual(OFFICIAL_LOGIN_RISK_VERSION, 1)
        self.assertEqual(OFFICIAL_LOGIN_TERMS_READ_DATE, "2026-11-08")
        self.assertEqual(len(OFFICIAL_LOGIN_RISK_ITEMS), 8)
        text = "\n".join(
            item.title + "\n" + item.body
            for item in OFFICIAL_LOGIN_RISK_ITEMS
        )
        self.assertIn("可能随时被调整或移除", text)
        self.assertIn("不是法律意见", text)
        self.assertIn("第 3.5 条第（3）项", text)
        self.assertIn("第 8.1 条", text)

    def test_consent_requires_matching_version_and_read_date(self) -> None:
        valid = AppConfig(
            official_login_consent_version=OFFICIAL_LOGIN_RISK_VERSION,
            official_login_terms_read_date=OFFICIAL_LOGIN_TERMS_READ_DATE,
            official_login_consent_at="2026-11-08T10:00:00+08:00",
        )
        self.assertTrue(consent_is_current(valid))
        self.assertFalse(
            consent_is_current(
                AppConfig(
                    official_login_consent_version=0,
                    official_login_terms_read_date=(
                        OFFICIAL_LOGIN_TERMS_READ_DATE
                    ),
                )
            )
        )
        self.assertFalse(
            consent_is_current(
                AppConfig(
                    official_login_consent_version=(
                        OFFICIAL_LOGIN_RISK_VERSION
                    ),
                    official_login_terms_read_date="2025-01-01",
                )
            )
        )

    def test_stale_official_access_falls_back_to_api(self) -> None:
        config = AppConfig(access_method="official_login")
        self.assertEqual(runtime_access_method(config), "api")
        self.assertIsNotNone(runtime_access_method(config, with_reason=True))

    def test_official_component_cannot_start_without_consent(self) -> None:
        self.assertFalse(official_web_ready(AppConfig(), True)[0])
        granted = AppConfig(
            official_login_consent_version=OFFICIAL_LOGIN_RISK_VERSION,
            official_login_terms_read_date=OFFICIAL_LOGIN_TERMS_READ_DATE,
            official_login_consent_at="2026-11-08T10:00:00+08:00",
        )
        self.assertTrue(official_web_ready(granted, True)[0])
        self.assertFalse(official_web_ready(granted, False)[0])

    def test_manual_official_config_without_consent_falls_back(self) -> None:
        config = AppConfig(access_method="official_login")
        updated, reason = startup_access_config(
            config,
            component_installed=True,
        )
        self.assertEqual(updated.access_method, "api")
        self.assertEqual(updated.official_login_consent_version, 0)
        self.assertIn("同意", reason)

    def test_api_modules_do_not_import_qtwebengine(self) -> None:
        self.assertNotIn("PySide6.QtWebEngineCore", sys.modules)
        self.assertNotIn("PySide6.QtWebEngineWidgets", sys.modules)

    def test_consent_fields_round_trip_with_unknown_keys_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_config(
                AppConfig(
                    official_login_consent_version=(
                        OFFICIAL_LOGIN_RISK_VERSION
                    ),
                    official_login_terms_read_date=(
                        OFFICIAL_LOGIN_TERMS_READ_DATE
                    ),
                    official_login_consent_at="2026-11-08T10:00:00+08:00",
                ),
                path,
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            data["future_field"] = {"keep": True}
            path.write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8",
            )
            loaded = load_config(path)
            self.assertEqual(
                loaded.official_login_consent_version,
                OFFICIAL_LOGIN_RISK_VERSION,
            )
            self.assertEqual(
                loaded.official_login_terms_read_date,
                OFFICIAL_LOGIN_TERMS_READ_DATE,
            )
            save_config(loaded, path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["future_field"], {"keep": True})


class OfficialWebComponentTests(unittest.TestCase):
    APP_VERSION = "13a"
    COMPONENT_VERSION = "13a-1"

    def _component_folder(self, root: Path) -> tuple[Path, str]:
        payload = root / "official-web-host.exe"
        payload.write_bytes(b"fake-host")
        internal = root / "_internal" / "qt.conf"
        internal.parent.mkdir(parents=True)
        internal.write_text("fake", encoding="utf-8")
        manifest = manifest_bytes_for_files(
            root,
            component_version=self.COMPONENT_VERSION,
            app_version=self.APP_VERSION,
            entrypoint="official-web-host.exe",
        )
        (root / COMPONENT_MANIFEST_NAME).write_bytes(manifest)
        return root, hashlib.sha256(manifest).hexdigest()

    def test_folder_import_verifies_and_installs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            root, manifest_hash = self._component_folder(root)
            install_root = Path(directory) / "installed"
            checked: list[Path] = []
            installed = import_component(
                root,
                install_root=install_root,
                expected_manifest_sha256=manifest_hash,
                expected_app_version=self.APP_VERSION,
                expected_component_version=self.COMPONENT_VERSION,
                self_check=lambda path: checked.append(path),
            )
            self.assertEqual(installed.version, self.COMPONENT_VERSION)
            self.assertEqual(
                [path.name for path in checked],
                [installed.entrypoint.name],
            )
            self.assertTrue(installed.entrypoint.is_file())
            self.assertTrue(
                component_status(
                    install_root,
                    expected_app_version=self.APP_VERSION,
                    expected_component_version=self.COMPONENT_VERSION,
                    expected_manifest_sha256=manifest_hash,
                ).installed
            )

    def test_import_can_replace_previous_owned_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            install_root = Path(directory) / "installed"
            first = Path(directory) / "first"
            first.mkdir()
            first, first_hash = self._component_folder(first)
            import_component(
                first,
                install_root=install_root,
                expected_manifest_sha256=first_hash,
                expected_app_version=self.APP_VERSION,
                expected_component_version=self.COMPONENT_VERSION,
                self_check=lambda _path: None,
            )

            second = Path(directory) / "second"
            second.mkdir()
            (second / "official-web-host.exe").write_bytes(b"new-host")
            internal = second / "_internal" / "qt.conf"
            internal.parent.mkdir(parents=True)
            internal.write_text("new", encoding="utf-8")
            manifest = manifest_bytes_for_files(
                second,
                component_version=self.COMPONENT_VERSION,
                app_version=self.APP_VERSION,
                entrypoint="official-web-host.exe",
            )
            (second / COMPONENT_MANIFEST_NAME).write_bytes(manifest)
            second_hash = hashlib.sha256(manifest).hexdigest()
            imported = import_component(
                second,
                install_root=install_root,
                expected_manifest_sha256=second_hash,
                expected_app_version=self.APP_VERSION,
                expected_component_version=self.COMPONENT_VERSION,
                self_check=lambda _path: None,
            )
            self.assertEqual(
                imported.entrypoint.read_bytes(),
                b"new-host",
            )

    def test_component_rejects_version_hash_and_extra_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            root, manifest_hash = self._component_folder(root)
            (root / "unexpected.bin").write_bytes(b"extra")
            with self.assertRaises(ComponentImportError):
                import_component(
                    root,
                    install_root=Path(directory) / "extra",
                    expected_manifest_sha256=manifest_hash,
                    expected_app_version=self.APP_VERSION,
                    expected_component_version=self.COMPONENT_VERSION,
                    self_check=lambda _path: None,
                )
            with self.assertRaises(ComponentImportError):
                import_component(
                    root,
                    install_root=Path(directory) / "wrong-version",
                    expected_manifest_sha256=manifest_hash,
                    expected_app_version=self.APP_VERSION,
                    expected_component_version="other",
                    self_check=lambda _path: None,
                )
            with self.assertRaises(ComponentImportError):
                import_component(
                    root,
                    install_root=Path(directory) / "wrong-hash",
                    expected_manifest_sha256="0" * 64,
                    expected_app_version=self.APP_VERSION,
                    expected_component_version=self.COMPONENT_VERSION,
                    self_check=lambda _path: None,
                )

    def test_zip_rejects_traversal_symlink_and_extra_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            zip_path = Path(directory) / "bad.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("../escape.txt", "bad")
            with self.assertRaises(ComponentImportError):
                import_component(
                    zip_path,
                    install_root=Path(directory) / "traversal",
                    expected_manifest_sha256="0" * 64,
                    expected_app_version=self.APP_VERSION,
                    expected_component_version=self.COMPONENT_VERSION,
                    self_check=lambda _path: None,
                )

    def test_folder_rejects_oversized_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "official-web-host.exe").write_bytes(b"12345")
            with patch(
                "ai_quiz_overlay.services.official_web_component."
                "MAX_COMPONENT_FILE_BYTES",
                4,
            ):
                with self.assertRaises(ComponentImportError):
                    manifest_bytes_for_files(
                        root,
                        component_version=self.COMPONENT_VERSION,
                        app_version=self.APP_VERSION,
                        entrypoint="official-web-host.exe",
                    )

    def test_zip_rejects_symlink_and_extra_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            symlink_path = Path(directory) / "symlink.zip"
            with zipfile.ZipFile(symlink_path, "w") as archive:
                info = zipfile.ZipInfo("link")
                info.external_attr = (0o120777 << 16)
                archive.writestr(info, "target")
            with self.assertRaises(ComponentImportError):
                import_component(
                    symlink_path,
                    install_root=Path(directory) / "symlink",
                    expected_manifest_sha256="0" * 64,
                    expected_app_version=self.APP_VERSION,
                    expected_component_version=self.COMPONENT_VERSION,
                    self_check=lambda _path: None,
                )

            root = Path(directory) / "extra-source"
            root.mkdir()
            root, manifest_hash = self._component_folder(root)
            extra_zip = Path(directory) / "extra.zip"
            with zipfile.ZipFile(extra_zip, "w") as archive:
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(root).as_posix())
                archive.writestr("extra-file.bin", "not in manifest")
            with self.assertRaises(ComponentImportError):
                import_component(
                    extra_zip,
                    install_root=Path(directory) / "extra-install",
                    expected_manifest_sha256=manifest_hash,
                    expected_app_version=self.APP_VERSION,
                    expected_component_version=self.COMPONENT_VERSION,
                    self_check=lambda _path: None,
                )


class OfficialWebRiskDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_unlock_requires_timer_scroll_checks_and_typed_phrase(self) -> None:
        clock = {"now": 100.0, "active": True}
        dialog = OfficialWebRiskDialog(
            clock=lambda: clock["now"],
            activity_probe=lambda: clock["active"],
        )
        dialog.resize(620, 520)
        dialog.show()
        self.app.processEvents()
        self.assertFalse(dialog.accept_button.isEnabled())
        for checkbox in dialog.risk_checkboxes:
            checkbox.setChecked(True)
        dialog.confirm_edit.setText("我已阅读并接受风险")
        dialog.scroll_area.verticalScrollBar().setValue(
            dialog.scroll_area.verticalScrollBar().maximum()
        )
        self.assertFalse(dialog.accept_button.isEnabled())
        clock["now"] += 31
        dialog._tick()
        self.assertTrue(dialog.accept_button.isEnabled())
        dialog.reject()


class _SignalStub:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _FakeProcess:
    def __init__(self) -> None:
        self.readyReadStandardOutput = _SignalStub()
        self.started = _SignalStub()
        self.finished = _SignalStub()
        self.errorOccurred = _SignalStub()
        self.program = ""
        self.arguments = []
        self.started_flag = False
        self.terminated = False

    def setProgram(self, value: str) -> None:
        self.program = value

    def setArguments(self, values) -> None:
        self.arguments = list(values)

    def setProcessChannelMode(self, _mode) -> None:
        pass

    def start(self) -> None:
        self.started_flag = True

    def readAllStandardOutput(self) -> bytes:
        return b""

    def write(self, data: bytes) -> int:
        self.written = getattr(self, "written", b"") + data
        return len(data)

    def waitForBytesWritten(self, _timeout: int) -> bool:
        return True

    def terminate(self) -> None:
        self.terminated = True

    def waitForFinished(self, _timeout: int) -> bool:
        return True

    def kill(self) -> None:
        pass

    def deleteLater(self) -> None:
        pass


class OfficialWebProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_manager_starts_and_terminates_without_loading_webengine(self) -> None:
        process = _FakeProcess()
        manager = OfficialWebProcessManager(
            process_factory=lambda: process,
        )
        status = ComponentStatus(
            True,
            "ready",
            "13a-1",
            Path("C:/component/official-web-host.exe"),
            "hash",
        )
        self.assertTrue(
            manager.start(
                status,
                session_dir=Path(tempfile.mkdtemp()),
            )
        )
        self.assertTrue(manager.is_running)
        self.assertTrue(process.started_flag)
        self.assertEqual(
            process.arguments,
            ["--profile-dir", str(manager._session_dir)],
        )
        manager.stop()
        self.assertFalse(manager.is_running)
        self.assertTrue(process.terminated)

    def test_browser_host_arguments_and_visibility_commands(self) -> None:
        process = _FakeProcess()
        manager = OfficialWebProcessManager(
            process_factory=lambda: process,
        )
        status = ComponentStatus(
            True,
            "ready",
            "13a-1",
            Path("C:/component/official-web-host.exe"),
            "hash",
        )
        self.assertTrue(
            manager.start(
                status,
                session_dir=Path(tempfile.mkdtemp()),
                browser_mode=True,
                interface_name="测试界面",
                logo_path="C:/logo.png",
                opacity=0.42,
            )
        )
        self.assertIn("--browser-mode", process.arguments)
        self.assertIn("测试界面", process.arguments)
        self.assertIn("C:/logo.png", process.arguments)
        self.assertIn("0.420", process.arguments)
        manager.show()
        manager.hide()
        manager.set_window_opacity(0.75)
        manager.set_voice_state("listening")
        payloads = process.written.decode("utf-8").splitlines()
        self.assertIn('"command": "show"', payloads[0])
        self.assertIn('"command": "hide"', payloads[1])
        self.assertIn('"command": "set_opacity"', payloads[2])
        self.assertIn('"command": "set_voice_state"', payloads[3])
        manager.stop()

    def test_countdown_pauses_when_window_is_not_active(self) -> None:
        clock = {"now": 10.0, "active": True}
        dialog = OfficialWebRiskDialog(
            clock=lambda: clock["now"],
            activity_probe=lambda: clock["active"],
        )
        dialog._tick()
        clock["now"] += 5
        dialog._tick()
        remaining = dialog.remaining_seconds
        clock["active"] = False
        clock["now"] += 20
        dialog._tick()
        self.assertEqual(dialog.remaining_seconds, remaining)
        dialog.reject()

    def test_confirm_field_rejects_programmatic_paste(self) -> None:
        dialog = OfficialWebRiskDialog()
        dialog.confirm_edit.setText("")
        dialog.confirm_edit.paste()
        self.assertEqual(dialog.confirm_edit.text(), "")
        dialog.reject()

    def test_escape_cancels_gate_even_when_locked(self) -> None:
        dialog = OfficialWebRiskDialog(
            clock=lambda: 1.0,
            activity_probe=lambda: True,
        )
        dialog.show()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertEqual(dialog.result(), dialog.DialogCode.Rejected)
