"""Work-mode registry and independent feature-scope tests."""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services.provider_registry import ACCESS_METHODS  # noqa: E402
from ai_quiz_overlay.work_modes import (  # noqa: E402
    WORK_MODES,
    create_work_mode,
)


class WorkModeTests(unittest.TestCase):
    def test_quiz_mode_uses_existing_hotkeys_only(self) -> None:
        mode = create_work_mode("quiz")
        self.assertEqual(
            mode.active_hotkey_keys(),
            ("chat", "screenshot", "screen_recognition"),
        )

    def test_global_assistant_uses_its_mode_hotkeys(self) -> None:
        definition = next(
            item for item in WORK_MODES if item.key == "global_assistant"
        )
        self.assertTrue(definition.enabled)
        self.assertEqual(definition.unavailable_reason, "")
        mode = create_work_mode("global_assistant")
        self.assertEqual(
            mode.active_hotkey_keys(),
            ("assistant", "ball_visibility", "screen_recognition"),
        )

    def test_access_and_work_mode_dimensions_are_independent(self) -> None:
        access_keys = {item.key for item in ACCESS_METHODS}
        mode_keys = {item.key for item in WORK_MODES}
        self.assertEqual(
            access_keys,
            {"api", "official_login", "official_browser"},
        )
        self.assertEqual(mode_keys, {"quiz", "global_assistant"})


if __name__ == "__main__":
    unittest.main()
