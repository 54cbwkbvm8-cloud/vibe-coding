"""200% 缩放下的逻辑选区到物理像素换算。"""

from pathlib import Path
import sys
import unittest

from PySide6.QtCore import QRect, QSize


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services.screenshot_geometry import (  # noqa: E402
    selection_to_image_rect,
)


class ScreenshotGeometryTests(unittest.TestCase):
    def test_200_percent_mapping(self) -> None:
        mapped = selection_to_image_rect(
            QRect(100, 80, 300, 200),
            QSize(1600, 900),
            QSize(3200, 1800),
        )
        self.assertEqual(mapped, QRect(200, 160, 600, 400))

    def test_selection_is_clamped_to_image(self) -> None:
        mapped = selection_to_image_rect(
            QRect(700, 400, 500, 300),
            QSize(1000, 600),
            QSize(2000, 1200),
        )
        self.assertEqual(mapped, QRect(1400, 800, 600, 400))


if __name__ == "__main__":
    unittest.main()
