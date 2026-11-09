"""Mode/access switching prompt and rollback behavior."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.config import AppConfig  # noqa: E402
from ai_quiz_overlay.controller import ApplicationController  # noqa: E402
from ai_quiz_overlay.ui.settings_panel import SettingsValues  # noqa: E402


def settings_values(access_method: str = "api") -> SettingsValues:
    return SettingsValues(
        api_key="fake-unit-key",
        access_method=access_method,
        work_mode="quiz",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=60,
        hotkeys={
            "chat": "Ctrl+Alt+Q",
            "screenshot": "Ctrl+Alt+A",
            "assistant": "Ctrl+Alt+Space",
            "ball_visibility": "Ctrl+Alt+B",
            "screen_recognition": "Ctrl+Alt+S",
        },
        image_max_edge=1600,
        auto_send_screenshot=False,
        no_focus_mode=False,
        opacity=1.0,
        acrylic_enabled=True,
        assistant_ball_persistent=True,
        assistant_auto_hide_seconds=60,
        assistant_ball_size=64,
        screen_recognition_auto_send=False,
        screen_recognition_prompt="请概括当前画面。",
        screen_recognition_image_max_edge=2048,
        screen_recognition_consent_version=1,
    )


class FakeWindow:
    def __init__(self, values: SettingsValues, busy: bool) -> None:
        self.values = values
        self.busy = busy
        self.statuses: list[str] = []
        self.stop_callback = None
        self.exit_prepared = False
        self.settings_panel = type(
            "Panel",
            (),
            {"hotkeys_valid": True},
        )()

    @property
    def is_busy(self) -> bool:
        return self.busy

    def current_settings_values(self) -> SettingsValues:
        return self.values

    def set_settings_status(self, message: str, is_error: bool = False) -> None:
        self.statuses.append(message)

    def stop_request_then(self, callback) -> None:
        self.stop_callback = callback

    def prepare_exit(self) -> None:
        self.exit_prepared = True


class FakeMode:
    definition = type("Definition", (), {"key": "quiz"})()

    def __init__(self, window: FakeWindow) -> None:
        self.window = window

    def is_busy(self) -> bool:
        return self.window.is_busy


class ContextSwitchTests(unittest.TestCase):
    def _controller(self, busy: bool):
        controller = ApplicationController.__new__(ApplicationController)
        controller.window = FakeWindow(settings_values("api"), busy)
        controller._config = AppConfig(
            access_method="official_login",
            work_mode="quiz",
        )
        controller.mode_coordinator = type(
            "Coordinator",
            (),
            {"current": FakeMode(controller.window)},
        )()
        return controller

    def test_cancel_switch_keeps_request_and_config_unchanged(self) -> None:
        controller = self._controller(busy=True)
        original_config = controller._config
        with patch.object(
            controller,
            "_confirm_stop_for_context_switch",
            return_value=False,
        ):
            controller.save_settings()
        self.assertEqual(controller._config, original_config)
        self.assertIsNone(controller.window.stop_callback)
        self.assertIn("取消切换", controller.window.statuses[-1])
        self.assertIn("保持不变", controller.window.statuses[-1])

    def test_confirmed_switch_defers_action_until_request_stops(self) -> None:
        controller = self._controller(busy=True)
        original_config = controller._config
        with patch.object(
            controller,
            "_confirm_stop_for_context_switch",
            return_value=True,
        ):
            controller.save_settings()
        self.assertEqual(controller._config, original_config)
        self.assertIsNotNone(controller.window.stop_callback)
        self.assertIn("正在停止当前回答", controller.window.statuses[-1])

    def test_exit_waits_for_active_assistant_request(self) -> None:
        controller = ApplicationController.__new__(ApplicationController)
        controller.window = FakeWindow(settings_values("api"), False)
        controller._exit_in_progress = False
        callbacks: list[object] = []
        controller.assistant = type(
            "Assistant",
            (),
            {
                "is_busy": True,
                "stop_request_then": lambda _self, callback: callbacks.append(
                    callback
                ),
            },
        )()
        controller.mode_coordinator = type(
            "Coordinator",
            (),
            {
                "current": type(
                    "Mode",
                    (),
                    {
                        "definition": type(
                            "Definition",
                            (),
                            {"key": "global_assistant"},
                        )()
                    },
                )()
            },
        )()

        controller.request_exit()
        self.assertFalse(controller.window.exit_prepared)
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        self.assertTrue(controller.window.exit_prepared)


if __name__ == "__main__":
    unittest.main()
