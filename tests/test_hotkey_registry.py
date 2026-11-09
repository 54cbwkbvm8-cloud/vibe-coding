"""Transactional hotkey registry tests using a local fake backend."""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.hotkeys import (  # noqa: E402
    HotkeyRegistry,
    validate_hotkey_values,
)
from ai_quiz_overlay.hotkey_definitions import (  # noqa: E402
    active_hotkey_keys,
)
from ai_quiz_overlay.win32.hotkey import (  # noqa: E402
    HotkeyConfigError,
    HotkeyRegistrationError,
)


class FakeHotkeyBackend:
    def __init__(self) -> None:
        self.registered: dict[int, tuple[str, str]] = {}
        self.register_calls: list[tuple[str, int, str]] = []
        self.unregister_calls: list[int] = []
        self.fail_texts: set[str] = set()

    def register(
        self,
        hwnd: int,
        hotkey_text: str,
        hotkey_id: int,
        action: str,
    ) -> None:
        self.register_calls.append((hotkey_text, hotkey_id, action))
        if hotkey_text in self.fail_texts:
            raise HotkeyRegistrationError(
                f"快捷键 {hotkey_text} 已被其他程序占用。"
            )
        self.registered[hotkey_id] = (hotkey_text, action)

    def unregister(self, hotkey_id: int | None = None) -> None:
        ids = list(self.registered) if hotkey_id is None else [hotkey_id]
        for current_id in ids:
            self.unregister_calls.append(current_id)
            self.registered.pop(current_id, None)


class HotkeyRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeHotkeyBackend()
        self.registry = HotkeyRegistry(self.backend, lambda: 123)
        self.defaults = {
            "chat": "Ctrl+Alt+Q",
            "screenshot": "Ctrl+Alt+A",
            "assistant": "Ctrl+Alt+Space",
            "ball_visibility": "Ctrl+Alt+B",
            "screen_recognition": "Ctrl+Alt+S",
        }
        self.active_keys = active_hotkey_keys("quiz")
        self.registry.register_initial(self.defaults, self.active_keys)

    def test_initial_registration_uses_one_entry_per_feature(self) -> None:
        self.assertEqual(
            sorted(value[1] for value in self.backend.registered.values()),
            ["chat", "screen_recognition", "screenshot"],
        )
        self.assertEqual(len(self.registry.active_ids), 3)

    def test_only_changed_hotkey_is_temporarily_registered(self) -> None:
        old_chat_id = self.registry.active_ids["chat"]
        old_screenshot_id = self.registry.active_ids["screenshot"]
        call_count = len(self.backend.register_calls)

        prepared = self.registry.prepare(
            {
                "chat": "Ctrl+Shift+F11",
                "screenshot": "Ctrl+Alt+A",
                "assistant": "Ctrl+Alt+Space",
                "ball_visibility": "Ctrl+Alt+B",
                "screen_recognition": "Ctrl+Alt+S",
            },
            self.active_keys,
        )
        self.assertEqual(prepared.changed_keys, ("chat",))
        self.assertEqual(len(self.backend.register_calls), call_count + 1)
        self.assertIn(old_chat_id, self.backend.registered)
        self.assertIn(old_screenshot_id, self.backend.registered)

        prepared.commit()
        self.assertNotIn(old_chat_id, self.backend.registered)
        self.assertIn(old_screenshot_id, self.backend.registered)
        self.assertIn(
            "Ctrl+Shift+F11",
            [value[0] for value in self.backend.registered.values()],
        )
        self.assertNotIn(
            "Ctrl+Alt+Q",
            [value[0] for value in self.backend.registered.values()],
        )

    def test_occupied_hotkey_rolls_back_all_temporary_registrations(self) -> None:
        old_ids = self.registry.active_ids
        old_registered = dict(self.backend.registered)
        self.backend.fail_texts.add("Ctrl+Shift+F12")

        with self.assertRaises(HotkeyRegistrationError):
            self.registry.prepare(
                {
                    "chat": "Ctrl+Shift+F11",
                    "screenshot": "Ctrl+Shift+F12",
                    "assistant": "Ctrl+Alt+Space",
                    "ball_visibility": "Ctrl+Alt+B",
                    "screen_recognition": "Ctrl+Alt+S",
                },
                self.active_keys,
            )

        self.assertEqual(self.registry.active_ids, old_ids)
        self.assertEqual(self.backend.registered, old_registered)

    def test_duplicate_parsed_hotkeys_are_rejected(self) -> None:
        with self.assertRaises(HotkeyConfigError):
            validate_hotkey_values(
                {
                    "chat": "Ctrl+Alt+Q",
                    "screenshot": "Alt+Ctrl+Q",
                    "assistant": "Ctrl+Alt+Space",
                    "ball_visibility": "Ctrl+Alt+B",
                    "screen_recognition": "Ctrl+Alt+S",
                }
            )

    def test_suspend_and_resume_recreate_all_active_bindings(self) -> None:
        self.registry.suspend()
        self.assertTrue(self.registry.suspended)
        self.assertEqual(self.backend.registered, {})
        with self.assertRaises(HotkeyConfigError):
            self.registry.prepare(
                {
                    "chat": "Ctrl+Shift+F11",
                    "screenshot": "Ctrl+Shift+F12",
                    "assistant": "Ctrl+Alt+Space",
                    "ball_visibility": "Ctrl+Alt+B",
                    "screen_recognition": "Ctrl+Alt+S",
                },
                self.active_keys,
            )
        self.registry.resume()
        self.assertFalse(self.registry.suspended)
        self.assertEqual(
            sorted(value[1] for value in self.backend.registered.values()),
            ["chat", "screen_recognition", "screenshot"],
        )

    def test_saved_values_register_after_restart(self) -> None:
        saved = {
            "chat": "Ctrl+Shift+F11",
            "screenshot": "Ctrl+Shift+F12",
            "assistant": "Ctrl+Alt+Space",
            "ball_visibility": "Ctrl+Shift+B",
            "screen_recognition": "Ctrl+Alt+S",
        }
        prepared = self.registry.prepare(saved, self.active_keys)
        prepared.commit()

        restarted_backend = FakeHotkeyBackend()
        restarted = HotkeyRegistry(restarted_backend, lambda: 456)
        restarted.register_initial(saved, self.active_keys)
        self.assertEqual(
            {value[0] for value in restarted_backend.registered.values()},
            {
                saved["chat"],
                saved["screenshot"],
                saved["screen_recognition"],
            },
        )

    def test_screen_recognition_is_registered_in_quiz_mode(self) -> None:
        registered_values = {
            value[0]
            for value in self.backend.registered.values()
        }
        self.assertIn("Ctrl+Alt+S", registered_values)
        self.assertNotIn("Ctrl+Alt+Space", registered_values)
        self.assertNotIn("Ctrl+Alt+B", registered_values)
        self.assertEqual(
            active_hotkey_keys("quiz"),
            ("chat", "screenshot", "screen_recognition"),
        )

    def test_mode_scope_switch_releases_inactive_bindings(self) -> None:
        prepared = self.registry.prepare(
            self.defaults,
            active_keys=(),
        )
        prepared.commit()
        self.assertEqual(self.backend.registered, {})
        self.assertEqual(self.registry.active_values, {})

    def test_assistant_scope_registers_both_assistant_hotkeys(self) -> None:
        screen_recognition_id = self.registry.active_ids[
            "screen_recognition"
        ]
        prepared = self.registry.prepare(
            self.defaults,
            active_keys=active_hotkey_keys("global_assistant"),
        )
        prepared.commit()
        self.assertEqual(
            sorted(
                value[1]
                for value in self.backend.registered.values()
            ),
            ["assistant", "ball_visibility", "screen_recognition"],
        )
        self.assertEqual(
            set(self.registry.active_values),
            {"assistant", "ball_visibility", "screen_recognition"},
        )
        self.assertEqual(
            self.registry.active_ids["screen_recognition"],
            screen_recognition_id,
        )

    def test_failed_mode_scope_registration_keeps_old_bindings(self) -> None:
        old_ids = self.registry.active_ids
        old_registered = dict(self.backend.registered)
        self.backend.fail_texts.add("Ctrl+Alt+B")
        with self.assertRaises(HotkeyRegistrationError):
            self.registry.prepare(
                self.defaults,
                active_keys=("assistant", "ball_visibility"),
            )
        self.assertEqual(self.registry.active_ids, old_ids)
        self.assertEqual(self.backend.registered, old_registered)

    def test_occupied_screen_recognition_hotkey_rolls_back(self) -> None:
        old_ids = self.registry.active_ids
        old_registered = dict(self.backend.registered)
        self.backend.fail_texts.add("Ctrl+Shift+F9")
        values = dict(self.defaults)
        values["screen_recognition"] = "Ctrl+Shift+F9"
        with self.assertRaises(HotkeyRegistrationError):
            self.registry.prepare(values, self.active_keys)
        self.assertEqual(self.registry.active_ids, old_ids)
        self.assertEqual(self.backend.registered, old_registered)


if __name__ == "__main__":
    unittest.main()
