"""Win32 快捷键解析测试；导入过程不应访问 Windows API。"""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.win32.hotkey import (  # noqa: E402
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    HotkeyConfigError,
    parse_hotkey,
)


class HotkeyParserTests(unittest.TestCase):
    def test_ctrl_alt_q(self) -> None:
        spec = parse_hotkey("Ctrl+Alt+Q")
        self.assertEqual(spec.modifiers, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT)
        self.assertEqual(spec.virtual_key, ord("Q"))

    def test_ctrl_shift_q(self) -> None:
        spec = parse_hotkey("Ctrl+Shift+Q")
        self.assertEqual(spec.modifiers, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT)
        self.assertEqual(spec.virtual_key, ord("Q"))

    def test_function_key(self) -> None:
        spec = parse_hotkey("Ctrl+Alt+F8")
        self.assertEqual(spec.virtual_key, 0x77)

    def test_missing_modifier_is_rejected(self) -> None:
        with self.assertRaises(HotkeyConfigError):
            parse_hotkey("Q")

    def test_unknown_key_is_rejected(self) -> None:
        with self.assertRaises(HotkeyConfigError):
            parse_hotkey("Ctrl+Alt+NotAKey")


if __name__ == "__main__":
    unittest.main()
