"""跨平台导入约定的测试。"""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay import platform_support  # noqa: E402


class PlatformSupportTests(unittest.TestCase):
    def test_non_windows_call_raises_clear_error(self) -> None:
        with patch.object(platform_support, "IS_WINDOWS", False):
            with self.assertRaises(platform_support.UnsupportedPlatformError):
                platform_support.require_windows("全局快捷键")

    def test_windows_call_is_allowed(self) -> None:
        with patch.object(platform_support, "IS_WINDOWS", True):
            platform_support.require_windows("全局快捷键")


if __name__ == "__main__":
    unittest.main()
