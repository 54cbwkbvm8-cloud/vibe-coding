"""窗口位置恢复与离屏回退测试。"""

from pathlib import Path
import sys
import unittest

from PySide6.QtCore import QRect, QSize


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.config import WindowGeometry  # noqa: E402
from ai_quiz_overlay.services.window_geometry import restore_window_rect  # noqa: E402


class WindowGeometryTests(unittest.TestCase):
    def test_saved_visible_position_is_used(self) -> None:
        result = restore_window_rect(
            WindowGeometry(100, 120, 500, 620),
            [QRect(0, 0, 1920, 1080)],
            QSize(420, 560),
        )
        self.assertEqual(result, QRect(100, 120, 500, 620))

    def test_offscreen_position_is_centered(self) -> None:
        result = restore_window_rect(
            WindowGeometry(5000, 5000, 420, 560),
            [QRect(0, 0, 1920, 1080)],
            QSize(420, 560),
        )
        self.assertEqual(result, QRect(750, 260, 420, 560))

    def test_partially_visible_window_is_clamped(self) -> None:
        result = restore_window_rect(
            WindowGeometry(1800, 900, 500, 620),
            [QRect(0, 0, 1920, 1080)],
            QSize(420, 560),
        )
        self.assertEqual(result, QRect(1420, 460, 500, 620))


if __name__ == "__main__":
    unittest.main()
