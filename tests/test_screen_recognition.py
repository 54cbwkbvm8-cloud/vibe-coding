"""One-shot screen recognition flow tests with synthetic images."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.config import (  # noqa: E402
    AppConfig,
    load_config,
    save_config,
)
from ai_quiz_overlay.controller import (  # noqa: E402
    ApplicationController,
    BrowserCaptureSnapshot,
    ScreenRecognitionSnapshot,
)
from ai_quiz_overlay.assistant_controller import (  # noqa: E402
    AssistantVisibilitySnapshot,
)


class FakeDefinition:
    def __init__(self, key: str) -> None:
        self.key = key


class FakeMode:
    def __init__(self, key: str) -> None:
        self.definition = FakeDefinition(key)

    def is_busy(self) -> bool:
        return False


class FakeCoordinator:
    def __init__(self, key: str) -> None:
        self.current = FakeMode(key)


class FakePreview:
    def __init__(self) -> None:
        self.cleared = 0
        self.hidden = 0
        self.visible = False

    def clear_image(self) -> None:
        self.cleared += 1

    def hide(self) -> None:
        self.hidden += 1
        self.visible = False

    def isVisible(self) -> bool:
        return self.visible


class FakePanel:
    def __init__(self) -> None:
        self.consent_states: list[bool] = []
        self.voice_consent_states: list[bool] = []
        self.statuses: list[str] = []

    def set_screen_consent_state(self, granted: bool) -> None:
        self.consent_states.append(granted)

    def set_voice_consent_state(self, granted: bool) -> None:
        self.voice_consent_states.append(granted)

    def set_browser_screen_consent_state(self, granted: bool) -> None:
        self.consent_states.append(granted)

    def set_browser_voice_consent_state(self, granted: bool) -> None:
        self.voice_consent_states.append(granted)

    def set_status(self, message: str, is_error: bool = False) -> None:
        self.statuses.append(message)


class FakeWindow:
    def __init__(self) -> None:
        self.settings_panel = FakePanel()
        self.visible = True
        self.hidden = 0

    def isVisible(self) -> bool:
        return self.visible

    def hide_overlay(self) -> None:
        self.visible = False
        self.hidden += 1


class FakeAssistant:
    def __init__(self) -> None:
        self.prepared = []
        self.sent = []
        self.restored = []
        self.focus_restored = 0
        self.capture_hidden = 0
        self.capture_snapshot = AssistantVisibilitySnapshot(
            input_visible=True,
            bubble_visible=False,
            ball_visible=False,
            ball_should_show=True,
            anchor=QRect(200, 160, 240, 240),
        )

    def prepare_screen_recognition_result(self, snapshot) -> None:
        self.prepared.append(snapshot)

    def send_screen_recognition(self, image, prompt: str) -> bool:
        self.sent.append((image, prompt))
        return True

    def restore_visibility_snapshot(self, snapshot) -> None:
        self.restored.append(snapshot)

    def restore_primary_input_focus(self) -> None:
        self.focus_restored += 1

    def capture_visibility_snapshot(self):
        return self.capture_snapshot

    def hide_all_for_screen_capture(self) -> None:
        self.capture_hidden += 1


class FakeScreen:
    def __init__(self, image: QImage) -> None:
        self._pixmap = QPixmap.fromImage(image)
        self.grab_calls = 0

    def grabWindow(self, _window_id: int) -> QPixmap:
        self.grab_calls += 1
        return self._pixmap


class FakeBrowserProcess:
    def __init__(self, visible: bool = True) -> None:
        self.browser_visible = visible
        self.shown = 0
        self.hidden = 0
        self.messages: list[str] = []

    def show(self) -> bool:
        self.shown += 1
        self.browser_visible = True
        return True

    def hide(self) -> bool:
        self.hidden += 1
        self.browser_visible = False
        return True

    def set_message(self, message: str) -> bool:
        self.messages.append(message)
        return True

    def set_voice_state(self, _state: str) -> bool:
        return True


class ScreenRecognitionConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_first_consent_is_persisted_before_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            controller = ApplicationController.__new__(ApplicationController)
            controller.window = FakeWindow()
            controller._config = AppConfig(
                screen_recognition_consent_version=0
            )
            controller._config_path = path
            dialog = MagicMock()
            accept = object()
            dialog.addButton.side_effect = [accept, object()]
            dialog.clickedButton.return_value = accept
            with patch(
                "ai_quiz_overlay.controller.QMessageBox",
                return_value=dialog,
            ):
                self.assertTrue(
                    controller._confirm_screen_recognition_consent()
                )
            self.assertEqual(
                load_config(path).screen_recognition_consent_version,
                1,
            )
            self.assertEqual(
                controller.window.settings_panel.consent_states,
                [True],
            )

    def test_rejected_first_consent_does_not_enter_capture_state(self) -> None:
        controller = ApplicationController.__new__(ApplicationController)
        controller._screen_capture_screen = None
        controller._screen_recognition_image = None
        controller.screen_recognition_preview = FakePreview()
        controller._config = AppConfig(
            screen_recognition_consent_version=0
        )
        controller.mode_coordinator = FakeCoordinator("quiz")
        controller._current_mode_busy = lambda: False
        controller._confirm_screen_recognition_consent = lambda: False
        controller.start_screen_recognition()
        self.assertIsNone(controller._screen_capture_screen)
        self.assertIsNone(controller._screen_recognition_image)

    def test_voice_consent_is_persisted_and_can_be_revoked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            controller = ApplicationController.__new__(ApplicationController)
            controller.window = FakeWindow()
            controller._config = AppConfig(voice_consent_version=0)
            controller._config_path = path
            dialog = MagicMock()
            accept = object()
            dialog.addButton.side_effect = [accept, object()]
            dialog.clickedButton.return_value = accept
            with patch(
                "ai_quiz_overlay.controller.QMessageBox",
                return_value=dialog,
            ):
                self.assertTrue(controller._confirm_voice_consent())
            self.assertEqual(load_config(path).voice_consent_version, 1)
            controller.screen_recognition_preview = FakePreview()
            controller.revoke_voice_consent()
            self.assertEqual(load_config(path).voice_consent_version, 0)
            self.assertEqual(
                controller.window.settings_panel.voice_consent_states,
                [True, False],
            )

    def test_revoke_consent_persists_zero_and_clears_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_config(
                AppConfig(screen_recognition_consent_version=1),
                path,
            )
            controller = ApplicationController.__new__(ApplicationController)
            controller.window = FakeWindow()
            controller._config = load_config(path)
            controller._config_path = path
            controller.screen_recognition_preview = FakePreview()
            controller._screen_capture_screen = None
            controller._screen_recognition_image = None
            controller._screen_recognition_snapshot = None
            controller.revoke_screen_recognition_consent()
            self.assertEqual(
                load_config(path).screen_recognition_consent_version,
                0,
            )
            self.assertEqual(
                controller.window.settings_panel.consent_states,
                [False],
            )

    def test_auto_send_takes_exactly_one_synthetic_screen_capture(self) -> None:
        image = QImage(640, 360, QImage.Format.Format_RGB32)
        image.fill(QColor("#203040"))
        screen = FakeScreen(image)
        controller = ApplicationController.__new__(ApplicationController)
        controller._config = AppConfig(
            screen_recognition_auto_send=True,
        )
        controller._screen_capture_screen = screen
        controller._screen_recognition_snapshot = ScreenRecognitionSnapshot(
            mode_key="quiz",
            main_visible=True,
            assistant=None,
        )
        dispatched: list[tuple[QImage, str]] = []
        controller._dispatch_screen_recognition = (
            lambda captured, prompt: dispatched.append((captured, prompt))
        )
        controller._capture_screen_recognition_once()
        self.assertEqual(screen.grab_calls, 1)
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0][0].size(), image.size())

    def test_start_hides_all_surfaces_before_delayed_capture(self) -> None:
        controller = ApplicationController.__new__(ApplicationController)
        controller._screen_capture_screen = None
        controller._screen_recognition_image = None
        controller.screen_recognition_preview = FakePreview()
        controller._config = AppConfig(
            screen_recognition_consent_version=1
        )
        controller.window = FakeWindow()
        controller.assistant = FakeAssistant()
        controller.mode_coordinator = FakeCoordinator("global_assistant")
        controller._confirm_screen_recognition_consent = lambda: True
        controller._screen_recognition_preflight_error = lambda: None
        fake_screen = object()
        scheduled: list[tuple[int, object]] = []
        with (
            patch(
                "ai_quiz_overlay.controller.QGuiApplication.screenAt",
                return_value=fake_screen,
            ),
            patch(
                "ai_quiz_overlay.controller.foreground_window",
                return_value=4321,
            ),
            patch(
                "ai_quiz_overlay.controller.QTimer.singleShot",
                side_effect=lambda delay, callback: scheduled.append(
                    (delay, callback)
                ),
            ),
        ):
            controller.start_screen_recognition()
        self.assertEqual(controller.window.hidden, 1)
        self.assertEqual(controller.assistant.capture_hidden, 1)
        self.assertIs(controller._screen_capture_screen, fake_screen)
        self.assertEqual(scheduled[0][0], 250)
        self.assertEqual(
            controller._screen_recognition_snapshot.previous_foreground,
            4321,
        )

    def test_dispatch_preserves_hidden_assistant_ball_state(self) -> None:
        controller = ApplicationController.__new__(ApplicationController)
        controller.window = MagicMock()
        controller.assistant = FakeAssistant()
        assistant_snapshot = AssistantVisibilitySnapshot(
            input_visible=False,
            bubble_visible=False,
            ball_visible=False,
            ball_should_show=False,
            anchor=QRect(300, 200, 96, 96),
        )
        controller._screen_recognition_snapshot = (
            ScreenRecognitionSnapshot(
                mode_key="global_assistant",
                main_visible=False,
                assistant=assistant_snapshot,
            )
        )
        controller._screen_recognition_image = QImage(
            320,
            200,
            QImage.Format.Format_RGB32,
        )
        image = controller._screen_recognition_image
        controller._dispatch_screen_recognition(image, "提示词")
        self.assertEqual(
            controller.assistant.prepared,
            [assistant_snapshot],
        )
        self.assertEqual(len(controller.assistant.sent), 1)
        self.assertFalse(assistant_snapshot.ball_should_show)
        self.assertIsNone(controller._screen_recognition_image)
        self.assertIsNone(controller._screen_recognition_snapshot)

    def test_preview_cancel_can_restore_previous_external_focus(self) -> None:
        controller = ApplicationController.__new__(ApplicationController)
        controller.window = MagicMock()
        controller.assistant = FakeAssistant()
        assistant_snapshot = AssistantVisibilitySnapshot(
            input_visible=False,
            bubble_visible=False,
            ball_visible=False,
            ball_should_show=False,
            anchor=QRect(300, 200, 96, 96),
        )
        snapshot = ScreenRecognitionSnapshot(
            mode_key="global_assistant",
            main_visible=False,
            assistant=assistant_snapshot,
            previous_foreground=9876,
        )
        restored: list[int] = []
        controller._activate_previous_foreground = restored.append
        with patch(
            "ai_quiz_overlay.controller.IS_WINDOWS",
            True,
        ):
            controller._restore_screen_recognition_surfaces(
                snapshot,
                restore_focus=True,
            )
            QTest.qWait(30)
        self.assertEqual(restored, [9876])

    def test_browser_screen_recognition_only_copies_image(self) -> None:
        image = QImage(320, 180, QImage.Format.Format_RGB32)
        image.fill(QColor("#334455"))
        screen = FakeScreen(image)
        controller = ApplicationController.__new__(ApplicationController)
        controller._config = AppConfig(
            access_method="official_browser",
            browser_screen_capture_consent_version=1,
        )
        controller._screen_capture_screen = screen
        controller._screen_recognition_snapshot = ScreenRecognitionSnapshot(
            mode_key="official_browser",
            main_visible=False,
            assistant=None,
            browser_visible=False,
        )
        controller.screen_recognition_preview = FakePreview()
        controller.window = MagicMock()
        controller.official_web_process = FakeBrowserProcess(False)
        controller.browser_clipboard = MagicMock()
        controller._dispatch_screen_recognition = MagicMock()
        controller._capture_screen_recognition_once()
        self.assertEqual(screen.grab_calls, 1)
        controller.browser_clipboard.set_image.assert_called_once()
        controller._dispatch_screen_recognition.assert_not_called()
        self.assertEqual(controller.official_web_process.shown, 0)

    def test_browser_region_capture_copies_and_restores_visible_window(self) -> None:
        controller = ApplicationController.__new__(ApplicationController)
        controller._screenshot_overlay = object()
        controller._browser_capture_snapshot = BrowserCaptureSnapshot(
            main_visible=False,
            browser_visible=True,
            previous_foreground=0,
        )
        controller.official_web_process = FakeBrowserProcess(False)
        controller.browser_clipboard = MagicMock()
        controller.window = MagicMock()
        image = QImage(120, 80, QImage.Format.Format_RGB32)
        controller._on_screenshot_selected(image)
        controller.browser_clipboard.set_image.assert_called_once_with(image)
        self.assertEqual(controller.official_web_process.shown, 1)
        self.assertIsNone(controller._browser_capture_snapshot)
        controller.window.set_pending_screenshot.assert_not_called()

    def test_browser_region_capture_keeps_hidden_window_hidden(self) -> None:
        controller = ApplicationController.__new__(ApplicationController)
        controller._screenshot_overlay = object()
        controller._browser_capture_snapshot = BrowserCaptureSnapshot(
            main_visible=False,
            browser_visible=False,
        )
        controller.official_web_process = FakeBrowserProcess(False)
        controller.browser_clipboard = MagicMock()
        controller.window = MagicMock()
        controller._on_screenshot_selected(
            QImage(80, 60, QImage.Format.Format_RGB32)
        )
        self.assertEqual(controller.official_web_process.shown, 0)
        self.assertEqual(controller.official_web_process.hidden, 0)


if __name__ == "__main__":
    unittest.main()
