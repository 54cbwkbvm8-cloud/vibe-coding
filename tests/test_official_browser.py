"""Policy tests for the official browser-only mode."""

from __future__ import annotations

import ast
import ctypes
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLabel


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "component"))

from ai_quiz_overlay.services.browser_policy import (  # noqa: E402
    OBSERVED_PUBLIC_LOGIN_RESOURCE_HOSTS,
    PERMISSION_POLICIES,
    address_display,
    is_allowed_main_frame_url,
    main_frame_action,
    permission_is_denied,
    popup_action,
)
from ai_quiz_overlay.services.browser_clipboard import (  # noqa: E402
    BrowserClipboardGuard,
    CLOUD_FORMAT,
    EXCLUDE_FORMAT,
    HISTORY_FORMAT,
)
from ai_quiz_overlay.hotkey_definitions import (  # noqa: E402
    active_context_hotkey_keys,
)
from ai_quiz_overlay.config import AppConfig, load_config, save_config  # noqa: E402
from ai_quiz_overlay.services.official_web import (  # noqa: E402
    BROWSER_MODE_RISK_ITEMS,
    BROWSER_MODE_RISK_VERSION,
    BROWSER_MODE_TERMS_READ_DATE,
    browser_consent_is_current,
    browser_mode_ready,
    startup_access_config,
)
from ai_quiz_overlay.ui.official_web_dialog import (  # noqa: E402
    OfficialWebRiskDialog,
)
from ai_quiz_overlay.ui.settings_panel import SettingsPanel  # noqa: E402


class OfficialBrowserPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_only_deepseek_main_frames_are_internal(self) -> None:
        self.assertTrue(
            is_allowed_main_frame_url("https://chat.deepseek.com/sign_in")
        )
        self.assertTrue(
            is_allowed_main_frame_url("https://www.deepseek.com/")
        )
        self.assertFalse(
            is_allowed_main_frame_url("https://deepseek.com.evil.example/")
        )
        self.assertFalse(
            is_allowed_main_frame_url("https://appleid.apple.com/auth")
        )
        self.assertEqual(
            main_frame_action("https://appleid.apple.com/auth"),
            "external",
        )
        self.assertEqual(
            main_frame_action("https://chat.deepseek.com/sign_in"),
            "internal",
        )

    def test_address_display_drops_query_fragment_and_port(self) -> None:
        self.assertEqual(
            address_display(
                "https://chat.deepseek.com/sign_in?q=secret#fragment"
            ),
            "chat.deepseek.com/sign_in",
        )
        self.assertEqual(
            address_display("https://chat.deepseek.com"),
            "chat.deepseek.com/",
        )

    def test_all_permissions_are_denied_by_default(self) -> None:
        self.assertGreaterEqual(len(PERMISSION_POLICIES), 8)
        self.assertTrue(permission_is_denied("camera"))
        self.assertTrue(permission_is_denied("microphone"))
        self.assertTrue(permission_is_denied("clipboard-read"))
        self.assertTrue(permission_is_denied("downloads"))
        policies = {item.permission: item.behavior for item in PERMISSION_POLICIES}
        self.assertTrue(
            any("文件选择" in name for name in policies)
        )
        self.assertTrue(any("下载" in name for name in policies))

    def test_observed_login_resource_hosts_do_not_expand_navigation(self) -> None:
        self.assertIn("open.weixin.qq.com", OBSERVED_PUBLIC_LOGIN_RESOURCE_HOSTS)
        self.assertIn("appleid.cdn-apple.com", OBSERVED_PUBLIC_LOGIN_RESOURCE_HOSTS)
        for host in OBSERVED_PUBLIC_LOGIN_RESOURCE_HOSTS:
            if host == "deepseek.com" or host.endswith(".deepseek.com"):
                continue
            with self.subTest(host=host):
                self.assertFalse(
                    is_allowed_main_frame_url(f"https://{host}/login")
                )

    def test_popup_targets_use_same_whitelist(self) -> None:
        self.assertEqual(
            popup_action("https://chat.deepseek.com/chat"),
            "internal",
        )
        self.assertEqual(
            popup_action("https://open.weixin.qq.com/connect/qrconnect"),
            "external",
        )
        self.assertEqual(popup_action("file:///C:/secret.txt"), "external")

    def test_browser_mode_registers_only_browser_context_hotkeys(self) -> None:
        self.assertEqual(
            active_context_hotkey_keys("official_browser", "quiz"),
            ("chat", "screenshot", "screen_recognition"),
        )
        self.assertEqual(
            active_context_hotkey_keys(
                "official_browser",
                "global_assistant",
            ),
            ("chat", "screenshot", "screen_recognition"),
        )

    def test_browser_shell_source_has_only_navigation_exceptions(self) -> None:
        source = (
            PROJECT_ROOT / "component" / "official_web_browser_host.py"
        ).read_text(encoding="utf-8")
        forbidden = (
            "runJavaScript",
            "QWebChannel",
            "QWebEngineScript",
            "cookieStore",
            "QWebEngineUrlRequestInterceptor",
            "setUrlRequestInterceptor",
            "setHttpUserAgent",
            "setUserAgent",
            "toHtml",
            "toPlainText",
            "findText",
            "QTWEBENGINE_REMOTE_DEBUGGING",
            "remote-debugging-port",
            "--remote-debugging",
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertIn("acceptNavigationRequest", source)
        self.assertIn("createWindow", source)
        self.assertIn("QDesktopServices.openUrl", source)
        tree = ast.parse(source)
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        main_navigation = next(
            node
            for node in functions
            if node.name == "acceptNavigationRequest"
            and "main_frame_action"
            in (ast.get_source_segment(source, node) or "")
        )
        for name in ("acceptNavigationRequest", "createWindow"):
            for node in functions:
                if node.name != name:
                    continue
                snippet = ast.get_source_segment(source, node) or ""
                for token in forbidden:
                    self.assertNotIn(token, snippet)
        self.assertIn(
            "main_frame_action",
            ast.get_source_segment(source, main_navigation) or "",
        )
        self.assertIn("createWindow", source)

    def test_no_custom_remote_debugging_environment_is_set(self) -> None:
        build_source = (
            PROJECT_ROOT / "build" / "build_official_web_component.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("QTWEBENGINE_REMOTE_DEBUGGING", build_source)
        self.assertNotIn("remote-debugging-port", build_source)
        process_source = (
            PROJECT_ROOT
            / "src"
            / "ai_quiz_overlay"
            / "services"
            / "official_web_process.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("QTWEBENGINE_REMOTE_DEBUGGING", process_source)
        self.assertNotIn("--remote-debugging", process_source)

    def test_formal_component_has_no_diagnostic_entrypoint(self) -> None:
        self.assertFalse(
            (
                PROJECT_ROOT
                / "component"
                / "official_web_diagnostic_build.py"
            ).exists()
        )
        self.assertFalse(
            (
                PROJECT_ROOT
                / "component"
                / "official_web_diagnostics.py"
            ).exists()
        )
        host_source = (
            PROJECT_ROOT / "component" / "official_web_host.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("official_web_diagnostic", host_source)
        self.assertNotIn("DiagnosticResultWindow", host_source)
        self.assertNotIn("诊断", host_source)
        build_source = (
            PROJECT_ROOT / "build" / "build_official_web_component.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("official_web_diagnostic", build_source)
        self.assertNotIn("--enable-diagnostics", build_source)

    def test_clipboard_auto_clear_only_when_sequence_is_unchanged(self) -> None:
        guard = BrowserClipboardGuard(
            auto_clear_enabled=True,
            clear_seconds=60,
        )

        class FakeUser32:
            def __init__(self, sequence: int) -> None:
                self.sequence = sequence
                self.opened = 0
                self.emptied = 0
                self.closed = 0

            def GetClipboardSequenceNumber(self):
                return self.sequence

            def OpenClipboard(self, _owner):
                self.opened += 1
                return 1

            def EmptyClipboard(self):
                self.emptied += 1
                return 1

            def CloseClipboard(self):
                self.closed += 1
                return 1

        unchanged = FakeUser32(17)
        guard._sequence = 17
        with patch("sys.platform", "win32"), patch.object(
            ctypes,
            "windll",
            type("Windll", (), {"user32": unchanged})(),
            create=True,
        ):
            self.assertTrue(guard.clear_if_unchanged())
        self.assertEqual((unchanged.opened, unchanged.emptied), (1, 1))

        replaced = FakeUser32(18)
        guard._sequence = 17
        with patch("sys.platform", "win32"), patch.object(
            ctypes,
            "windll",
            type("Windll", (), {"user32": replaced})(),
            create=True,
        ):
            self.assertFalse(guard.clear_if_unchanged())
        self.assertEqual((replaced.opened, replaced.emptied), (0, 0))
        guard.deleteLater()

    def test_clipboard_format_names_match_windows_contract(self) -> None:
        self.assertEqual(
            EXCLUDE_FORMAT,
            "ExcludeClipboardContentFromMonitorProcessing",
        )
        self.assertEqual(HISTORY_FORMAT, "CanIncludeInClipboardHistory")
        self.assertEqual(CLOUD_FORMAT, "CanUploadToCloudClipboard")

    def test_browser_risk_has_nine_items_and_no_timed_confirmation(self) -> None:
        self.assertEqual(BROWSER_MODE_RISK_VERSION, 1)
        self.assertEqual(BROWSER_MODE_TERMS_READ_DATE, "2026-11-08")
        self.assertEqual(len(BROWSER_MODE_RISK_ITEMS), 9)
        risk_text = "\n".join(
            item.title + "\n" + item.body
            for item in BROWSER_MODE_RISK_ITEMS
        )
        self.assertIn("可用：手机号、微信扫码", risk_text)
        self.assertIn("内嵌窗口不支持 Apple 登录", risk_text)
        self.assertIn("不会为了登录擅自扩大白名单", risk_text)
        dialog = OfficialWebRiskDialog(
            risk_items=BROWSER_MODE_RISK_ITEMS,
            require_countdown=False,
            require_confirmation=False,
            title="浏览器模式风险",
            terms_read_date=BROWSER_MODE_TERMS_READ_DATE,
        )
        self.assertEqual(len(dialog.risk_checkboxes), 9)
        self.assertIsNone(dialog.confirm_edit)
        self.assertTrue(dialog.countdown_label.isHidden())
        self.assertFalse(dialog.accept_button.isEnabled())
        dialog.reject()

    def test_browser_settings_state_lists_supported_login_methods(self) -> None:
        panel = SettingsPanel()
        joined = "\n".join(
            label.text()
            for label in panel.findChildren(QLabel)
        )
        self.assertIn("当前版本内嵌窗口可用：手机号、微信扫码", joined)
        self.assertIn("内嵌窗口不支持 Apple 登录", joined)
        panel.deleteLater()

    def test_browser_mode_without_component_explains_import_requirement(self) -> None:
        panel = SettingsPanel()
        panel.set_official_web_state(
            installed=False,
            message="实验性官网组件尚未导入。",
            consent_current=False,
        )
        browser = panel.access_selection.button_for("official_browser")
        self.assertFalse(browser.isEnabled())
        self.assertIn("需先导入", browser.text())
        self.assertIn("组件", panel.browser_open_button.toolTip())
        panel.deleteLater()

    def test_browser_consent_version_and_date_control_component_start(self) -> None:
        valid = AppConfig(
            access_method="official_browser",
            browser_mode_consent_version=BROWSER_MODE_RISK_VERSION,
            browser_mode_terms_read_date=BROWSER_MODE_TERMS_READ_DATE,
            browser_mode_consent_at="2026-11-08T10:00:00+08:00",
        )
        self.assertTrue(browser_consent_is_current(valid))
        self.assertTrue(browser_mode_ready(valid, True)[0])
        self.assertFalse(browser_mode_ready(valid, False)[0])
        stale, reason = startup_access_config(
            AppConfig(access_method="official_browser"),
            component_installed=True,
        )
        self.assertEqual(stale.access_method, "api")
        self.assertEqual(stale.browser_mode_consent_version, 0)
        self.assertIn("同意", reason)

    def test_browser_fields_round_trip_and_preserve_unknown_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_config(
                AppConfig(
                    browser_mode_consent_version=1,
                    browser_mode_terms_read_date="2026-11-08",
                    browser_mode_consent_at="2026-11-08T10:00:00+08:00",
                    browser_clipboard_auto_clear_enabled=False,
                    browser_clipboard_clear_seconds=90,
                    browser_screen_capture_consent_version=1,
                    browser_voice_consent_version=1,
                ),
                path,
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            data["future_browser_field"] = {"keep": True}
            path.write_text(json.dumps(data), encoding="utf-8")
            loaded = load_config(path)
            self.assertFalse(loaded.browser_clipboard_auto_clear_enabled)
            self.assertEqual(loaded.browser_clipboard_clear_seconds, 90)
            self.assertEqual(loaded.browser_screen_capture_consent_version, 1)
            self.assertEqual(loaded.browser_voice_consent_version, 1)
            save_config(loaded, path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["future_browser_field"],
                {"keep": True},
            )
